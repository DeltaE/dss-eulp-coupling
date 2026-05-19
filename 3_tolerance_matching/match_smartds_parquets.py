from pathlib import Path
import runpy


runpy.run_path(str(Path(__file__).with_name("match_smartds_parquets_NC.py")), run_name="__main__")
