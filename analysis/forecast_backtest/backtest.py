#!/usr/bin/env python3
"""
A longer backtest for the team's 2025 state forecast (forecast/estimate_2025.py), from one
committed USDA NASS Quick Stats export of corn acres harvested (grain + silage, state + US).

What it measures (reads ONLY quickstats_corn_harvested_1990_2026.csv next to this file):
  1. Grain: relative revision (final - forecast) / forecast for every state-year 2012-2024 that has
     an in-season NASS forecast and a final, by forecast month (Jun Acreage, Aug, Sep, Oct, Nov
     Crop Production). Compared with the forecast's grain_revision_rel_sd and its grain interval.
  2. Silage: two naive baselines, persistence and the 3-year mean, 2000-2024, each target year
     using only earlier years' finals. Context for the forecast's method-D backtest, not a
     head-to-head (different years, different finals source, no planted acres here).
  3. Maryland: grain forecasts vs final and silage finals, 2012-2024.

The export has no 2025 rows (2025 is the graded year) and its 2026 "YEAR" rows equal the
November 2026 forecast, so only 1990-2024 "YEAR" rows count as finals. Planted acres are not
in the export, so method D itself cannot be re-run here.

    python analysis/forecast_backtest/backtest.py
Writes outputs/backtest.json and outputs/tables.md (deterministic: no timestamps).
"""
import hashlib
import json
import math
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
CSV = HERE / 'quickstats_corn_harvested_1990_2026.csv'
CSV_SHA256 = '88a894586ecfba4bb6816e884eda87e1a97dcbf54ff03a777961b7d15dfaebe4'
OUT = HERE / 'outputs'

GRAIN = 'CORN, GRAIN - ACRES HARVESTED'
SILAGE = 'CORN, SILAGE - ACRES HARVESTED'
LAST_FINAL_YEAR = 2024          # 2025 is the graded year (absent); 2026 'YEAR' is preliminary
GRAIN_YEARS = range(2012, LAST_FINAL_YEAR + 1)
SILAGE_YEARS = range(2000, LAST_FINAL_YEAR + 1)
MONTHS = [('jun', 'YEAR - JUN ACREAGE'), ('aug', 'YEAR - AUG FORECAST'), ('sep', 'YEAR - SEP FORECAST'),
          ('oct', 'YEAR - OCT FORECAST'), ('nov', 'YEAR - NOV FORECAST')]

# Copied from forecast/outputs/summary.json (commit 11b0782, method D); this script does not read forecast/.
FORECAST = dict(
    grain_revision_rel_sd=0.0448,   # RMS of (final - Nov)/Nov, 2023-2024, finals from the Jan 2025 Annual Summary
    interval_z_grain=2.06,          # grain 95% interval = grain x (1 +/- 2.06 x 0.0448), about +/-9.2%
    silage_backtest=dict(years='2023-2024', state_years=96, median_abs_pct_error=11.5, mean_abs_pct_error=15.8,
                         acre_weighted_abs_pct_error=dict(D=10.49, B_persistence_scaled_by_planted=14.07)),
    grain_backtest=dict(state_years=82, median_abs_pct_error=0.5, mean_abs_pct_error=2.0, covered_by_95_interval=0.951),
)


def r(x, nd=4):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), nd)


def load(path=CSV):
    """Every row of the export, with numeric acres. Raises if the file changed or holds 2025."""
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != CSV_SHA256:
        raise RuntimeError(f'{path.name}: sha256 {digest} != recorded {CSV_SHA256}')
    d = pd.read_csv(path, dtype=str, keep_default_na=False)
    d['Year'] = d['Year'].astype(int)
    if (d['Year'] == 2025).any():
        raise RuntimeError('the export holds 2025 rows; 2025 is the graded year and must not be used')
    bad = ~d['Value'].str.fullmatch(r'[\d,]+')
    if bad.any():  # (D), (NA), (Z) would be unknown, never zero; this export has none
        raise RuntimeError(f'non-numeric values: {sorted(d.loc[bad, "Value"].unique())}')
    d['acres'] = d['Value'].str.replace(',', '').astype(float)
    return d


def finals(d, item):
    """Final ('YEAR') values through 2024 as a State x Year table. 2026 'YEAR' (= Nov forecast) is dropped."""
    f = d[(d['Data Item'] == item) & (d['Period'] == 'YEAR') & (d['Year'] <= LAST_FINAL_YEAR)]
    return f.pivot(index='State', columns='Year', values='acres')


def grain_panel(d):
    """One row per (State, Year) 2012-2024 with final and each month's forecast. 'OTHER STATES' (an
    aggregate whose final is printed as 0) is dropped; US TOTAL is kept but flagged."""
    g = d[(d['Data Item'] == GRAIN) & (d['Year'].isin(GRAIN_YEARS)) & (d['State'] != 'OTHER STATES')]
    p = g.pivot_table(index=['State', 'Year'], columns='Period', values='acres', aggfunc='first')
    p = p.rename(columns={'YEAR': 'final', **{per: m for m, per in MONTHS}})
    for m, _ in MONTHS:
        if m not in p:
            p[m] = float('nan')
    p = p[p['final'].notna()].reset_index()
    p['latest'] = p['nov']
    p['latest_month'] = p['nov'].notna().map({True: 'nov', False: None})
    for m in ('oct', 'sep', 'aug', 'jun'):
        fill = p['latest'].isna() & p[m].notna()
        p.loc[fill, 'latest'] = p.loc[fill, m]
        p.loc[fill, 'latest_month'] = m
    for m in [m for m, _ in MONTHS] + ['latest']:
        ok = p[m] > 0
        p[f'rev_{m}'] = ((p['final'] - p[m]) / p[m]).where(ok)
    return p


def rev_stats(rev, base=None, final=None):
    """Summary of relative revisions; `base`/`final` (acres) give the acre-weighted |revision|."""
    rev = rev.dropna()
    n = len(rev)
    if not n:
        return dict(n=0)
    half = FORECAST['interval_z_grain'] * FORECAST['grain_revision_rel_sd']
    out = dict(n=n, mean=r(rev.mean()), median_abs=r(rev.abs().median()),
               rms=r(math.sqrt((rev ** 2).mean())), sd=r(rev.std(ddof=1)) if n > 1 else None,
               p90_abs=r(rev.abs().quantile(0.90)), p95_abs=r(rev.abs().quantile(0.95)), max_abs=r(rev.abs().max()),
               share_exact_zero=r((rev == 0).mean(), 3),
               coverage_forecast_interval=r((rev.abs() <= half + 1e-12).mean(), 3))
    if base is not None:
        b, f = base.loc[rev.index], final.loc[rev.index]
        out['acre_weighted_abs'] = r((f - b).abs().sum() / b.sum())
    return out


def grain_section(d):
    p = grain_panel(d)
    st = p[p['State'] != 'US TOTAL']
    us = p[p['State'] == 'US TOTAL'].set_index('Year')
    half = FORECAST['interval_z_grain'] * FORECAST['grain_revision_rel_sd']

    def block(df, m):
        return rev_stats(df[f'rev_{m}'], df[m], df['final'])

    pooled = {v: block(st, v) for v in ('nov', 'latest')}
    pooled['fallback_only'] = block(st[st['latest_month'] != 'nov'], 'latest')  # states with no Nov forecast
    by_year = {int(y): dict(nov=block(g, 'nov'), latest=block(g, 'latest')) for y, g in st.groupby('Year')}
    by_month_unbalanced = {m: block(st, m) for m, _ in MONTHS}
    bal = st.dropna(subset=[m for m, _ in MONTHS])
    by_month_balanced = {m: block(bal, m) for m, _ in MONTHS}
    rms_nov = pooled['nov']['rms']
    nov = st[st['nov'].notna()]
    bands = pd.cut(nov['nov'], [0, 500_000, 2_000_000, float('inf')], right=False,
                   labels=['under_500k', '500k_to_2m', '2m_and_over'])
    by_size = {str(k): block(g, 'nov') for k, g in nov.groupby(bands, observed=True)}
    oct_nov = st.dropna(subset=['oct', 'nov'])
    return dict(
        definition='relative revision = (final - forecast) / forecast; states only (US TOTAL and OTHER STATES excluded); '
                   '"final" = Quick Stats current YEAR value (may include revisions after the first January print)',
        forecast_interval_half_width=r(half),
        forecast_grain_revision_rel_sd=FORECAST['grain_revision_rel_sd'],
        pooled_2012_2024=pooled,
        latest_month_counts={k: int(v) for k, v in st['latest_month'].value_counts().sort_index().items()},
        by_year=by_year,
        by_month_unbalanced=by_month_unbalanced,
        by_month_balanced=dict(state_years=len(bal), states=int(bal['State'].nunique()), stats=by_month_balanced),
        oct_equals_nov=dict(state_years_with_both=len(oct_nov), differing=int((oct_nov['oct'] != oct_nov['nov']).sum())),
        by_nov_forecast_size=by_size,
        same_years_as_forecast_2023_2024_nov=block(st[st['Year'].isin([2023, 2024])], 'nov'),
        z_needed_for_95pct_with_forecast_sd=r(pooled['nov']['p95_abs'] / FORECAST['grain_revision_rel_sd'], 2),
        interval_if_rms_from_2012_2024=dict(rel_sd=rms_nov, z=FORECAST['interval_z_grain'],
                                           half_width=r(FORECAST['interval_z_grain'] * rms_nov),
                                           coverage=r((st['rev_nov'].dropna().abs() <= FORECAST['interval_z_grain'] * rms_nov).mean(), 3)),
        us_total_by_year={int(y): {m: r(us.loc[y, f'rev_{m}']) for m, _ in MONTHS} for y in us.index},
    )


def silage_section(d):
    s = finals(d, SILAGE)
    rows = []
    for t in SILAGE_YEARS:
        for state in s.index:
            actual = s.at[state, t] if t in s.columns else float('nan')
            prev = [s.at[state, t - k] if (t - k) in s.columns else float('nan') for k in (1, 2, 3)]
            if not actual > 0 or any(pd.isna(x) for x in prev):
                continue  # strict: t-1..t-3 must all be published, so both baselines score the same rows
            rows.append(dict(State=state, Year=t, actual=actual, persistence=prev[0], mean3=sum(prev) / 3))
    b = pd.DataFrame(rows)

    def score(df):
        out = dict(state_years=len(df), states=int(df['State'].nunique()))
        for m in ('persistence', 'mean3'):
            e = (df[m] - df['actual']).abs()
            pct = e / df['actual']
            out[m] = dict(acre_weighted_abs_pct_error=r(100 * e.sum() / df['actual'].sum(), 2),
                          median_abs_pct_error=r(100 * pct.median(), 2), mean_abs_pct_error=r(100 * pct.mean(), 2))
        return out

    md = b[b['State'] == 'MARYLAND']
    return dict(
        definition='persistence: silage_t = silage_(t-1); mean3: mean of t-1..t-3 finals. Scored only on state-years '
                   'where t-1..t-3 and t are all published (same rows for both). States only.',
        years='2000-2024',
        overall=score(b),
        same_years_as_forecast_2023_2024=score(b[b['Year'].isin([2023, 2024])]),
        by_year={int(y): score(g) for y, g in b.groupby('Year')},
        maryland=score(md),
        maryland_rows=[dict(year=int(x.Year), actual=int(x.actual), persistence=int(x.persistence), mean3=round(x.mean3))
                       for x in md.itertuples()],
        forecast_method_D_reported=FORECAST['silage_backtest'],
    )


def maryland_panel(d):
    p = grain_panel(d)
    md = p[p['State'] == 'MARYLAND'].set_index('Year')
    sil = finals(d, SILAGE).loc['MARYLAND']
    out = []
    for y in GRAIN_YEARS:
        row = dict(year=y)
        for m, _ in MONTHS:
            v = md.at[y, m] if y in md.index else float('nan')
            row[f'grain_{m}'] = None if pd.isna(v) else int(v)
        row['grain_final'] = int(md.at[y, 'final']) if y in md.index else None
        rv = md.at[y, 'rev_nov'] if y in md.index else float('nan')
        row['grain_rev_nov'] = r(rv)
        row['silage_final'] = None if pd.isna(sil.get(y)) else int(sil[y])
        out.append(row)
    return out


def compute(path=CSV):
    d = load(path)
    return dict(
        source=dict(file=path.name, sha256=CSV_SHA256, rows=len(d), years=[int(d['Year'].min()), int(d['Year'].max())],
                    has_2025=False, finals_used_through=LAST_FINAL_YEAR,
                    note='2026 YEAR rows equal the Nov 2026 forecast (preliminary) and are excluded from finals; '
                         'no planted acres in this export, so the forecast method D cannot be re-run here'),
        forecast_reference=FORECAST,
        grain=grain_section(d),
        silage=silage_section(d),
        maryland=maryland_panel(d),
    )


def pct(x, nd=1):
    return '' if x is None else f'{100 * x:.{nd}f}%'


def tables_md(res):
    g, s = res['grain'], res['silage']
    L = ['# Backtest tables (generated by backtest.py; do not edit)', '',
         f"Grain interval of the forecast: +/-{pct(g['forecast_interval_half_width'])} "
         f"(z {FORECAST['interval_z_grain']} x rel. SD {FORECAST['grain_revision_rel_sd']}).", '',
         '## Grain revisions, (final - forecast) / forecast, states, 2012-2024', '',
         '| set | n | median abs | RMS | SD | p95 abs | max abs | exact 0 | acre-wtd abs | inside +/-9.2% |',
         '|---|---|---|---|---|---|---|---|---|---|']

    def row(name, x):
        return (f"| {name} | {x['n']} | {pct(x['median_abs'], 2)} | {pct(x['rms'], 2)} | {pct(x['sd'], 2)} | {pct(x['p95_abs'])} | "
                f"{pct(x['max_abs'])} | {pct(x['share_exact_zero'], 0)} | {pct(x['acre_weighted_abs'], 2)} | {pct(x['coverage_forecast_interval'])} |")
    L.append(row('Nov forecast, pooled', g['pooled_2012_2024']['nov']))
    L.append(row('latest pre-final (Nov, else Oct/Sep/Aug/Jun), pooled', g['pooled_2012_2024']['latest']))
    L.append(row('  of which states with no Nov forecast', g['pooled_2012_2024']['fallback_only']))
    L.append(row('Nov, 2023-2024 only', g['same_years_as_forecast_2023_2024_nov']))
    for k, x in g['by_nov_forecast_size'].items():
        L.append(row(f'Nov, state forecast {k.replace("_", " ")} acres', x))
    on = g['oct_equals_nov']
    L += ['', f"Oct and Nov state forecasts are identical in {on['state_years_with_both'] - on['differing']} of "
          f"{on['state_years_with_both']} state-years that have both."]
    L += ['', '### By year (Nov forecast)', '', '| year | n | median abs | RMS | p95 abs | max abs | inside +/-9.2% |', '|---|---|---|---|---|---|---|']
    for y, v in g['by_year'].items():
        x = v['nov']
        L.append(f"| {y} | {x['n']} | {pct(x['median_abs'], 2)} | {pct(x['rms'], 2)} | {pct(x['p95_abs'])} | {pct(x['max_abs'])} | {pct(x['coverage_forecast_interval'])} |")
    bal = g['by_month_balanced']
    L += ['', f"### Convergence by forecast month (balanced: {bal['state_years']} state-years with all five months, {bal['states']} states)", '',
          '| month | median abs | RMS | p95 abs | acre-wtd abs | inside +/-9.2% | unbalanced n | unbalanced median abs |', '|---|---|---|---|---|---|---|---|']
    for m, _ in MONTHS:
        x, u = bal['stats'][m], g['by_month_unbalanced'][m]
        L.append(f"| {m} | {pct(x['median_abs'], 2)} | {pct(x['rms'], 2)} | {pct(x['p95_abs'])} | {pct(x['acre_weighted_abs'], 2)} | "
                 f"{pct(x['coverage_forecast_interval'])} | {u['n']} | {pct(u['median_abs'], 2)} |")
    L += ['', '### US total grain revision by forecast month', '', '| year | ' + ' | '.join(m for m, _ in MONTHS) + ' |', '|---' * 6 + '|']
    for y, v in g['us_total_by_year'].items():
        L.append(f'| {y} | ' + ' | '.join(pct(v[m], 2) for m, _ in MONTHS) + ' |')
    L += ['', '## Silage naive baselines (abs % error per state-year; each year uses only earlier finals)', '',
          '| set | state-years | persistence acre-wtd | persistence median | persistence mean | 3-yr mean acre-wtd | 3-yr median | 3-yr mean |',
          '|---|---|---|---|---|---|---|---|']
    for name, x in (('2000-2024, all states', s['overall']), ('2023-2024 only', s['same_years_as_forecast_2023_2024']),
                    ('Maryland 2000-2024', s['maryland'])):
        p_, m_ = x['persistence'], x['mean3']
        L.append(f"| {name} | {x['state_years']} | {p_['acre_weighted_abs_pct_error']}% | {p_['median_abs_pct_error']}% | {p_['mean_abs_pct_error']}% | "
                 f"{m_['acre_weighted_abs_pct_error']}% | {m_['median_abs_pct_error']}% | {m_['mean_abs_pct_error']}% |")
    fb = s['forecast_method_D_reported']
    L.append(f"| forecast method D (reported, {fb['years']}, other finals) | {fb['state_years']} | D {fb['acre_weighted_abs_pct_error']['D']}% "
             f"(B {fb['acre_weighted_abs_pct_error']['B_persistence_scaled_by_planted']}%) | {fb['median_abs_pct_error']}% | {fb['mean_abs_pct_error']}% | | | |")
    L += ['', '## Maryland, 2012-2024 (acres)', '',
          '| year | Jun | Aug | Sep | Oct | Nov | grain final | Nov->final | silage final |', '|---|---|---|---|---|---|---|---|---|']
    f = lambda v: '' if v is None else f'{v:,}'  # noqa: E731
    for x in res['maryland']:
        L.append(f"| {x['year']} | {f(x['grain_jun'])} | {f(x['grain_aug'])} | {f(x['grain_sep'])} | {f(x['grain_oct'])} | {f(x['grain_nov'])} | "
                 f"{f(x['grain_final'])} | {pct(x['grain_rev_nov'])} | {f(x['silage_final'])} |")
    return '\n'.join(L) + '\n'


def main():
    res = compute()
    OUT.mkdir(exist_ok=True)
    (OUT / 'backtest.json').write_bytes((json.dumps(res, indent=1) + '\n').encode('utf-8'))
    (OUT / 'tables.md').write_bytes(tables_md(res).encode('utf-8'))
    g = res['grain']['pooled_2012_2024']['nov']
    print(json.dumps(dict(grain_nov=g, silage=res['silage']['overall']), indent=1))


if __name__ == '__main__':
    main()
