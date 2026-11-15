#!/usr/bin/env python3
"""Round 4 of the forecast_v2 backtest (PREREGISTRATION_ROUND4.md): yield-adjusted silage. Written after the
round-2 2025 score was seen. Selection uses the backtest only. Reads only committed inputs and no 2025 final:

    python forecast_v2/backtest_round4.py   ->  forecast_v2/outputs/round4/backtest_round4.json

Y1 = R2 x (1 + beta_t x a), clipped to [0.5, 1.5] x R2, a = state in-season yield / state 5-year mean final - 1.
Y2 = the same with the US yield anomaly for every state. beta_t is fitted on state-years 2013..t-1 only.
"""
import csv
import json
import math
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import backtest as bt  # noqa: E402
from common import HERE, LAST_FINAL_YEAR, ROUND2_METHODS, US, load_quickstats, num  # noqa: E402

YIELD_CSV = HERE / 'data' / 'quickstats_corn_yield_2000_2025.csv'
INCUMBENT = 'R2'
SIMPLICITY = ['Y2', 'Y1']   # Y2 is simpler: it wins within TIE_PP of Y1
TIE_PP = 0.20
MIN_GAIN_PP = 0.50
MEDIAN_SLACK_PP = 0.50
BETA_FROM = 2013
MIN_BETA_STATE_YEARS = 30
CLIP = (0.5, 1.5)
OUT = HERE / 'outputs' / 'round4'
METHODS = {
    'Y1': 'R2 x (1 + beta_t x a_state), clipped to [0.5, 1.5] x R2; a_state = latest in-season state yield / '
          'state 5-year mean final yield (t-5..t-1, >= 3 finals) - 1; no state anomaly -> R2',
    'Y2': 'R2 x (1 + beta_t x a_US), clipped to [0.5, 1.5] x R2; a_US = latest in-season US yield / US 5-year mean '
          'final yield - 1, the same for every state',
}
# in-season yield known at each release (latest first); June has none -> a undefined -> R2
YIELD_PERIODS = {
    'JUN': [],
    'AUG': ['YEAR - AUG FORECAST'],
    'SEP': ['YEAR - SEP FORECAST', 'YEAR - AUG FORECAST'],
    'NOV': ['YEAR - NOV FORECAST', 'YEAR - OCT FORECAST', 'YEAR - SEP FORECAST', 'YEAR - AUG FORECAST'],
}


def load_yields():
    """fin[(state, year)] = final yield for years <= 2024; fc[(state, year)] = {period: in-season forecast}."""
    fin, fc = {}, {}
    with open(YIELD_CSV, encoding='utf-8-sig', newline='') as f:
        for r in csv.DictReader(f):
            y, v = int(r['Year']), num(r['Value'])
            if y >= 2026 or v is None:
                continue
            if r['Period'] == 'YEAR':
                if y > LAST_FINAL_YEAR:
                    continue   # 2025 final yield = answer-key era (the committed file holds none; guard anyway)
                fin[(r['State'], y)] = v
            else:
                fc.setdefault((r['State'], y), {})[r['Period']] = v
    return fin, fc


def anomaly(fin, fc, st, t, release='NOV'):
    """yf_t(st) / mean(final yield of st, t-5..t-1) - 1, or None (no in-season yield, or < 3 finals)."""
    d = fc.get((st, t), {})
    yf = next((d[p] for p in YIELD_PERIODS[release] if d.get(p) is not None), None)
    past = [fin[(st, y)] for y in range(t - 5, t) if fin.get((st, y)) is not None]
    if yf is None or len(past) < 3:
        return None
    return yf / statistics.mean(past) - 1


def add_anomalies(rows, fin, fc, release='NOV'):
    for r in rows:
        r['a1'] = anomaly(fin, fc, r['state'], r['year'], release)
        r['a2'] = anomaly(fin, fc, US, r['year'], release)
    return rows


def fit_beta(rows, t, key):
    """Weighted LS slope through the origin of (truth / R2 - 1) on a, weights = previous-year silage acres,
    over state-years BETA_FROM..t-1 with both defined; 0 if fewer than MIN_BETA_STATE_YEARS."""
    pts = [(r['S2'], r[key], r['truth'] / r[INCUMBENT] - 1) for r in rows
           if BETA_FROM <= r['year'] < t and r[key] is not None and r[INCUMBENT] > 0]
    den = sum(w * a * a for w, a, _ in pts)
    if len(pts) < MIN_BETA_STATE_YEARS or den == 0:
        return 0.0, len(pts)
    return sum(w * a * y for w, a, y in pts) / den, len(pts)


def adjusted(r2, beta, a):
    if a is None:
        return r2
    return r2 * min(CLIP[1], max(CLIP[0], 1 + beta * a))


def betas_for(beta_rows, years):
    out = {}
    for t in years:
        b1, n1 = fit_beta(beta_rows, t, 'a1')
        b2, n2 = fit_beta(beta_rows, t, 'a2')
        out[t] = dict(Y1=b1, Y1_state_years=n1, Y2=b2, Y2_state_years=n2)
    return out


def apply(rows, betas):
    for r in rows:
        b = betas[r['year']]
        r['Y1'] = adjusted(r[INCUMBENT], b['Y1'], r['a1'])
        r['Y2'] = adjusted(r[INCUMBENT], b['Y2'], r['a2'])
    return rows


def us_rmse(per_year):
    return round(math.sqrt(statistics.mean(v['sum_of_states_pct_error'] ** 2 for v in per_year.values())), 3)


def per_release(finals, inseason, fin, fc, betas, s_method, g_method='G1'):
    """bt.per_release for a round-4 silage method: each release's rows use the yield forecast known then and
    beta_t (fitted on finished years only, so known at every release of t). Grain is G1, unchanged."""
    base, base_cals = bt.per_release(finals, inseason, INCUMBENT, g_method)
    out, cals = {}, {}
    for rel in bt.RELEASES:
        sil = apply(add_anomalies(bt.silage_rows(finals, inseason, bt.SILAGE_YEARS, release=rel), fin, fc, rel), betas)
        us_s = {}
        for t in bt.SILAGE_YEARS:
            ry = [r for r in sil if r['year'] == t]
            e, tr = sum(r[s_method] for r in ry), sum(r['truth'] for r in ry)
            us_s[t] = (tr - e) / e
        out[rel] = dict(base[rel], silage=dict(
            score=bt.score(sil, s_method), interval=bt.coverage(sil, s_method, bt.SILAGE_CLASSES), us=bt.us_check(us_s),
            planted_periods=base[rel]['silage']['planted_periods'],
            rows_with_anomaly=sum(r['a1' if s_method == 'Y1' else 'a2'] is not None for r in sil)))
        cals[rel] = dict(base_cals[rel], silage=bt.calibrate(sil, s_method, bt.SILAGE_CLASSES),
                         us_silage=bt.us_band(list(us_s.values())))
    return out, cals


def run():
    finals, inseason = load_quickstats()
    assert not any(y > 2024 for (_, y) in finals), 'a final after 2024 was loaded'
    fin, fc = load_yields()
    assert not any(y > 2024 for (_, y) in fin), 'a final yield after 2024 was loaded'

    rob = add_anomalies(bt.silage_rows(finals, inseason, bt.SILAGE_ROBUST_YEARS), fin, fc)   # 2013-2024
    betas = betas_for(rob, range(BETA_FROM, LAST_FINAL_YEAR + 2))   # 2013..2025 (2025 uses 2013-2024)
    apply(rob, betas)
    sil = [r for r in rob if r['year'] in bt.SILAGE_YEARS]
    assert len(sil) == len(bt.silage_rows(finals, inseason, bt.SILAGE_YEARS)), 'rows differ from backtest.silage_rows'

    methods = [INCUMBENT, 'Y1', 'Y2']
    pooled = {m: bt.score(sil, m) for m in methods}
    per_year = {m: bt.by_year(sil, m) for m in methods}
    floor = min(pooled[m]['acre_weighted_mape'] for m in SIMPLICITY)
    challenger = next(m for m in SIMPLICITY if pooled[m]['acre_weighted_mape'] <= floor + TIE_PP)
    gain = pooled[INCUMBENT]['acre_weighted_mape'] - pooled[challenger]['acre_weighted_mape']
    median_change = pooled[challenger]['median_ape'] - pooled[INCUMBENT]['median_ape']
    win = challenger if gain >= MIN_GAIN_PP and median_change <= MEDIAN_SLACK_PP else INCUMBENT

    out = dict(
        preregistration='forecast_v2/PREREGISTRATION_ROUND4.md (commit ab143f2, written before the yield data was '
                        'downloaded and after round 2\'s 2025 score was seen)',
        inputs=dict(yield_csv='forecast_v2/data/quickstats_corn_yield_2000_2025.csv (starts 2005; 2025 YEAR and 2026 '
                              'rows removed)', yield_periods=YIELD_PERIODS),
        silage=dict(
            window=f'{bt.SILAGE_YEARS[0]}-{bt.SILAGE_YEARS[-1]}', methods={INCUMBENT: ROUND2_METHODS[INCUMBENT], **METHODS},
            pooled=pooled, per_year=per_year,
            us_rmse_pct_2018_2024={m: us_rmse(per_year[m]) for m in methods},
            robustness_2013_2024={m: bt.score(rob, m) for m in methods},
            beta_by_year={str(t): dict(Y1=round(b['Y1'], 4), Y1_state_years=b['Y1_state_years'],
                                       Y2=round(b['Y2'], 4), Y2_state_years=b['Y2_state_years'])
                          for t, b in betas.items()},
            rows_with_state_anomaly=sum(r['a1'] is not None for r in sil), rows=len(sil),
            best_challenger=challenger, gain_vs_incumbent_pp=round(gain, 3),
            median_change_vs_incumbent_pp=round(median_change, 2),
            rule=dict(min_gain_pp=MIN_GAIN_PP, median_slack_pp=MEDIAN_SLACK_PP, tie_pp=TIE_PP, simplicity=SIMPLICITY),
            winner=win, interval=bt.coverage(sil, win, bt.SILAGE_CLASSES)),
    )
    return out, dict(finals=finals, inseason=inseason, fin=fin, fc=fc, betas=betas, sil=sil)


def main():
    out, _ = run()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'backtest_round4.json').write_text(json.dumps(out, indent=1), encoding='utf-8', newline='\n')
    s = out['silage']
    for m, v in s['pooled'].items():
        print(f"{m:3s} awMAPE {v['acre_weighted_mape']:7.3f}  median {v['median_ape']:5.2f}  w10 {v['within_10pct']:.3f}"
              f"  US RMSE {s['us_rmse_pct_2018_2024'][m]:5.2f}  | 2013-24 {s['robustness_2013_2024'][m]['acre_weighted_mape']:6.2f}"
              f"  | US by year {[v2['sum_of_states_pct_error'] for v2 in s['per_year'][m].values()]}")
    print('beta', {t: (b['Y1'], b['Y1_state_years'], b['Y2'], b['Y2_state_years']) for t, b in s['beta_by_year'].items()})
    print('rows with state anomaly', s['rows_with_state_anomaly'], '/', s['rows'])
    print('best challenger', s['best_challenger'], 'gain', s['gain_vs_incumbent_pp'], 'median change',
          s['median_change_vs_incumbent_pp'], '-> winner', s['winner'])


if __name__ == '__main__':
    main()
