from pathlib import Path
import runpy


runpy.run_path(str(Path(__file__).with_name("clean_up_bldgs_NC.py")), run_name="__main__")
