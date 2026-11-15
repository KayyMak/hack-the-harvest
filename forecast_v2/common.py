"""Shared loaders and the pre-registered candidate methods for forecast_v2 (see PREREGISTRATION.md).

Every function that builds a forecast for year t takes `finals` restricted to years < t and in-season values
for t only, so a backtest year never sees its own or a later final.
"""
import csv
import importlib.util
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
HARVESTED_CSV = ROOT / 'analysis' / 'forecast_backtest' / 'quickstats_corn_harvested_1990_2026.csv'
PLANTED_CSV = HERE / 'data' / 'quickstats_corn_planted_2005_2026.csv'
US = 'US TOTAL'
LAST_FINAL_YEAR = 2024   # 2025 YEAR is the answer key, 2026 YEAR is preliminary: never loaded

# latest first: the first period present for (state, t) is the one used
GRAIN_PERIODS = ['YEAR - NOV FORECAST', 'YEAR - OCT FORECAST', 'YEAR - SEP FORECAST', 'YEAR - AUG FORECAST',
                 'YEAR - JUN ACREAGE']
PLANTED_PERIODS = ['YEAR - OCT FORECAST', 'YEAR - OCT ACREAGE', 'YEAR - SEP FORECAST', 'YEAR - AUG FORECAST',
                   'YEAR - AUG ACREAGE', 'YEAR - JUN ACREAGE', 'YEAR - MAR ACREAGE']

SILAGE_METHODS = {
    'S1': 'D (baseline): forecast/estimate_2025.py method D, 3 prior years',
    'S2': 'PERSIST: silage_{t-1}',
    'S3': 'PLANTSCALE: silage_{t-1} x planted_t / planted_{t-1}',
    'S4': 'RATIO3: median_{t-3..t-1}(silage/grain) x grain_t',
    'S5': 'BLEND_PD: (S1 + S2) / 2',
    'S6': 'BLEND_PR: (S2 + S4) / 2',
}
SIMPLICITY = ['S2', 'S3', 'S4', 'S1', 'S6', 'S5']
GRAIN_METHODS = {
    'G1': 'NASS: latest pre-January NASS grain forecast as is',
    'G2': 'NASS_BC: G1 x median(final / same-period forecast) over the state\'s years 2012..t-1 (>= 3 years, else G1)',
}


def num(v):
    v = (v or '').replace(',', '').strip()
    try:
        return float(v)
    except ValueError:
        return None   # blank, (D), (NA), (Z): unknown, never zero


def _rows(path):
    with open(path, encoding='utf-8-sig', newline='') as f:
        yield from csv.DictReader(f)


def load_quickstats():
    """finals[(state, year)] = {'grain', 'silage', 'planted'} for years <= 2024;
    inseason[(state, year)] = {'grain': {period: v}, 'planted': {period: v}} for pre-January periods."""
    finals, inseason = {}, {}
    for path, item_of in ((HARVESTED_CSV, lambda r: 'silage' if 'SILAGE' in r['Data Item'] else 'grain'),
                          (PLANTED_CSV, lambda r: 'planted')):
        for r in _rows(path):
            y = int(r['Year'])
            if y >= 2026:
                continue
            item = item_of(r)
            st = r['State']
            v = num(r['Value'])
            if r['Period'] == 'YEAR':
                if y > LAST_FINAL_YEAR:
                    continue   # 2025 final = answer key (the committed files hold none; guard anyway)
                finals.setdefault((st, y), {'grain': None, 'silage': None, 'planted': None})[item] = v
            elif v is not None and item != 'silage':   # NASS publishes no in-season silage area
                inseason.setdefault((st, y), {'grain': {}, 'planted': {}})[item][r['Period']] = v
    return finals, inseason


def latest(inseason, st, t, item):
    """(value, period) of the latest pre-January estimate of `item` for state st, year t."""
    d = inseason.get((st, t), {}).get(item, {})
    for p in (GRAIN_PERIODS if item == 'grain' else PLANTED_PERIODS):
        if d.get(p) is not None:
            return d[p], p
    return None, None


def prior(finals, t):
    """Finals restricted to years before t: the only history a forecast for t may see."""
    return {k: v for k, v in finals.items() if k[1] < t}


# ---------------------------------------------------------------- baseline D, imported (never run main())
def _load_fc1():
    spec = importlib.util.spec_from_file_location('fc1_estimate_2025', ROOT / 'forecast' / 'estimate_2025.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


FC1 = _load_fc1()


# ---------------------------------------------------------------- silage candidates
def silage_candidates(st, t, hist, planted_t, grain_t):
    """All six candidates for state st, year t. `hist` holds finals for years < t only.
    Returns {method: value}; a candidate that cannot be computed takes S2's value."""
    for (s, y) in hist:
        if y >= t:
            raise AssertionError(f'history for {t} contains {y}')
    prev = hist.get((st, t - 1), {})
    s_prev = prev.get('silage')
    if s_prev is None:
        return None
    out = {'S2': s_prev}
    # S1: method D exactly as forecast/estimate_2025.py computes it (fed finals as its history)
    h1 = {k: v for k, v in hist.items() if k[0] == st and k[1] in (t - 3, t - 2, t - 1)}
    e = FC1.estimate_state(st, planted_t, grain_t, h1, [t - 3, t - 2, t - 1], 0.0, 'D', t) if planted_t else None
    out['S1'] = e['silage'] if e else s_prev
    # S3
    out['S3'] = s_prev * planted_t / prev['planted'] if planted_t and prev.get('planted') else s_prev
    # S4
    ratios = [hist[(st, y)]['silage'] / hist[(st, y)]['grain'] for y in (t - 3, t - 2, t - 1)
              if hist.get((st, y), {}).get('silage') is not None and hist.get((st, y), {}).get('grain')]
    out['S4'] = statistics.median(ratios) * grain_t if ratios and grain_t else s_prev
    out['S5'] = (out['S1'] + out['S2']) / 2
    out['S6'] = (out['S2'] + out['S4']) / 2
    return out


# ---------------------------------------------------------------- grain candidates
def grain_candidates(st, t, hist, inseason):
    """{'G1', 'G2', 'period'} for state st, year t (or None without an in-season forecast)."""
    g, period = latest(inseason, st, t, 'grain')
    if g is None:
        return None
    ratios = []
    for y in range(2012, t):
        f = inseason.get((st, y), {}).get('grain', {}).get(period)
        fin = hist.get((st, y), {}).get('grain')
        if f and fin:
            ratios.append(fin / f)
    g2 = g * statistics.median(ratios) if len(ratios) >= 3 else g
    return {'G1': g, 'G2': g2, 'period': period, 'n_ratios': len(ratios)}
