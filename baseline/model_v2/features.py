"""Feature functions for the model-v2 experiment. Reads only committed baseline outputs.

Every feature is computed from one field-year's own accepted observations, so no
information crosses field-years (and therefore no information crosses folds).

Series: per-date median NDVI over observations with status "ok" (duplicate processing
versions of a scene count once), sorted by date -- the same as run_baseline.daily_series.
Smoothed: centered 3-date rolling median, the same as decline_rule_baseline.smooth.

Timing features (constants fixed before any score was computed):
  decline_doy  first date after the smoothed peak where smoothed NDVI is at least
               DECLINE_DROP (0.25) below the peak and still that low at the next clear
               date (a low final date counts) -- decline_rule_baseline.decline_doy.
               No sustained decline in the season -> NO_DECLINE_DOY (335, Dec 1): the
               crop was still standing at season end, i.e. censored late, not unknown.
  drop_doy     day of year of the later date of the largest decrease between two
               consecutive smoothed values. NaN with fewer than 2 dates or no decrease.
  drop_size    size of that decrease (positive). NaN when drop_doy is NaN.
  regrowth     with m = the minimum smoothed value on or after the smoothed peak,
               max(smoothed after m) - smoothed[m]; 0 when m is the last date.
               NaN with no dates.
"""
import csv
from datetime import date
from pathlib import Path
import statistics

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
BASELINE_OUT = HERE.parent / 'outputs'
DECLINE_DROP = 0.25
NO_DECLINE_DOY = 335.0
MONTHS = [7, 8, 9, 10, 11]
BASE_FEATURES = [f'ndvi_{m:02d}' for m in MONTHS] + [
    'peak_ndvi', 'peak_doy', 'late_ndvi', 'early_minus_late']
TIMING_FEATURES = ['decline_doy', 'drop_doy', 'drop_size', 'regrowth']


def doy(day):
    return float(date.fromisoformat(day).timetuple().tm_yday)


def daily_series(observations, last_month=None):
    """[(iso date, median NDVI)] over accepted observations, optionally up to last_month."""
    by_date = {}
    for row in observations:
        if row['status'] != 'ok' or row['ndvi'] in ('', None):
            continue
        if last_month is not None and int(row['date'][5:7]) > last_month:
            continue
        by_date.setdefault(row['date'], []).append(float(row['ndvi']))
    return [(day, statistics.median(v)) for day, v in sorted(by_date.items())]


def smooth(values):
    return [statistics.median(values[max(0, i - 1):i + 2]) for i in range(len(values))]


def base_features(series):
    """The baseline's nine features (run_baseline.summarize) from a daily series."""
    f = {name: np.nan for name in BASE_FEATURES}
    if not series:
        return f
    s = pd.Series([v for _, v in series], index=pd.to_datetime([d for d, _ in series]))
    for m in MONTHS:
        f[f'ndvi_{m:02d}'] = s[s.index.month == m].median()
    early = s[s.index.month <= 8].median()
    late = s[s.index.month >= 10].median()
    f.update(peak_ndvi=s.max(), peak_doy=float(s.idxmax().day_of_year),
             late_ndvi=s[s.index.month >= 9].median(), early_minus_late=early - late)
    return f


def timing_features(series):
    f = {name: np.nan for name in TIMING_FEATURES}
    if not series:
        return f
    days = [d for d, _ in series]
    values = smooth([v for _, v in series])
    peak = max(range(len(values)), key=lambda i: values[i])
    f['decline_doy'] = NO_DECLINE_DOY
    for i in range(peak + 1, len(values)):
        low = values[i] <= values[peak] - DECLINE_DROP
        if low and (i == len(values) - 1 or values[i + 1] <= values[peak] - DECLINE_DROP):
            f['decline_doy'] = doy(days[i])
            break
    diffs = [values[i] - values[i + 1] for i in range(len(values) - 1)]
    if diffs and max(diffs) > 0:
        j = max(range(len(diffs)), key=lambda i: diffs[i])
        f['drop_doy'], f['drop_size'] = doy(days[j + 1]), float(diffs[j])
    m = min(range(peak, len(values)), key=lambda i: values[i])
    f['regrowth'] = float(max(values[m + 1:]) - values[m]) if m < len(values) - 1 else 0.0
    return f


def load_observations(path=BASELINE_OUT / 'observations.csv'):
    observations = {}
    with Path(path).open(encoding='utf-8', newline='') as file:
        for r in csv.DictReader(file):
            observations.setdefault((int(r['OBJECTID']), int(r['year'])), []).append(r)
    return observations


def build_table(features_csv=BASELINE_OUT / 'features.csv', observations=None):
    """Labeled field-years in the baseline's row order with baseline, Jul-Oct, and timing features.

    Jul-Oct columns carry the suffix `_juloct`: the nine baseline features recomputed from
    observations truncated at Oct 31 (ndvi_11_juloct is therefore all NaN and not used).
    """
    observations = load_observations() if observations is None else observations
    base = pd.read_csv(features_csv)
    base = base[base.valid_dates > 0].reset_index(drop=True)  # same filter as run_baseline.evaluate
    rows = []
    for r in base.itertuples():
        obs = observations.get((int(r.OBJECTID), int(r.year)), [])
        full = daily_series(obs)
        rec = dict(OBJECTID=int(r.OBJECTID), year=int(r.year), label=r.label)
        rec.update(base_features(full))
        rec.update({f'{k}_juloct': v for k, v in base_features(daily_series(obs, last_month=10)).items()})
        rec.update(timing_features(full))
        rows.append(rec)
    return pd.DataFrame(rows), base
