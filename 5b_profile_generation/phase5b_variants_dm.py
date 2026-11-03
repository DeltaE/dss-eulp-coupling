from pathlib import Path
import runpy
import sys

IMPL = Path(__file__).with_name("find_max_day_curve_impl.py")
sys.argv = [str(IMPL), "--scenario", "dm"]
runpy.run_path(str(IMPL), run_name="__main__")
