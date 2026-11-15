"""Shared paths and constants for the Maryland 2025 estimate.

Raw inputs live under data/raw/ (ignored by Git). Small, reproducible outputs live
under baseline/outputs/estimate_2025/.
"""
from pathlib import Path
import json
import sys

HERE = Path(__file__).resolve().parent
BASELINE = HERE.parent
ROOT = BASELINE.parent
if str(BASELINE) not in sys.path:
    sys.path.insert(0, str(BASELINE))

RAW = ROOT / 'data' / 'raw'
CSB_MD = RAW / 'csb_maryland.parquet'
CDL_MD = RAW / 'CDL_2025_24.tif'
SCENE_CACHE = RAW / 'estimate_2025_cache'
OUT = BASELINE / 'outputs' / 'estimate_2025'

YEAR = 2025
STATE = 'MARYLAND'
SEED = 42
SAMPLE_SIZE = 1500
BATCH_SIZE = 250
CORN_CODE = 1                 # Cropland Data Layer class 1 = Corn
MIN_CORN_SHARE = 0.5          # a field is 2025 corn when at least half its CDL pixels are corn
MIN_VALID_DATES = 3           # the baseline pilot gate: fewer clear dates is "too few clear looks"
ACRE_M2 = 4046.8564224

CSB_URL = 'https://data.source.coop/fiboa/us-usda-cropland/us_usda_cropland.parquet'
CDL_URL = 'https://nassgeodata.gmu.edu/webservice/nass_data_cache/byfips/CDL_2025_24.tif'


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(obj, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    tmp.replace(path)
