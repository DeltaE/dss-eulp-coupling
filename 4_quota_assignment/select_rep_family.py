from pathlib import Path
import runpy


runpy.run_path(str(Path(__file__).with_name("select_rep_family_NC.py")), run_name="__main__")
