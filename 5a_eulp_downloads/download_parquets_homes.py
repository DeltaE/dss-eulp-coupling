from pathlib import Path
import runpy


runpy.run_path(str(Path(__file__).with_name("download_parquets_homes_NC.py")), run_name="__main__")
