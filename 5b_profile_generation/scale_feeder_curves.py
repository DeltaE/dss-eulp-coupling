from pathlib import Path
import runpy


runpy.run_path(str(Path(__file__).with_name("scale_feeder_curves_NC.py")), run_name="__main__")
