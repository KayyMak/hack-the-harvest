#!/usr/bin/env python3
"""
Dashboard export for the submitted forecast_v2 estimate (R2). Adapted from forecast/export_dashboard.py, which
is left unchanged. It joins forecast_v2/outputs/summary.json (built only from reports released before January
2026) with the judges' NASS 2025 reference (data/reference/quickstats_2025_judges.csv) for display. The
estimator never reads the reference; this script only compares after the fact.

    python forecast_v2/export_dashboard.py   ->  web/public/forecast_2025.json, web/public/forecast_state_estimates_2025.csv
"""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / 'forecast_v2' / 'outputs' / 'summary.json'
ESTIMATES = ROOT / 'forecast_v2' / 'outputs' / 'state_estimates_2025.csv'
JUDGES = ROOT / 'data' / 'reference' / 'quickstats_2025_judges.csv'
OUT = ROOT / 'web' / 'public' / 'forecast_2025.json'
# Student t, 0.95 quantile (two-sided 90%), by degrees of freedom; 30 stands in for anything larger.
T90 = {1: 6.314, 2: 2.920, 3: 2.353, 4: 2.132, 5: 2.015, 6: 1.943, 7: 1.895, 8: 1.860, 9: 1.833, 10: 1.812,
       11: 1.796, 12: 1.782, 13: 1.771, 14: 1.761, 15: 1.753, 16: 1.746, 17: 1.740, 18: 1.734, 19: 1.729,
       20: 1.725, 21: 1.721, 22: 1.717, 23: 1.714, 24: 1.711, 25: 1.708, 26: 1.706, 27: 1.703, 28: 1.701,
       29: 1.699, 30: 1.697}


def acres(v: str):
    v = (v or '').replace(',', '').strip()
    return float(v) if v.replace('.', '', 1).isdigit() else None


def main():
    s = json.loads(SUMMARY.read_text(encoding='utf-8'))
    nass = {}
    for r in csv.DictReader(JUDGES.open(encoding='utf-8')):
        crop = 'silage' if 'SILAGE' in r['Data Item'] else 'grain'
        nass[(r['State'], crop)] = acres(r['Value'])

    def cell(est, se, lo, hi, truth):
        if est is None:
            return None
        err = None if not truth else (est - truth) / truth
        return dict(est=est, se=se, low=lo, high=hi, nass=truth, err=err,
                    inside=None if truth is None else (lo <= truth <= hi))

    states = []
    for st in s['states']:
        states.append(dict(
            state=st['state'],
            silage=cell(st['silage'], st['silage_se'], st['silage_low'], st['silage_high'], nass.get((st['state'], 'silage'))),
            grain=cell(st['grain'], st['grain_se'], st['grain_low'], st['grain_high'], nass.get((st['state'], 'grain'))),
        ))
    us = s['us']
    z = s['interval_z']
    # forecast_v2 saves its own US grain range (Student t on the backtest US errors); fall back to z x SE
    g_lo = us.get('grain_low', round(us['grain'] - z['grain'] * us['grain_se']))
    g_hi = us.get('grain_high', round(us['grain'] + z['grain'] * us['grain_se']))
    us_out = dict(
        silage=cell(us['silage'], us['silage_se'], us['silage_low'], us['silage_high'], nass.get(('US TOTAL', 'silage'))),
        grain=cell(us['grain'], us['grain_se'], g_lo, g_hi, nass.get(('US TOTAL', 'grain'))),
    )

    def reliability(crop):
        """NASS's 'Reliability' format from the saved US backtest: root-mean-square % error, and the 90% margin
        (Student t on n-1 df x RMSE, as NASS does): 9 times in 10 the miss is no larger than this."""
        errs = [v['pct_error'] for v in s['backtest'][crop]['us_total'].values()]
        n = len(errs)
        if n < 2:
            return None
        rmse = (sum(e * e for e in errs) / n) ** 0.5
        t90 = T90[min(n - 1, 30)]
        years = sorted(s['backtest'][crop]['us_total'])
        return dict(years=f'{years[0]}-{years[-1]}', n=n, rmse_pct=round(rmse, 1), t=t90,
                    margin90_pct=round(t90 * rmse, 1), max_abs_pct=round(max(abs(e) for e in errs), 1))

    def score(crop):
        rows = [x[crop] for x in states if x[crop] and x[crop]['nass']]
        abs_err = sum(abs(r['est'] - r['nass']) for r in rows)
        return dict(states=len(rows), within_10pct=sum(abs(r['err']) <= 0.10 for r in rows),
                    acre_weighted_abs_pct_error=round(100 * abs_err / sum(r['nass'] for r in rows), 2),
                    median_abs_pct_error=round(100 * sorted(abs(r['err']) for r in rows)[len(rows) // 2], 2),
                    inside_95_interval=sum(bool(r['inside']) for r in rows))

    out = dict(
        title='2025 corn for grain and silage, acres harvested',
        data_cutoff='2025-11-14',
        estimate_note=('Built only from USDA NASS reports and Quick Stats in-season values released before January 2026 '
                       '(forecast_v2, pre-registered backtest pick R2); the January 2026 Annual Summary is never read.'),
        reference_note='Reference: judges\' NASS QuickStats 2025 export (data/reference/quickstats_2025_judges.csv), used only for scoring.',
        method=s['method'], silage_method=s['silage_method'], backtest=s['backtest'], interval_z=z,
        us=us_out, scores=dict(grain=score('grain'), silage=score('silage')),
        reliability=dict(grain=reliability('grain'), silage=reliability('silage')),
        convergence=s['convergence'], states=states,
        sources=s['sources'],
    )
    OUT.write_text(json.dumps(out, separators=(',', ':')), encoding='utf-8')
    # the QuickStats-shaped estimate file, for the dashboard's download button
    (OUT.parent / 'forecast_state_estimates_2025.csv').write_bytes(ESTIMATES.read_bytes())
    print(f'wrote {OUT} ({OUT.stat().st_size // 1024} KB)')
    print(json.dumps(out['scores'], indent=1))


if __name__ == '__main__':
    main()
