# -*- coding: utf-8 -*-
"""
Tests of smartds_repairs.py (the repairs of three defects of the SMART-DS release) on small
made-up feeders written by the test: the detection rules, the changes, the bytes the apply
function keeps in each file it writes, the phase pre command and its stops, and the
setting smartds_repairs. Also
the repairs in memory (repaired_texts) that phase growth reads. Also the Phase 8 head of a
regulator (8_results_analysis/aggregate_m1_m2_with_circuits.py):
feeder_head_kva and the head columns, with one head and with a second head of network
growth. No OpenDSS and no SMART-DS data.

Run under pytest: pytest tests/test_smartds_repairs.py
"""
import math
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "8_results_analysis"))
import smartds_repairs as sr  # noqa: E402
import aggregate_m1_m2_with_circuits as agg  # noqa: E402
from pipeline_utils import SETTINGS_ENV, load_config, smartds_repairs_on  # noqa: E402

REG = "reg_a(r:x-y)"
REG_LINE = (f"New Transformer.trans_{REG} phases=3 windings=2 buses=(src.1.2.3,b1.1.2.3) "
            f"kvs=(12.47, 12.47) kvas=(10000.0, 10000.0)\n")
SERVICE_72 = ("New Transformer.tr1 phases=1 windings=3 wdg=1 conn=wye bus=b2.1 Kv=7.2 kva=25.0 "
              "wdg=2 conn=wye bus=lv1.1.0 Kv=0.12 kva=25.0 wdg=3 conn=wye bus=lv1.0.2 Kv=0.12 kva=25.0\n")
SERVICE_1247 = ("New Transformer.tr2 phases=3 windings=2 wdg=1 conn=delta bus=b2.1.2.3 Kv=12.47 kva=75.0 "
                "wdg=2 conn=wye bus=lv2.1.2.3 Kv=0.48 kva=75.0\n")
SERVICE_14434 = ("New Transformer.tr3 phases=1 windings=3 wdg=1 conn=wye bus=b2.2 Kv=14.434 kva=25.0 "
                 "wdg=2 conn=wye bus=lv3.1.0 Kv=0.12 kva=25.0 wdg=3 conn=wye bus=lv3.0.2 Kv=0.12 kva=25.0\n")
LINES = "New Line.l1 bus1=b1.1.2.3 bus2=b2.1.2.3 phases=3 linecode=lc1 length=100 units=m\n"
LINECODES = "New Linecode.lc1 nphases=3 r1=0.1 x1=0.2 units=km normamps=325.0\n"
LOADS = "New Load.load_1 bus1=lv1.1 phases=1 kV=0.12 kW=1 kvar=0.2 yearly=res_kw_1_pu\n"
LOADSHAPES = "New Loadshape.res_kw_1_pu npts=96 interval=0.25 mult=(file=x.csv)\n"
C = "regulator_settings_from_voltage"


def master(head, basekv="12.47", vbases="[0.12, 0.208, 7.2, 12.47]", nl="\n"):
    lines = ["Clear", "", f"New Circuit.feeder_x bus1=src pu=1.03 basekV={basekv} R1=1e-05 X1=1e-05", "",
             "Redirect LineCodes.dss", "Redirect Lines.dss", "Redirect Transformers.dss", "Redirect Loads.dss",
             f"new monitor.m1 element={head} mode=0", f"new monitor.m2 element={head} mode=1",
             f"new energymeter.m3 {head}", ""]
    if vbases is not None:
        lines += [f"Set Voltagebases={vbases}", ""]
    lines += ["Calcvoltagebases", "", "Solve mode=yearly stepsize=15m number=35040"]
    return nl.join(lines) + nl


def feeder(head=f"Line.{REG}", transformers=REG_LINE + SERVICE_72, **kw):
    return {"Master.dss": master(head, **kw), "Lines.dss": LINES, "LineCodes.dss": LINECODES,
            "Transformers.dss": transformers, "Loads.dss": LOADS, "LoadShapes.dss": LOADSHAPES}


def write(folder, texts, newline=None):
    os.makedirs(folder, exist_ok=True)
    for name, text in texts.items():
        with open(os.path.join(folder, name), "w", encoding="utf-8", newline=newline or "") as fh:
            fh.write(text)
    return folder


def snapshot(folder):
    return {n: Path(folder, n).read_bytes() for n in sorted(os.listdir(folder))}


# ---------------------------------------------------------------- repair A
def test_repair_a_puts_the_three_head_statements_on_the_regulator(tmp_path):
    texts = feeder()
    changes, defects = sr.check(texts, "f1")
    assert defects == []
    assert [c["repair"] for c in changes] == ["head_meters_on_regulator"] * 3
    assert [c["line"] for c in changes] == [9, 10, 11]
    assert changes[0]["was"] == f"new monitor.m1 element=Line.{REG} mode=0"
    assert changes[0]["now"] == f"new monitor.m1 element=Transformer.trans_{REG} mode=0"
    assert changes[1]["now"] == f"new monitor.m2 element=Transformer.trans_{REG} mode=1"
    # the Energymeter statement names its element without element=
    assert changes[2]["was"] == f"new energymeter.m3 Line.{REG}"
    assert changes[2]["now"] == f"new energymeter.m3 Transformer.trans_{REG}"
    folder = write(tmp_path / "f1", texts)
    before = snapshot(folder)
    applied, _ = sr.repair_folder(folder, "f1")
    after = snapshot(folder)
    assert len(applied) == 3 and sorted(after) == sorted(before)
    assert after["Master.dss"] == master(f"Transformer.trans_{REG}").encode()
    assert all(after[n] == before[n] for n in before if n != "Master.dss")
    assert sr.repair_line(applied[2]) == (f"[repair] f1: head_meters_on_regulator: Master.dss line 11: "
                                          f"new energymeter.m3 Line.{REG} -> new energymeter.m3 Transformer.trans_{REG}")


def test_repair_a_keeps_the_regulator_name_as_written():
    texts = feeder(transformers=REG_LINE.replace(f"trans_{REG}", f"TRANS_{REG.upper()}") + SERVICE_72)
    changes, defects = sr.check(texts, "f1")
    assert defects == [] and changes[0]["now"] == f"new monitor.m1 element=Transformer.TRANS_{REG.upper()} mode=0"


@pytest.mark.parametrize("transformers, why", [
    (SERVICE_72, "0 regulators"),                                                      # no regulator
    (REG_LINE + REG_LINE.replace(f"trans_{REG}", "trans_other"), "2 regulators"),      # two on the source bus
    (REG_LINE.replace("kvs=(12.47, 12.47)", "kvs=(12.47, 7.2)"), "0 regulators"),      # windings of different kV
    (REG_LINE.replace(f"trans_{REG}", "regulator_a"), "not Transformer.trans_"),       # not named trans_<name>
])
def test_repair_a_is_not_offered_without_its_regulator(transformers, why):
    changes, defects = sr.check(feeder(transformers=transformers), "f1")
    assert [c for c in changes if c["repair"] == "head_meters_on_regulator"] == []
    assert len(defects) == 3 and all(r == "head_meters_on_regulator" and why in t for r, t in defects)
    lines = sr.fail_lines("f1", defects)
    assert len(lines) == 3 and all(ln.startswith("[FAIL] f1: head_meters_on_regulator: Master.dss line ")
                                   for ln in lines)


def test_a_head_line_that_exists_is_sound():
    changes, defects = sr.check(feeder(head="Line.l1"), "f1")
    assert changes == [] and defects == []


# ---------------------------------------------------------------- repair B
def test_repair_b_single_phase_14434_under_1247_gives_25():
    texts = feeder(head="Line.l1", transformers=SERVICE_14434, vbases="[0.12, 0.208, 12.47, 14.434]")
    changes, defects = sr.check(texts, "f1")
    assert defects == [] and [c["repair"] for c in changes] == ["source_voltage_from_transformers"] * 2
    assert changes[0]["line"] == 3 and "basekV=12.47" in changes[0]["was"]
    assert changes[0]["now"] == changes[0]["was"].replace("basekV=12.47", "basekV=25.0")
    assert changes[1]["now"] == "Set Voltagebases=[0.12, 0.208, 14.434, 25.0]"


@pytest.mark.parametrize("transformers, before, after", [
    (SERVICE_14434, "[0.12, 0.208, 12.47, 14.434]", "[0.12, 0.208, 14.434, 25.0]"),
    (SERVICE_14434 * 2, "[0.12, 0.208, 12.47, 14.434]", "[0.12, 0.208, 14.434, 25.0]"),
    (SERVICE_14434 + SERVICE_14434.replace("tr3", "tr4"), "[0.12, 0.208, 12.47, 14.434]",
     "[0.12, 0.208, 14.434, 25.0]"),
    ("New Transformer.tr5 phases=3 windings=2 buses=(b2.1.2.3,lv5.1.2.3) kvs=(25.0, 0.48) kvas=(75.0, 75.0)\n",
     "[0.48, 12.47, 25.0]", "[0.48, 25.0]"),
])
def test_repair_b_voltagebases_lists(transformers, before, after):
    changes, _ = sr.check(feeder(head="Line.l1", transformers=transformers, vbases=before), "f1")
    assert changes[-1]["was"] == f"Set Voltagebases={before}" and changes[-1]["now"] == f"Set Voltagebases={after}"


def test_repair_b_without_voltagebases_changes_basekv_only():
    changes, _ = sr.check(feeder(head="Line.l1", transformers=SERVICE_14434, vbases=None), "f1")
    assert len(changes) == 1 and "basekV=25.0" in changes[0]["now"]


@pytest.mark.parametrize("basekv, transformers", [
    ("12.47", SERVICE_72 + SERVICE_1247),                                   # 7.2 x sqrt(3) = 12.47
    ("4.0", "New Transformer.tr6 phases=3 windings=2 buses=(b2.1.2.3,lv6.1.2.3) kvs=(4.0, 0.48) "
            "kvas=(75.0, 75.0)\n"),
    ("12.47", ""),                                                          # no transformer: not checked
    ("12.47", REG_LINE.replace("12.47, 12.47", "25.0, 25.0")),              # a regulator gives no voltage
])
def test_sound_voltages(basekv, transformers):
    changes, defects = sr.check(feeder(head="Line.l1", transformers=transformers, basekv=basekv), "f1")
    assert [c for c in changes if c["repair"] != C] == [] and defects == []


def test_transformer_voltage_rules():
    def voltage(text):
        return sr.transformer_voltage(sr.read_feeder({"Transformers.dss": text}))
    assert voltage(SERVICE_72) == pytest.approx(7.2 * math.sqrt(3.0))
    # a single-phase transformer whose primary bus names two phase nodes is taken at its kV
    assert voltage(SERVICE_14434.replace("bus=b2.2 ", "bus=b2.1.2 ")) == 14.434
    assert voltage(REG_LINE) is None and voltage("") is None
    assert voltage(SERVICE_72 + SERVICE_14434) == pytest.approx(14.434 * math.sqrt(3.0))


# ---------------------------------------------------------------- the apply function
def test_a_sound_feeder_is_not_written(tmp_path):
    folder = write(tmp_path / "f1", feeder(head="Line.l1"))
    before = snapshot(folder)
    stamp = {n: os.stat(os.path.join(folder, n)).st_mtime_ns for n in before}
    assert sr.repair_folder(folder, "f1") == ([], [])
    assert snapshot(folder) == before
    assert {n: os.stat(os.path.join(folder, n)).st_mtime_ns for n in before} == stamp


@pytest.mark.parametrize("nl", ["\r\n", "\n"])
def test_line_endings_are_kept(tmp_path, nl):
    texts = feeder(transformers=REG_LINE + SERVICE_14434, vbases="[0.12, 0.208, 12.47, 14.434]", nl=nl)
    folder = write(tmp_path / "f1", texts)
    changes, _ = sr.repair_folder(folder, "f1")
    assert [c["line"] for c in changes if c["repair"] != C] == [9, 10, 11, 3, 13]
    raw = Path(folder, "Master.dss").read_bytes()
    expected = master(f"Transformer.trans_{REG}", basekv="25.0", vbases="[0.12, 0.208, 14.434, 25.0]", nl=nl)
    assert raw == expected.encode()


def test_the_table(tmp_path):
    changes, _ = sr.check(feeder(), "f1")
    sr.write_table(tmp_path / "t.csv", changes)
    table = pd.read_csv(tmp_path / "t.csv", dtype=str)
    assert list(table.columns) == ["feeder", "repair", "file", "line", "was", "now"] and len(table) == 3
    sr.write_table(tmp_path / "e.csv", [])
    assert Path(tmp_path / "e.csv").read_text(encoding="utf-8") == "feeder,repair,file,line,was,now\n"


# ---------------------------------------------------------------- phase pre
def _pre(tmp_path, texts, settings=None):
    root = tmp_path / "staged"
    write(root / "sub" / "f1", texts)
    registry = tmp_path / "feeder_registry.json"
    registry.write_text('{"feeders": [{"circuit_id": 1, "circuit": "circuit_1", "substation": "sub", '
                        '"feeder_name": "f1", "original_path": "sub/f1/", "flat_dir": "f1/"}], '
                        '"circuit_name_map": {"f1": "circuit_1"}, "reverse_circuit_map": {"circuit_1": "f1"}}',
                        encoding="utf-8")
    env = dict(os.environ, PIPELINE_SMART_DS_ROOT=root.as_posix(), PIPELINE_FEEDER_REGISTRY_PATH=registry.as_posix(),
               PIPELINE_MAX_FEEDERS="null", PYTHONIOENCODING="utf-8")
    env.pop(SETTINGS_ENV, None)
    if settings:
        folder = tmp_path / "settings"
        write(folder, settings)
        env[SETTINGS_ENV] = folder.as_posix()
    before = snapshot(root / "sub" / "f1")
    p = subprocess.run([sys.executable, os.path.join(REPO_ROOT, "smartds_repairs.py"), "--topology-id", "T"],
                       cwd=REPO_ROOT, env=env, capture_output=True, text=True, encoding="utf-8")
    assert snapshot(root / "sub" / "f1") == before  # read only on the staged files
    return p.returncode, p.stdout.splitlines()


def test_pre_repairable_feeder_growth_off(tmp_path):
    code, out = _pre(tmp_path, feeder())
    assert code == 0
    assert [ln for ln in out if ln.startswith("[repair] f1: head_meters_on_regulator: Master.dss line ")][:1]
    assert out[-1] == "[repair] 1 feeders checked: 3 statements to repair on 1 feeders."


def test_pre_defect_without_repair_stops(tmp_path):
    code, out = _pre(tmp_path, feeder(transformers=SERVICE_72))
    assert code == 1
    fails = [ln for ln in out if ln.startswith("[FAIL] f1: head_meters_on_regulator: ")]
    assert len(fails) == 3 and "which no New Line statement of the feeder defines" in fails[0]


def test_pre_repairable_feeder_whatever_the_growth_setting(tmp_path):
    off = _pre(tmp_path / "off", feeder())
    on = _pre(tmp_path / "on", feeder(), settings={"growth.yaml": "growth_years: 5\n"})
    assert off == on and on[0] == 0 and not [ln for ln in on[1] if ln.startswith("[FAIL]")]
    assert len([ln for ln in on[1] if ln.startswith("[repair] f1: head_meters_on_regulator: Master.dss line ")]) == 3
    code, out = _pre(tmp_path / "sound", feeder(head="Line.l1"), settings={"growth.yaml": "growth_years: 5\n"})
    assert code == 0


def test_repaired_texts_in_memory():
    texts = feeder(transformers=REG_LINE + SERVICE_14434, vbases="[0.12, 0.208, 12.47, 14.434]", nl="\r\n")
    before = dict(texts)
    changes, _ = sr.check(texts, "f1")
    changes = [c for c in changes if c["repair"] != C]
    out = sr.repaired_texts(texts, changes)
    assert out["Master.dss"] == master(f"Transformer.trans_{REG}", basekv="25.0", vbases="[0.12, 0.208, 14.434, 25.0]",
                                       nl="\r\n")
    assert all(out[n] is texts[n] for n in texts if n != "Master.dss") and sorted(out) == sorted(texts)
    assert texts == before and texts["Master.dss"] == before["Master.dss"]          # the input is not changed
    assert sr.repaired_texts(texts, []) == texts


def test_growth_reads_the_repaired_source_voltage():
    for sub in ("7_circuit_instantiation", os.path.join("7_circuit_instantiation", "deployer_modules")):
        sys.path.insert(0, os.path.join(REPO_ROOT, sub))
    import growth
    texts = {name.lower(): text for name, text in feeder(head="Line.l1", transformers=SERVICE_14434,
                                                        vbases="[0.12, 0.208, 12.47, 14.434]").items()}
    assert growth.read_feeder(texts)["base_kv"] == 12.47
    repaired = sr.repaired_texts(texts, sr.check(texts, "f1")[0])
    assert growth.read_feeder(repaired)["base_kv"] == 25.0


# ---------------------------------------------------------------- repair C
REG_1PH = "New Transformer.trans_reg_b phases=1 windings=2 buses=(b2x.3,b2.3) kvs=({kv}, {kv}) kvas=(10000.0, 10000.0)\n"
REG_1PH_WDG = ("New Transformer.trans_reg_b phases=1 windings=2 wdg=1 bus=b2x.3 kv={kv} kva=10000.0 "
               "wdg=2 bus=b2.3 kv={kv} kva=10000.0\n")
V25 = {"basekv": "25.0", "vbases": "[0.12, 0.208, 14.434, 25.0]"}


def regcontrol(transformer, ptratio, name="reg_b"):
    settings = f" ptratio={ptratio}" if ptratio is not None else ""
    return f"New RegControl.{name} transformer={transformer} winding=2{settings} band=2.4 vreg = 123.60000000000001\n"


def c_feeder(transformers, regulators, **kw):
    texts = feeder(head="Line.l1", transformers=transformers, **kw)
    texts["Regulators.dss"] = regulators
    return texts


def c_rows(texts):
    changes, defects = sr.check(texts, "f1")
    assert defects == []
    return [c for c in changes if c["repair"] == C]


def test_repair_c_ptratio_of_a_single_phase_regulator_at_25kv():
    texts = c_feeder(SERVICE_14434 + REG_1PH.format(kv=14.434), regcontrol("trans_reg_b", 69.44465262857685), **V25)
    changes, _ = sr.check(texts, "f1")
    assert len(changes) == 1 and changes[0]["repair"] == C
    assert changes[0]["file"] == "Regulators.dss" and changes[0]["line"] == 1
    assert changes[0]["now"] == regcontrol("trans_reg_b", "120.28130608117205").strip()
    assert sr.regulator_counts(sr.read_feeder(texts)) == (0, 0)


@pytest.mark.parametrize("form", [REG_1PH, REG_1PH_WDG])
def test_repair_c_kv_of_a_single_phase_regulator_at_1247(form):
    texts = c_feeder(SERVICE_72 + form.format(kv=12.47), regcontrol("trans_reg_b", 60.0))
    rows = c_rows(texts)
    assert len(rows) == 1 and rows[0]["file"] == "Transformers.dss" and rows[0]["line"] == 2
    assert rows[0]["was"] == form.format(kv=12.47).strip()
    assert rows[0]["now"] == form.format(kv=7.2).strip()


@pytest.mark.parametrize("transformers, ptratio, kw", [
    (SERVICE_72 + REG_LINE, 60.0, {}),
    (SERVICE_72 + REG_LINE, 59.99631547328862, {}),
    (SERVICE_14434 + REG_LINE.replace("12.47, 12.47", "25.0, 25.0"), 120.28130608117205, V25),
])
def test_repair_c_three_phase_regulators_that_fit(transformers, ptratio, kw):
    assert c_rows(c_feeder(transformers, regcontrol(f"trans_{REG}", ptratio), **kw)) == []


def test_repair_c_after_the_source_voltage_moves():
    texts = c_feeder(REG_LINE + SERVICE_14434, regcontrol(f"trans_{REG}", 60.0),
                     vbases="[0.12, 0.208, 12.47, 14.434]")
    changes, defects = sr.check(texts, "f1")
    assert defects == []
    b = [c for c in changes if c["repair"] == "source_voltage_from_transformers"]
    today = sr.check(feeder(head="Line.l1", transformers=SERVICE_14434, vbases="[0.12, 0.208, 12.47, 14.434]"), "f1")[0]
    assert b == today
    rows = [c for c in changes if c["repair"] == C]
    assert [(c["file"], c["line"]) for c in rows] == [("Transformers.dss", 1), ("Regulators.dss", 1)]
    assert rows[0]["now"] == REG_LINE.replace("12.47, 12.47", "25.0, 25.0").strip()
    assert rows[1]["now"] == regcontrol(f"trans_{REG}", "120.28130608117205").strip()


def test_repair_c_single_phase_line_to_line():
    form = REG_1PH.replace("b2x.3,b2.3", "b2x.1.2,b2.1.2")
    texts = c_feeder(SERVICE_72 + form.format(kv=12.47), regcontrol("trans_reg_b", 60.0))
    rows = c_rows(texts)
    assert len(rows) == 1 and rows[0]["file"] == "Regulators.dss"
    assert rows[0]["now"] == regcontrol("trans_reg_b", repr(12.47 * 1000 / 120)).strip()


@pytest.mark.parametrize("transformer", [
    REG_1PH.replace("b2x.3,b2.3", "b2x.3,b2.1.2"),                   # one node and two nodes
    REG_1PH.replace("phases=1", "phases=2").replace("b2x.3,b2.3", "b2x.1.2,b2.1.2"),    # two phases
])
def test_repair_c_does_not_judge_other_shapes(transformer):
    texts = c_feeder(SERVICE_72 + transformer.format(kv=99.0), regcontrol("trans_reg_b", 1.0))
    assert sr.check(texts, "f1") == ([], [])
    assert sr.regulator_counts(sr.read_feeder(texts)) == (1, 0)


def test_repair_c_regcontrol_without_ptratio():
    texts = c_feeder(SERVICE_14434 + REG_1PH.format(kv=14.434), regcontrol("trans_reg_b", None), **V25)
    assert sr.check(texts, "f1") == ([], [])
    assert sr.regulator_counts(sr.read_feeder(texts)) == (0, 1)


ABC_TRANSFORMERS = (f"New Transformer.trans_{REG} phases=3 windings=2\n"
                    f"~ buses=(src.1.2.3,b1.1.2.3) kvs=(12.47, 12.47) kvas=(10000.0, 10000.0) ! the head\n"
                    + SERVICE_14434)
ABC_REGULATORS = (f"! regulators\nNew RegControl.reg_a transformer=TRANS_{REG.upper()} winding=2\n"
                  f"~ ptratio=60.0 band=2.4 vreg=123.6\n\nNew RegControl.other transformer=x winding=2 ptratio=60.0\n")


def abc_feeder(nl):
    texts = feeder(transformers=ABC_TRANSFORMERS, vbases="[0.12, 0.208, 12.47, 14.434]")
    texts["Regulators.dss"] = ABC_REGULATORS
    return {n: t.replace("\n", nl) for n, t in texts.items()}


@pytest.mark.parametrize("nl", ["\r\n", "\n"])
def test_repair_folder_writes_each_file_a_change_names(tmp_path, nl):
    folder = write(tmp_path / "f1", abc_feeder(nl))
    before = snapshot(folder)
    changes, defects = sr.repair_folder(folder, "f1")
    assert defects == []
    assert [(c["repair"][:6], c["file"], c["line"]) for c in changes] == [
        ("head_m", "Master.dss", 9), ("head_m", "Master.dss", 10), ("head_m", "Master.dss", 11),
        ("source", "Master.dss", 3), ("source", "Master.dss", 13),
        ("regula", "Transformers.dss", 1), ("regula", "Regulators.dss", 2)]
    assert changes[5]["numbers"] == [1, 2] and changes[6]["numbers"] == [2, 3]
    after = snapshot(folder)
    assert sorted(after) == sorted(before)
    assert after["Master.dss"] == master(f"Transformer.trans_{REG}", basekv="25.0",
                                         vbases="[0.12, 0.208, 14.434, 25.0]", nl=nl).encode()
    assert after["Transformers.dss"] == ABC_TRANSFORMERS.replace("12.47, 12.47", "25.0, 25.0").replace("\n", nl).encode()
    assert after["Regulators.dss"] == ABC_REGULATORS.replace("ptratio=60.0 band", "ptratio=120.28130608117205 band") \
        .replace("\n", nl).encode()
    assert all(after[n] == before[n] for n in before if n not in ("Master.dss", "Transformers.dss", "Regulators.dss"))
    # the repaired folder needs no more repair
    assert sr.check(sr.read_texts(folder), "f1") == ([], [])


def test_a_sound_feeder_with_regulators_is_not_written(tmp_path):
    texts = c_feeder(SERVICE_14434 + REG_1PH.format(kv=14.434), regcontrol("trans_reg_b", 120.28130608117205), **V25)
    folder = write(tmp_path / "f1", texts)
    before = snapshot(folder)
    stamp = {n: os.stat(os.path.join(folder, n)).st_mtime_ns for n in before}
    assert sr.repair_folder(folder, "f1") == ([], [])
    assert snapshot(folder) == before
    assert {n: os.stat(os.path.join(folder, n)).st_mtime_ns for n in before} == stamp


def test_the_table_of_repair_c(tmp_path):
    changes, _ = sr.check(abc_feeder("\n"), "f1")
    sr.write_table(tmp_path / "t.csv", changes)
    table = pd.read_csv(tmp_path / "t.csv", dtype=str)
    rows = table[table["repair"] == C]
    assert rows[["file", "line"]].values.tolist() == [["Transformers.dss", "1"], ["Regulators.dss", "2"]]
    assert rows["now"].tolist()[1] == (f"New RegControl.reg_a transformer=TRANS_{REG.upper()} winding=2 "
                                       f"ptratio=120.28130608117205 band=2.4 vreg=123.6")


@pytest.mark.parametrize("nl", ["\r\n", "\n"])
def test_repaired_texts_equal_what_repair_folder_writes(tmp_path, nl):
    texts = abc_feeder(nl)
    changes, _ = sr.check(texts, "f1")
    folder = write(tmp_path / "f1", texts)
    sr.repair_folder(folder, "f1")
    written = {n: Path(folder, n).read_bytes().decode("utf-8") for n in texts}
    assert sr.repaired_texts(texts, changes) == written


def test_pre_prints_repair_c(tmp_path):
    texts = c_feeder(SERVICE_14434 + REG_1PH.format(kv=14.434) + REG_1PH.replace("trans_reg_b", "trans_reg_c")
                     .replace("phases=1", "phases=2").format(kv=25.0),
                     regcontrol("trans_reg_b", 69.44465262857685) + regcontrol(f"trans_{REG}", None, name="reg_a"),
                     **V25)
    texts["Transformers.dss"] += REG_LINE.replace("12.47, 12.47", "25.0, 25.0")
    code, out = _pre(tmp_path, texts)
    assert code == 0
    assert [ln for ln in out if ln.startswith("[repair] f1: ")] == [
        f"[repair] f1: {C}: Regulators.dss line 1: {regcontrol('trans_reg_b', 69.44465262857685).strip()} -> "
        f"{regcontrol('trans_reg_b', '120.28130608117205').strip()}"]
    assert out[-1] == ("[repair] 1 feeders checked: 1 statements to repair on 1 feeders. 1 regulators of a shape "
                       f"{C} does not judge. 1 RegControls without ptratio, not checked.")


def test_pre_repairs_off_prints_one_line(tmp_path):
    code, out = _pre(tmp_path, feeder(transformers=SERVICE_72),
                     settings={"pipeline_config.yaml": "smartds_repairs: false\n"})
    assert code == 0 and len(out) == 1 and out[0].startswith("[repair] smartds_repairs is false")


# ---------------------------------------------------------------- the setting
def test_the_setting(tmp_path, monkeypatch):
    assert smartds_repairs_on({"smartds_repairs": True}) is True
    assert smartds_repairs_on({"smartds_repairs": False}) is False
    for bad in ({"smartds_repairs": "yes"}, {"smartds_repairs": None}, {}):
        with pytest.raises(SystemExit) as e:
            smartds_repairs_on(bad)
        assert e.value.code == 1
    monkeypatch.delenv(SETTINGS_ENV, raising=False)
    assert smartds_repairs_on(load_config()) is True                     # the tracked value
    write(tmp_path, {"pipeline_config.yaml": "smartds_repairs: false\n"})
    monkeypatch.setenv(SETTINGS_ENV, tmp_path.as_posix())
    assert smartds_repairs_on(load_config()) is False                    # a --settings folder turns it off
    write(tmp_path, {"pipeline_config.yaml": "ev_day: typical\n"})
    assert smartds_repairs_on(load_config()) is True                     # without the key: the tracked value


# ---------------------------------------------------------------- Phase 8, a regulator head
M1_LINE = ["hour", " t(sec)", " V1", " VAngle1", " V2", " VAngle2", " V3", " VAngle3",
           " I1", " IAngle1", " I2", " IAngle2", " I3", " IAngle3"]
M1_REG = ["hour", " t(sec)", " V1", " VAngle1", " V2", " VAngle2", " V3", " VAngle3", " V4", " VAngle4",
          " I1", " IAngle1", " I2", " IAngle2", " I3", " IAngle3", " I4", " IAngle4"]
M2_LINE = ["hour", " t(sec)", " S1 (kVA)", " Ang1", " S2 (kVA)", " Ang2", " S3 (kVA)", " Ang3"]
M2_REG = M2_LINE + [" S4 (kVA)", " Ang4"]


def _export(path, columns, steps=96, base=100.0):
    rows = []
    for k in range(steps):
        rows.append([f"{(k + 1) * 0.25}", f"{k * 900}"] + [f"{base + k + i * 7.5}" for i in range(len(columns) - 2)])
    if "S4 (kVA)" in " ".join(columns):
        for row in rows:
            row[columns.index(" S4 (kVA)")] = "0"
    Path(path).write_text(",".join(columns) + "\n" + "".join(",".join(r) + "\n" for r in rows), encoding="utf-8")


def _circuit(work, name, head, regulator):
    mcd = work / "7_circuit_instantiation" / name / "ModifiedCircuitData"
    write(mcd, feeder(head=head))
    circuit = "feeder_x"
    _export(mcd / f"{circuit}_Mon_m1_1.csv", M1_REG if regulator else M1_LINE)
    _export(mcd / f"{circuit}_Mon_m2_1.csv", M2_REG if regulator else M2_LINE)
    return mcd


def _aggregate(work):
    env = dict(os.environ, PIPELINE_WORK_ROOT=work.as_posix(), PYTHONIOENCODING="utf-8")
    env.pop(SETTINGS_ENV, None)
    p = subprocess.run([sys.executable, "aggregate_m1_m2_with_circuits.py"], cwd=os.path.join(REPO_ROOT, "8_results_analysis"),
                       env=env, capture_output=True, text=True, encoding="utf-8")
    assert p.returncode == 0, p.stdout + p.stderr
    root = work / "7_circuit_instantiation"
    return (pd.read_csv(root / "aggregate_m1.csv", low_memory=False), pd.read_csv(root / "aggregate_m2.csv", low_memory=False),
            pd.read_csv(root / "circuit_summary.csv"))


def test_phase8_regulator_head(tmp_path):
    line_mcd = _circuit(tmp_path / "w_line", "sub_circuit_1_baseline", "Line.l1", regulator=False)
    reg_mcd = _circuit(tmp_path / "w_reg", "sub_circuit_2_baseline", f"Transformer.trans_{REG}", regulator=True)
    # feeder_head_kva: the kVA of the regulator's first winding; a line head keeps its rule
    reg_files, line_files = sorted(reg_mcd.glob("*.dss")), sorted(line_mcd.glob("*.dss"))
    assert agg._feeder_head_kva(reg_files) == 10000.0
    assert agg._feeder_head_kva(line_files) == pytest.approx(325.0 * 12.47 * math.sqrt(3.0))
    assert agg._head_transformer(line_files) is None
    assert agg._head_transformer(reg_files) == {"name": f"trans_{REG}", "phases": 3, "kva": 10000.0}
    m1_line, m2_line, s_line = _aggregate(tmp_path / "w_line")
    m1_reg, m2_reg, s_reg = _aggregate(tmp_path / "w_reg")
    assert s_reg["feeder_head_kva"].tolist() == [10000.0]
    assert s_line["feeder_head_kva"].tolist() == [pytest.approx(325.0 * 12.47 * math.sqrt(3.0))]
    # the head columns of a regulator head equal those of a line head
    assert list(m1_reg.columns) == list(m1_line.columns)
    assert list(m2_reg.columns) == list(m2_line.columns)
    # the totals are the sums over the phase conductors of the raw export
    raw = pd.read_csv(reg_mcd / "feeder_x_Mon_m2_1.csv")
    data = m2_reg[m2_reg["row_type"] == "data"].reset_index(drop=True)
    p = sum(raw[f" S{i} (kVA)"] * pd.Series(raw[f" Ang{i}"]).map(lambda a: math.cos(math.radians(a)))
            for i in (1, 2, 3))
    assert data["P_3ph (kW)"].tolist() == pytest.approx(p.tolist())


# ---------------------------------------------------------------- Phase 8, a second head of network growth
COPY = "ng_express_2_reg"
REG_COPY = (f"New Transformer.{COPY} phases=3 windings=2 buses=(src.1.2.3,ng_bus.1.2.3) "
            f"kvs=(12.47, 12.47) kvas=(10000.0, 10000.0)\n")
EXPRESS = "New Line.ng_express_2 bus1=src.1.2.3 bus2=b2.1.2.3 phases=3 linecode=lc2 length=185 units=m\n"
EXPRESS_CODE = "New Linecode.lc2 nphases=3 r1=0.1 x1=0.2 units=km normamps=350.0\n"
HEADS = {"reg": (f"Transformer.trans_{REG}", True), "copy": (f"Transformer.{COPY}", True),
         "line": ("Line.l1", False), "express": ("Line.ng_express_2", False)}


def _grown(work, head1, head2):
    """A circuit folder after network growth with two heads (HEADS keys): Monitors m1 and m2
    on head1, h2m1 and h2m2 on head2, their exports (the fourth channels for a head on a
    regulator, other values on head 2), and the growth tables Phase 8 reads."""
    folder = work / "7_circuit_instantiation" / "sub_circuit_1_baseline"
    mcd = folder / "ModifiedCircuitData"
    texts = feeder(head=HEADS[head1][0], transformers=REG_LINE + REG_COPY + SERVICE_72)
    texts["Master.dss"] = texts["Master.dss"].replace(
        "new energymeter.m3", f"New Monitor.h2m1 element={HEADS[head2][0]} mode=0\n"
                              f"New Monitor.h2m2 element={HEADS[head2][0]} mode=1\nnew energymeter.m3")
    texts["Lines.dss"], texts["LineCodes.dss"] = LINES + EXPRESS, LINECODES + EXPRESS_CODE
    write(mcd, texts)
    for mon, head, base in (("", head1, 100.0), ("h2", head2, 40.0)):
        _export(mcd / f"feeder_x_Mon_{mon}m1_1.csv", M1_REG if HEADS[head][1] else M1_LINE, base=base)
        _export(mcd / f"feeder_x_Mon_{mon}m2_1.csv", M2_REG if HEADS[head][1] else M2_LINE, base=base)
    write(folder, {"scenario_assignments.json": "{}\n"})
    write(mcd, {"planning_limits.csv": "limit,setting,elements_checked,elements_over,worst_element,worst_value,"
                                       "worst_step,worst_date\nhead,100 percent,2,0,l1,50.0,1,2018-07-18\n",
                "network_growth_rounds.csv": "round,step,items,converged\n0,,0,1\n1,new_feeder,1,1\n",
                "network_growth.csv": "round,step,element,was,now,count_before,count,length_m,kva,peak,detail\n",
                "network_growth_built.yaml": "[]\n"})
    return mcd


def _aggregate_grown(work):
    settings = work / "settings"
    write(settings, {"growth.yaml": "growth_years: 10\nnetwork_growth:\n  steps: [new_feeder]\n"})
    env = dict(os.environ, PIPELINE_WORK_ROOT=work.as_posix(), PYTHONIOENCODING="utf-8",
               PIPELINE_SMART_DS_ROOT=settings.as_posix())
    env[SETTINGS_ENV] = settings.as_posix()
    p = subprocess.run([sys.executable, "aggregate_m1_m2_with_circuits.py"], cwd=os.path.join(REPO_ROOT, "8_results_analysis"),
                       env=env, capture_output=True, text=True, encoding="utf-8")
    root = work / "7_circuit_instantiation"
    assert p.returncode == 0 and not (root / "problem_circuits.txt").exists(), p.stdout + p.stderr
    return (pd.read_csv(root / "aggregate_m1.csv", low_memory=False), pd.read_csv(root / "aggregate_m2.csv", low_memory=False),
            pd.read_csv(root / "circuit_summary.csv"))


def _without_neutral(path, regulator):
    frame = pd.read_csv(path)
    return agg._drop_neutral_channels(frame, 3) if regulator else frame


def _check_rows(mcd, head1, head2, m1, m2):
    """The data rows equal head_totals of the two heads' exports without the neutral's
    channels; the head rows equal each head's own export without them."""
    for folder in ("7_circuit_instantiation", os.path.join("7_circuit_instantiation", "deployer_modules")):
        if os.path.join(REPO_ROOT, folder) not in sys.path:
            sys.path.append(os.path.join(REPO_ROOT, folder))
    import planning_limits
    own = {k: [_without_neutral(mcd / f"feeder_x_Mon_{mon}{m}_1.csv", HEADS[head][1]) for m in ("m1", "m2")]
           for k, mon, head in ((1, "", head1), (2, "h2", head2))}
    totals = planning_limits.head_totals([own[1][0], own[2][0]], [own[1][1], own[2][1]])
    for agg_frame, total, i in ((m1, totals[0], 0), (m2, totals[1], 1)):
        data = agg_frame[agg_frame["row_type"] == "data"].reset_index(drop=True)
        assert len(data) == 96
        for col in total.columns:
            assert data[col].tolist() == pytest.approx(total[col].astype(float).tolist(), rel=1e-12), col
        for k in (1, 2):
            rows = agg_frame[(agg_frame["row_type"] == "head") & (agg_frame["head"] == k)].reset_index(drop=True)
            assert len(rows) == 96
            for col in own[k][i].columns:
                assert rows[col].tolist() == pytest.approx(own[k][i][col].astype(float).tolist(), rel=1e-12), col


@pytest.mark.parametrize("head2, kva", [("copy", 10000.0 + 10000.0),
                                        ("express", 10000.0 + 350.0 * 12.47 * math.sqrt(3.0))])
def test_phase8_regulator_head_and_a_second_head(tmp_path, head2, kva):
    mcd = _grown(tmp_path / "w", "reg", head2)
    files = sorted(mcd.glob("*.dss"))
    # feeder_head_kva: the regulator's kVA plus the rating of the second head
    assert agg._feeder_head_kva(files) == pytest.approx(kva, rel=1e-12)
    m1, m2, summary = _aggregate_grown(tmp_path / "w")
    assert summary["feeder_head_kva"].tolist() == [pytest.approx(kva, rel=1e-12)]
    assert m1.loc[m1["row_type"] == "summary", "feeder_head_kva"].tolist() == [pytest.approx(kva, rel=1e-12)]
    # the columns of a circuit with two line heads: no channel of a neutral
    m1_lines, m2_lines, _ = _aggregate_grown(_grown(tmp_path / "w_lines", "line", "express").parents[2])
    assert list(m1.columns) == list(m1_lines.columns)
    assert list(m2.columns) == list(m2_lines.columns)
    assert not any(c.strip() in ("V4", "VAngle4", "I4", "IAngle4", "S4 (kVA)", "Ang4") for c in list(m1) + list(m2))
    _check_rows(mcd, "reg", head2, m1, m2)
    # the head of each Monitor: a copy of the regulator is a head on a transformer
    assert agg._head_transformer(files) == {"name": f"trans_{REG}", "phases": 3, "kva": 10000.0}
    assert agg._head_transformer(files, "h2m1") == ({"name": COPY, "phases": 3, "kva": 10000.0}
                                                    if head2 == "copy" else None)


def test_phase8_two_line_heads_keep_their_rule(tmp_path):
    mcd = _grown(tmp_path / "w", "line", "express")
    files = sorted(mcd.glob("*.dss"))
    kva = (325.0 + 350.0) * 12.47 * math.sqrt(3.0)
    assert agg._head_transformer(files) is None
    assert agg._feeder_head_kva(files) == pytest.approx(kva, rel=1e-12)
    m1, m2, summary = _aggregate_grown(tmp_path / "w")
    assert summary["feeder_head_kva"].tolist() == [pytest.approx(kva, rel=1e-12)]
    _check_rows(mcd, "line", "express", m1, m2)
