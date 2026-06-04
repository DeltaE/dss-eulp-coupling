from pathlib import Path
import runpy


runpy.run_path(str(Path(__file__).with_name("find_max_day_curve_NC_dm.py")), run_name="__main__")
