#!/usr/bin/env python3
"""Backtest of the pre-registered forecast_v2 candidates (PREREGISTRATION.md). Reads only committed inputs:

    python forecast_v2/backtest.py      ->  forecast_v2/outputs/backtest.json

Every backtest year t uses finals for years < t and NASS in-season (pre-January) values for t. No 2025 value
of any kind is read here.
"""
import json
import math
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (FC1, GRAIN_METHODS, HERE, SILAGE_METHODS, SIMPLICITY, US, grain_candidates,  # noqa: E402
                    latest, load_quickstats, prior, silage_candidates)

SILAGE_YEARS = list(range(2018, 2025))        # primary window (selection)
SILAGE_ROBUST_YEARS = list(range(2013, 2025))  # reported only
GRAIN_YEARS = list(range(2013, 2025))
SILAGE_TIE_PP = 0.20
GRAIN_MIN_GAIN_PP = 0.05
SILAGE_CLASSES = (20_000, 100_000)
GRAIN_CLASSES = (500_000, 2_000_000)


# ---------------------------------------------------------------- rows
def silage_rows(finals, inseason, years, hist_for=None, truth_for=None):
    rows = []
    for t in years:
        hist = hist_for(t) if hist_for else prior(finals, t)
        states = sorted({st for (st, y) in finals if y == t and st != US}) if truth_for is None else sorted(truth_for(t))
        for st in states:
            truth = truth_for(t)[st] if truth_for else finals[(st, t)]['silage']
            if not truth:
                continue
            planted_t, pp = latest(inseason, st, t, 'planted')
            grain_t, gp = latest(inseason, st, t, 'grain')
            c = silage_candidates(st, t, hist, planted_t, grain_t)
            if c is None:
                continue
            rows.append(dict(year=t, state=st, truth=truth, planted_period=pp, grain_period=gp, **c))
    return rows


def grain_rows(finals, inseason, years):
    rows, us_rows = [], []
    for t in years:
        hist = prior(finals, t)
        for st in sorted({st for (st, y) in finals if y == t}):
            truth = finals[(st, t)]['grain']
            c = grain_candidates(st, t, hist, inseason)
            if not truth or c is None:
                continue
            (us_rows if st == US else rows).append(dict(year=t, state=st, truth=truth, **c))
    return rows, us_rows


# ---------------------------------------------------------------- scores
def score(rows, m):
    if not rows:
        return None
    ape = [abs(r[m] - r['truth']) / r['truth'] for r in rows]
    out = dict(state_years=len(rows),
               acre_weighted_mape=round(100 * sum(abs(r[m] - r['truth']) for r in rows) / sum(r['truth'] for r in rows), 3),
               median_ape=round(100 * statistics.median(ape), 2),
               mean_ape=round(100 * statistics.mean(ape), 2),
               within_10pct=round(sum(a <= 0.10 for a in ape) / len(ape), 3))
    return out


def by_year(rows, m):
    out = {}
    for t in sorted({r['year'] for r in rows}):
        ry = [r for r in rows if r['year'] == t]
        s = score(ry, m)
        est, tru = sum(r[m] for r in ry), sum(r['truth'] for r in ry)
        s['sum_of_states_pct_error'] = round(100 * (est - tru) / tru, 2)
        out[t] = s
    return out


# ---------------------------------------------------------------- intervals
def size_class(est, cuts):
    return sum(est >= c for c in cuts)


def calibrate(rows, m, cuts):
    """se = est x RMS relative error in the row's size class; z = 95th pct of |truth - est| / se (>= 1.96)."""
    rel = {}
    for r in rows:
        if r[m] > 0:
            rel.setdefault(size_class(r[m], cuts), []).append((r['truth'] - r[m]) / r[m])
    rms = {c: math.sqrt(statistics.mean(x * x for x in v)) for c, v in rel.items()}
    pooled = math.sqrt(statistics.mean(x * x for v in rel.values() for x in v))
    for c in range(len(cuts) + 1):
        rms.setdefault(c, pooled)
    zs = sorted(abs(r['truth'] - r[m]) / (r[m] * rms[size_class(r[m], cuts)]) for r in rows if r[m] > 0)
    z = max(1.96, zs[min(len(zs) - 1, math.ceil(0.95 * len(zs)) - 1)] * (1 + 1e-9))
    return dict(rel_rms={str(c): round(v, 5) for c, v in sorted(rms.items())}, z=z, _rms=rms)


def inside(r, m, cal, cuts):
    se = r[m] * cal['_rms'][size_class(r[m], cuts)]
    return max(0.0, r[m] - cal['z'] * se) <= r['truth'] <= r[m] + cal['z'] * se


def coverage(rows, m, cuts):
    cal = calibrate(rows, m, cuts)
    in_sample = sum(inside(r, m, cal, cuts) for r in rows) / len(rows)
    loyo_hits = 0
    for t in sorted({r['year'] for r in rows}):
        c = calibrate([r for r in rows if r['year'] != t], m, cuts)
        loyo_hits += sum(inside(r, m, c, cuts) for r in rows if r['year'] == t)
    return dict(in_sample=round(in_sample, 3), leave_one_year_out=round(loyo_hits / len(rows), 3),
                z=round(cal['z'], 3), rel_rms_by_size_class=cal['rel_rms'], size_class_cuts=list(cuts))


# ---------------------------------------------------------------- first-print check
def first_print_rows(inseason):
    """t = 2023, 2024 with priors as printed in January of t and first-print truth (reported only)."""
    an = {name: FC1.annual(name) for name in ('cropan23', 'cropan24', 'cropan25')}
    priors = {2023: an['cropan23'], 2024: an['cropan24']}
    truth = {2023: an['cropan24'], 2024: an['cropan25']}

    def hist_for(t):
        return {k: v for k, v in priors[t].items() if k[1] < t and k[0] != 'UNITED STATES'}

    def truth_for(t):
        return {st: v['silage'] for (st, y), v in truth[t].items() if y == t and st != 'UNITED STATES' and v['silage']}

    return silage_rows(None, inseason, [2023, 2024], hist_for=hist_for, truth_for=truth_for)


def run():
    finals, inseason = load_quickstats()
    assert not any(y > 2024 for (_, y) in finals), 'a final after 2024 was loaded'

    sil = silage_rows(finals, inseason, SILAGE_YEARS)
    sil_robust = silage_rows(finals, inseason, SILAGE_ROBUST_YEARS)
    fp = first_print_rows(inseason)
    gr, gr_us = grain_rows(finals, inseason, GRAIN_YEARS)

    sil_scores = {m: score(sil, m) for m in SILAGE_METHODS}
    best = min(sil_scores, key=lambda m: sil_scores[m]['acre_weighted_mape'])
    floor = sil_scores[best]['acre_weighted_mape']
    winner = next(m for m in SIMPLICITY if sil_scores[m]['acre_weighted_mape'] <= floor + SILAGE_TIE_PP)

    gr_scores = {m: score(gr, m) for m in GRAIN_METHODS}
    g_winner = 'G2' if gr_scores['G2']['acre_weighted_mape'] <= gr_scores['G1']['acre_weighted_mape'] - GRAIN_MIN_GAIN_PP else 'G1'

    us_sil = by_year(sil, winner)
    us_sil_rel = [(r['sum_of_states_pct_error'] / 100) for r in us_sil.values()]
    us_gr_rel = [(r['truth'] - r[g_winner]) / r[g_winner] for r in gr_us]

    out = dict(
        preregistration='forecast_v2/PREREGISTRATION.md',
        inputs=dict(harvested='analysis/forecast_backtest/quickstats_corn_harvested_1990_2026.csv',
                    planted='forecast_v2/data/quickstats_corn_planted_2005_2026.csv',
                    first_print_check='forecast/cache/cropan23.txt, cropan24.txt, cropan25.txt'),
        silage=dict(
            window=f'{SILAGE_YEARS[0]}-{SILAGE_YEARS[-1]}', methods=SILAGE_METHODS,
            pooled=sil_scores,
            per_year={m: by_year(sil, m) for m in SILAGE_METHODS},
            lowest=best, tie_tolerance_pp=SILAGE_TIE_PP, simplicity_order=SIMPLICITY, winner=winner,
            planted_period_counts={p: sum(r['planted_period'] == p for r in sil) for p in sorted({str(r['planted_period']) for r in sil})},
            robustness_2013_2024=dict(pooled={m: score(sil_robust, m) for m in SILAGE_METHODS},
                                      per_year={m: by_year(sil_robust, m) for m in SILAGE_METHODS}),
            first_print_check_2023_2024=dict(pooled={m: score(fp, m) for m in SILAGE_METHODS},
                                             per_year={m: by_year(fp, m) for m in SILAGE_METHODS}),
            interval=coverage(sil, winner, SILAGE_CLASSES),
            us_rel_rms=round(math.sqrt(statistics.mean(x * x for x in us_sil_rel)), 5),
        ),
        grain=dict(
            window=f'{GRAIN_YEARS[0]}-{GRAIN_YEARS[-1]}', methods=GRAIN_METHODS,
            pooled=gr_scores, per_year={m: by_year(gr, m) for m in GRAIN_METHODS},
            min_gain_pp=GRAIN_MIN_GAIN_PP, winner=g_winner,
            us_rows=[dict(year=r['year'], truth=r['truth'], G1=r['G1'], G2=round(r['G2']), period=r['period']) for r in gr_us],
            us_rel_rms=round(math.sqrt(statistics.mean(x * x for x in us_gr_rel)), 5),
            interval=coverage(gr, g_winner, GRAIN_CLASSES),
            rows_by_period={p: sum(r['period'] == p for r in gr) for p in sorted({r['period'] for r in gr})},
        ),
    )
    return out, dict(sil=sil, gr=gr, gr_us=gr_us)


def main():
    out, _ = run()
    (HERE / 'outputs').mkdir(exist_ok=True)
    (HERE / 'outputs' / 'backtest.json').write_text(json.dumps(out, indent=1), encoding='utf-8')
    s, g = out['silage'], out['grain']
    print('silage', s['window'], 'winner', s['winner'])
    for m, v in s['pooled'].items():
        r = s['robustness_2013_2024']['pooled'][m]
        f = s['first_print_check_2023_2024']['pooled'][m]
        print(f"  {m} awMAPE {v['acre_weighted_mape']:6.2f}  med {v['median_ape']:5.1f}  mean {v['mean_ape']:5.1f}  "
              f"w10 {v['within_10pct']:.2f}  | 2013-24 {r['acre_weighted_mape']:6.2f} | first-print 23-24 {f['acre_weighted_mape']:6.2f}")
    print('  interval', s['interval'])
    print('grain', g['window'], 'winner', g['winner'])
    for m, v in g['pooled'].items():
        print(f"  {m} awMAPE {v['acre_weighted_mape']:6.3f}  med {v['median_ape']:5.2f}  mean {v['mean_ape']:5.2f}  w10 {v['within_10pct']:.3f}")
    print('  interval', g['interval'])


if __name__ == '__main__':
    main()
