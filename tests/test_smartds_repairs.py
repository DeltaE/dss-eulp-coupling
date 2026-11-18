# -*- coding: utf-8 -*-
"""
Tests of smartds_repairs.py (the repairs of two defects of the SMART-DS release) on small
made-up feeders written by the test: the detection rules, the changes, the bytes the apply
function keeps, the phase pre command and its stops, and the setting smartds_repairs. Also
the Phase 8 head of a regulator (8_results_analysis/aggregate_m1_m2_with_circuits.py):
feeder_head_kva and the head columns. No OpenDSS and no SMART-DS data.

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
    lines = sr.fail_lines("f1", changes, defects, growth=False)
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
    assert sr.check(feeder(head="Line.l1", transformers=transformers, basekv=basekv), "f1") == ([], [])


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
    assert [c["line"] for c in changes] == [9, 10, 11, 3, 13]
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


def test_pre_growth_on_stops_a_feeder_that_needs_a_repair(tmp_path):
    code, out = _pre(tmp_path, feeder(), settings={"growth.yaml": "growth_years: 5\n"})
    assert code == 1
    assert ("[FAIL] f1: needs the repair head_meters_on_regulator, and repairs run with growth off only "
            "(growth_years above 0 in growth.yaml).") in out
    code, out = _pre(tmp_path / "sound", feeder(head="Line.l1"), settings={"growth.yaml": "growth_years: 5\n"})
    assert code == 0


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


def _export(path, columns, steps=96):
    rows = []
    for k in range(steps):
        rows.append([f"{(k + 1) * 0.25}", f"{k * 900}"] + [f"{100.0 + k + i * 7.5}" for i in range(len(columns) - 2)])
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
