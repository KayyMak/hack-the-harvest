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


# What was known as of each 2025 release date (PREREGISTRATION.md, amendment 1); NOV = everything pre-January.
RELEASES = ['JUN', 'AUG', 'SEP', 'NOV']
ASOF_PERIODS = {
    'grain': {'JUN': GRAIN_PERIODS[4:], 'AUG': GRAIN_PERIODS[3:], 'SEP': GRAIN_PERIODS[2:], 'NOV': GRAIN_PERIODS},
    'planted': {'JUN': ['YEAR - JUN ACREAGE', 'YEAR - MAR ACREAGE'],
                'AUG': ['YEAR - AUG FORECAST', 'YEAR - AUG ACREAGE', 'YEAR - JUN ACREAGE', 'YEAR - MAR ACREAGE'],
                'SEP': ['YEAR - SEP FORECAST', 'YEAR - AUG FORECAST', 'YEAR - AUG ACREAGE', 'YEAR - JUN ACREAGE',
                        'YEAR - MAR ACREAGE'],
                'NOV': PLANTED_PERIODS},
}


def latest(inseason, st, t, item, release='NOV'):
    """(value, period) of the latest estimate of `item` for state st, year t known as of `release`
    (NOV = the latest pre-January estimate)."""
    d = inseason.get((st, t), {}).get(item, {})
    for p in ASOF_PERIODS[item][release]:
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
    # round 2 (PREREGISTRATION.md "Round 2"): S5 with D's shares estimated differently
    for m, (k, agg, shrink) in ROUND2.items():
        d = d_prime(st, t, hist, planted_t, grain_t, k, agg, shrink)
        out[m] = ((d if d is not None else s_prev) + s_prev) / 2
    out.update(round3_silage(st, t, hist, planted_t, grain_t))   # PREREGISTRATION_ROUND3.md
    return out


# ---------------------------------------------------------------- round 3 (PREREGISTRATION_ROUND3.md)
ROUND3_METHODS = {
    'T1': 'RESID5: (planted_t - grain_t) x 5-year median of min(1, silage / (planted - grain)); silage-only states: planted_t x 5-year median(silage / planted)',
    'T2': 'DAMP50: silage_{t-1} x (1 + 0.5 x (planted_t / planted_{t-1} - 1))',
    'T3': 'RATIO5: grain_t x 5-year median(silage / grain)',
}
ROUND3_SIMPLICITY = ['T2', 'T3', 'T1']
ROUND3_GRAIN = {'GB5': 'NASS_BC5: G1 x 5-year median(final / same-period forecast), >= 3 years else G1'}


def round3_silage(st, t, hist, planted_t, grain_t):
    """T1-T3 for state st, year t from finals before t (5-year windows t-5..t-1); fallback silage_{t-1}."""
    prev = hist.get((st, t - 1), {})
    s_prev = prev['silage']
    years = range(t - 5, t)
    out = {'T1': s_prev, 'T2': s_prev, 'T3': s_prev}
    a, _ = yearly_shares(hist, st, years)
    if a and planted_t:
        share = statistics.median(x[1] for x in a)
        if 'planted' in {x[0] for x in a}:
            out['T1'] = share * planted_t
        elif grain_t is not None and planted_t - grain_t > 0:
            out['T1'] = share * (planted_t - grain_t)
    if planted_t and prev.get('planted'):
        out['T2'] = s_prev * (1 + 0.5 * (planted_t / prev['planted'] - 1))
    ratios = [hist[(st, y)]['silage'] / hist[(st, y)]['grain'] for y in years
              if hist.get((st, y), {}).get('silage') is not None and hist.get((st, y), {}).get('grain')]
    if ratios and grain_t:
        out['T3'] = statistics.median(ratios) * grain_t
    return out


def grain_bc5(g, period, st, t, hist, inseason):
    """GB5: g x median over y in t-5..t-1 of final_y / forecast_y (same period), >= 3 years else g."""
    ratios = []
    for y in range(t - 5, t):
        f = inseason.get((st, y), {}).get('grain', {}).get(period)
        fin = hist.get((st, y), {}).get('grain')
        if f and fin:
            ratios.append(fin / f)
    return g * statistics.median(ratios) if len(ratios) >= 3 else g


# ---------------------------------------------------------------- round 2: method D with other share estimates
ROUND2 = {'R1': (3, 'mean', True), 'R2': (5, 'median', False), 'R3': (5, 'mean', True)}
ROUND2_METHODS = {
    'R1': 'SHRINK3: (D\' + PERSIST) / 2, D\' shares = 3-year means shrunk toward the USDA farm production region (empirical Bayes)',
    'R2': 'MED5: (D\' + PERSIST) / 2, D\' shares = 5-year medians',
    'R3': 'SHRINK5: (D\' + PERSIST) / 2, D\' shares = 5-year means shrunk toward the region (empirical Bayes)',
}
ROUND2_SIMPLICITY = ['R2', 'R1', 'R3']
REGIONS = {
    'Northeast': 'MAINE NEW HAMPSHIRE VERMONT MASSACHUSETTS RHODE ISLAND CONNECTICUT NEW YORK NEW JERSEY PENNSYLVANIA DELAWARE MARYLAND',
    'Lake States': 'MICHIGAN WISCONSIN MINNESOTA',
    'Corn Belt': 'OHIO INDIANA ILLINOIS IOWA MISSOURI',
    'Northern Plains': 'NORTH DAKOTA SOUTH DAKOTA NEBRASKA KANSAS',
    'Appalachian': 'VIRGINIA WEST VIRGINIA NORTH CAROLINA KENTUCKY TENNESSEE',
    'Southeast': 'SOUTH CAROLINA GEORGIA FLORIDA ALABAMA',
    'Delta': 'MISSISSIPPI ARKANSAS LOUISIANA',
    'Southern Plains': 'OKLAHOMA TEXAS',
    'Mountain': 'MONTANA IDAHO WYOMING COLORADO NEW MEXICO ARIZONA UTAH NEVADA',
    'Pacific': 'WASHINGTON OREGON CALIFORNIA ALASKA HAWAII',
}
_TWO_WORD = ('NEW ', 'RHODE ', 'NORTH ', 'SOUTH ', 'WEST ')


def _split_states(text):
    out, words = [], text.split()
    i = 0
    while i < len(words):
        if any((words[i] + ' ').startswith(p) for p in _TWO_WORD) and i + 1 < len(words):
            out.append(words[i] + ' ' + words[i + 1])
            i += 2
        else:
            out.append(words[i])
            i += 1
    return out


REGION_OF = {st: r for r, txt in REGIONS.items() for st in _split_states(txt)}


def yearly_shares(hist, st, years):
    """Method D's per-year shares, defined as in forecast/estimate_2025.py: A = (kind, silage/(planted-grain)
    capped at 1, or silage/planted when there is no grain area), C = silage/planted."""
    a, c = [], []
    for y in years:
        h = hist.get((st, y))
        if not h or h.get('silage') is None or not h.get('planted'):
            continue
        resid = h['planted'] - (h['grain'] or 0)
        if h['grain'] is None:
            a.append(('planted', h['silage'] / h['planted']))
        elif resid > 0:
            a.append(('residual', min(1.0, h['silage'] / resid)))
        c.append(h['silage'] / h['planted'])
    return a, c


def _agg(vals, how):
    return statistics.median(vals) if how == 'median' else statistics.mean(vals)


def _shrunk(m, vals, pool):
    """Empirical-Bayes shrinkage of a state's mean share m toward the pool's mean (PREREGISTRATION.md round 2)."""
    if len(vals) < 2 or len(pool) < 3:
        return m
    v = statistics.variance(vals) / len(vals)
    tau2 = statistics.variance(pool)
    if v == 0 or tau2 == 0:
        return m
    w = tau2 / (tau2 + v)
    return w * m + (1 - w) * statistics.mean(pool)


def d_prime(st, t, hist, planted_t, grain_t, k, how, shrink):
    """Method D with shares over t-k..t-1 aggregated by `how`, optionally shrunk toward the region."""
    years = list(range(t - k, t))
    a, c = yearly_shares(hist, st, years)
    if planted_t is None or not a:
        return None
    kinds = {x[0] for x in a}
    a_vals = [x[1] for x in a]
    a_share, c_share = _agg(a_vals, how), (_agg(c, how) if c else None)
    if shrink:
        kind = 'planted' if 'planted' in kinds else 'residual'
        region = REGION_OF.get(st)
        pool_a, pool_c = {}, {}   # region -> list of other states' window means (state itself included)
        for s in {s for (s, y) in hist if y in years}:
            sa, sc = yearly_shares(hist, s, years)
            if len(sa) >= 2 and ('planted' if any(x[0] == 'planted' for x in sa) else 'residual') == kind:
                pool_a.setdefault(REGION_OF.get(s) if kind == 'residual' else 'ALL', []).append(statistics.mean(x[1] for x in sa))
            if len(sc) >= 2:
                pool_c.setdefault(REGION_OF.get(s), []).append(statistics.mean(sc))
        all_a = [x for v in pool_a.values() for x in v]
        all_c = [x for v in pool_c.values() for x in v]
        pa = pool_a.get(region if kind == 'residual' else 'ALL', [])
        pc = pool_c.get(region, [])
        a_share = _shrunk(a_share, a_vals, pa if len(pa) >= 3 else all_a)
        if c:
            c_share = _shrunk(c_share, c, pc if len(pc) >= 3 else all_c)
    if grain_t is None or 'planted' in kinds:
        a_est = a_share * planted_t
    else:
        a_est = a_share * max(0.0, planted_t - grain_t)
    return (a_est + c_share * planted_t) / 2 if c else a_est


# ---------------------------------------------------------------- grain candidates
def grain_candidates(st, t, hist, inseason, release='NOV'):
    """{'G1', 'G2', 'period'} for state st, year t (or None without an in-season forecast)."""
    g, period = latest(inseason, st, t, 'grain', release)
    if g is None:
        return None
    ratios = []
    for y in range(2012, t):
        f = inseason.get((st, y), {}).get('grain', {}).get(period)
        fin = hist.get((st, y), {}).get('grain')
        if f and fin:
            ratios.append(fin / f)
    g2 = g * statistics.median(ratios) if len(ratios) >= 3 else g
    return {'G1': g, 'G2': g2, 'GB5': grain_bc5(g, period, st, t, hist, inseason), 'period': period,
            'n_ratios': len(ratios)}
