"""Experiment only: pull Sentinel-2 series for the 2017-2020 extra-label field-years.

    python baseline/experiments/extra_labels/extract_extra.py 2019

Same recipe as run_baseline.extract (Planetary Computer sentinel-2-l2a, Jul 1-Nov 30, scene
cloud < 40 %, SCL mask, STAC/processing-baseline reflectance offset, centre-inside-polygon
pixels). Polygons are the 2021-2023 BARC GeoPackage polygons for the same OBJECTID (field
boundaries are assumed unchanged in earlier years). Writes only baseline/cache_extra/.
Failed scene reads are retried up to 3 times (unlabeled_calls.retry_read_errors); scenes that
still fail stay read_error records and are reported, never filled.
"""
import json
from pathlib import Path
import sys

import geopandas as gpd
import pandas as pd

HERE = Path(__file__).resolve().parent
BASELINE = HERE.parents[1]
ROOT = BASELINE.parent
sys.path.insert(0, str(BASELINE))
import run_baseline as rb  # noqa: E402
import unlabeled_calls as uc  # noqa: E402

CACHE = BASELINE / 'cache_extra'
LABELS = ROOT / 'data' / 'extra_labels' / 'labels_combined.csv'
YEARS = (2017, 2018, 2019, 2020)


def extra_jobs(years):
    lab = pd.read_csv(LABELS)
    lab = lab[(lab.split == 'train_extra') & lab.year.isin(years) & lab.use_for_training]
    fields = gpd.read_file(rb.SOURCE, layer=rb.LAYER).set_index('OBJECTID')
    rows = [dict(OBJECTID=int(r.OBJECTID), year=int(r.year), label=r.label,
                 geometry=fields.loc[int(r.OBJECTID), 'geometry']) for r in lab.itertuples()]
    jobs = gpd.GeoDataFrame(rows, geometry='geometry', crs=fields.crs).to_crs(4326)
    return jobs.sort_values(['year', 'OBJECTID']).reset_index(drop=True)


def main(years):
    rb.CACHE = CACHE  # run_baseline.cache_path reads this global at call time
    uc.CACHE = CACHE  # retry_read_errors reads the saved catalog from here
    jobs = extra_jobs(years)
    print(f'{len(jobs)} field-years: {sorted(zip(jobs.OBJECTID, jobs.year))}', flush=True)
    rb.extract(jobs)
    failing = uc.retry_read_errors(jobs, waits=(5, 20, 45))
    out = []
    for row in jobs.itertuples():
        s = rb.summarize(row, rb.load_cache(row))
        out.append(dict(OBJECTID=s['OBJECTID'], year=s['year'], valid_dates=s['valid_dates'],
                        read_errors=s['read_errors'], scenes=s['scene_observations']))
    print(json.dumps(dict(summary=out, still_failing=failing), indent=1), flush=True)


if __name__ == '__main__':
    main(tuple(int(a) for a in sys.argv[1:]) or YEARS)
