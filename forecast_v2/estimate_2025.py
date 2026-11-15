#!/usr/bin/env python3
"""2025 corn-for-grain and corn-for-silage acres harvested, every state + US, with the backtest winner fixed in
forecast_v2/outputs/backtest.json (see PREREGISTRATION.md). Run from the repo root:

    python forecast_v2/backtest.py         # fixes the winner (no 2025 value read)
    python forecast_v2/estimate_2025.py    # -> forecast_v2/outputs/state_estimates_2025.csv, summary.json

Inputs for 2025: NASS reports released before January 2026 (cached in forecast/cache/: June Acreage, Aug, Sep,
Nov Crop Production) and the planted file's 2025 in-season periods. Finals for 2022-2024 come from the January
2025 Annual Summary (cropan25); earlier finals from Quick Stats. The January 2026 Annual Summary (cropan26),
the judges' file and every 2025 YEAR value are never read.
"""
import csv
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import backtest as bt  # noqa: E402
from common import FC1, GRAIN_METHODS, HERE, ROOT, SILAGE_METHODS, US, load_quickstats, silage_candidates  # noqa: E402

OUT = HERE / 'outputs'
OLD_CSV = ROOT / 'forecast' / 'outputs' / 'state_estimates_2025.csv'
SIL_ITEM, GR_ITEM = 'CORN, SILAGE - ACRES HARVESTED', 'CORN, GRAIN - ACRES HARVESTED'


def history_2025(finals):
    """Finals for years < 2025: Quick Stats up to 2021, the January 2025 Annual Summary for 2022-2024."""
    hist = {k: dict(v) for k, v in finals.items() if k[1] < 2022 and k[0] != US}
    for (st, y), v in FC1.annual('cropan25').items():
        if st != 'UNITED STATES' and y in (2022, 2023, 2024):
            hist[(st, y)] = dict(planted=v['planted'], grain=v['grain'], silage=v['silage'])
    assert all(y < 2025 for (_, y) in hist)
    return hist


def vintages(inseason):
    """2025 in-season inputs as known at each pre-January release, each falling back to the earlier release
    where a state is missing: (release, date, label, planted{st}, grain{st}, us_grain)."""
    def planted(*periods):
        out = {}
        for p in reversed(periods):   # earliest first, later releases overwrite
            out.update({st: d['planted'][p] for (st, y), d in inseason.items()
                        if y == 2025 and st != US and d['planted'].get(p)})
        return out

    def grain_of(name):
        return {st: v['grain'] for st, v in FC1.planted_grain_report(name).items() if v['grain']}

    jun = grain_of('acrg0625')
    aug = {**jun, **grain_of('crop0825')}
    sep = {**aug, **grain_of('crop0925')}
    nov = {**sep, **{st: v for st, v in FC1.grain_report('crop1125').items() if v}}
    pj = planted('YEAR - JUN ACREAGE', 'YEAR - MAR ACREAGE')
    pa = planted('YEAR - AUG FORECAST', 'YEAR - JUN ACREAGE', 'YEAR - MAR ACREAGE')
    ps = planted('YEAR - SEP FORECAST', 'YEAR - AUG FORECAST', 'YEAR - JUN ACREAGE', 'YEAR - MAR ACREAGE')
    out = []
    for rel, date, label, pl, gr in (
            ('JUN', '2025-06-30', 'June Acreage', pj, jun),
            ('AUG', '2025-08-12', 'Aug Crop Production', pa, aug),
            ('SEP', '2025-09-12', 'Sep Crop Production', ps, sep),
            ('NOV', '2025-11-14', 'Nov Crop Production', ps, nov)):   # no planted update after September 2025
        out.append((rel, date, label, pl, {st: v for st, v in gr.items() if st != 'UNITED STATES'}, gr.get('UNITED STATES')))
    return out


def estimate(hist, planted, grain, s_method, g_method, cal_s, cal_g):
    res = {}
    for st in sorted(set(planted) | {s for (s, _) in hist}):
        c = silage_candidates(st, 2025, hist, planted.get(st), grain.get(st))
        if c is None:
            continue
        h1 = {k: v for k, v in hist.items() if k[0] == st and k[1] in (2022, 2023, 2024)}
        d = FC1.estimate_state(st, planted.get(st), grain.get(st), h1, [2022, 2023, 2024], 0.0, 'D', 2025) if planted.get(st) else None
        sil = c[s_method]
        se = sil * cal_s['_rms'][bt.size_class(sil, bt.SILAGE_CLASSES)]
        g = grain.get(st)
        gse = g * cal_g['_rms'][bt.size_class(g, bt.GRAIN_CLASSES)] if g else None
        res[st] = dict(silage=sil, silage_se=se, grain=g, grain_se=gse, candidates=c,
                       share_mean=d['share_mean'] if d else None, share_sd=d['share_sd'] if d else None,
                       share_kind=d['share_kind'] if d else None)
    return res


def main():
    committed = json.loads((OUT / 'backtest.json').read_text(encoding='utf-8'))
    back, rows = bt.run()
    s_method, g_method = back['silage']['winner'], back['grain']['winner']
    assert (s_method, g_method) == (committed['silage']['winner'], committed['grain']['winner']), 'winner differs from the committed backtest'
    assert g_method == 'G1', 'only the pre-registered winner G1 is wired for 2025 grain'
    cals = rows['cals']   # per release (PREREGISTRATION.md amendment 1); NOV = the main backtest
    cal_s, cal_g = cals['NOV']['silage'], cals['NOV']['grain']
    z_s, z_g = cal_s['z'], cal_g['z']
    (us_rel_s, us_t_s), (us_rel_g, us_t_g) = cals['NOV']['us_silage'], cals['NOV']['us_grain']

    finals, inseason = load_quickstats()
    hist = history_2025(finals)

    by_date, by_state, final = [], [], None
    for rel, date, label, planted, grain, us_gr_row in vintages(inseason):
        c = cals[rel]
        est = estimate(hist, planted, grain, s_method, g_method, c['silage'], c['grain'])
        (rs, ts), (rg, tg) = c['us_silage'], c['us_grain']
        zs_, zg_ = c['silage']['z'], c['grain']['z']
        us_sil = sum(e['silage'] for e in est.values())
        us_gr = us_gr_row or sum(e['grain'] for e in est.values() if e['grain'])
        md = est.get('MARYLAND')
        bp = back['per_release'][rel]
        by_date.append(dict(
            as_of=date, source=label, us_silage=round(us_sil), us_silage_se=round(us_sil * rs),
            us_silage_low=round(us_sil * (1 - ts * rs)), us_silage_high=round(us_sil * (1 + ts * rs)),
            us_grain=round(us_gr), us_grain_se=round(us_gr * rg),
            md_silage=round(md['silage']) if md else None, md_silage_se=round(md['silage_se']) if md else None,
            # added in forecast_v2: each date's own range, calibrated on that release's backtest errors
            us_grain_low=round(us_gr * (1 - tg * rg)), us_grain_high=round(us_gr * (1 + tg * rg)),
            us_silage_half_width_pct=round(100 * ts * rs, 2), us_grain_half_width_pct=round(100 * tg * rg, 2),
            md_silage_low=max(0, round(md['silage'] - zs_ * md['silage_se'])) if md else None,
            md_silage_high=round(md['silage'] + zs_ * md['silage_se']) if md else None,
            md_grain=round(md['grain']) if md and md['grain'] else None,
            md_grain_low=round(md['grain'] - zg_ * md['grain_se']) if md and md['grain'] else None,
            md_grain_high=round(md['grain'] + zg_ * md['grain_se']) if md and md['grain'] else None,
            interval_z=dict(silage=round(zs_, 2), grain=round(zg_, 2), us_t_silage=ts, us_t_grain=tg),
            backtest_state_coverage_loyo=dict(silage=bp['silage']['interval']['leave_one_year_out'],
                                              grain=bp['grain']['interval']['leave_one_year_out']),
            backtest_us_years_inside=dict(silage=f"{bp['silage']['us']['inside_leave_one_year_out']}/{bp['silage']['us']['years']}",
                                          grain=f"{bp['grain']['us']['inside_leave_one_year_out']}/{bp['grain']['us']['years']}")))
        for st, e in sorted(est.items()):
            by_state.append([rel, date, st, round(e['silage']), max(0, round(e['silage'] - zs_ * e['silage_se'])),
                             round(e['silage'] + zs_ * e['silage_se']),
                             round(e['grain']) if e['grain'] else '', max(0, round(e['grain'] - zg_ * e['grain_se'])) if e['grain'] else '',
                             round(e['grain'] + zg_ * e['grain_se']) if e['grain'] else ''])
        final = (est, us_sil, us_gr)
    est, us_sil, us_gr = final
    with (OUT / 'convergence_by_state_2025.csv').open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['release', 'as_of', 'state', 'silage', 'silage_low', 'silage_high', 'grain', 'grain_low', 'grain_high'])
        w.writerows(by_state)

    # rows: exactly the (State, Data Item) rows of the current forecast's CSV, in its order
    old = list(csv.DictReader(OLD_CSV.open(encoding='utf-8')))
    out_rows, states = [], []
    for r in old:
        st, item = r['State'], r['Data Item']
        if st == 'US TOTAL':
            v = us_sil if item == SIL_ITEM else us_gr
        else:
            e = est[st]
            v = e['silage'] if item == SIL_ITEM else e['grain']
        if v is None:
            raise RuntimeError(f'no 2025 value for {st} / {item}')
        out_rows.append([r['Year'], r['Geo Level'], st, item, r['Domain'], f'{round(v):,}'])
    OUT.mkdir(exist_ok=True)
    with (OUT / 'state_estimates_2025.csv').open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['Year', 'Geo Level', 'State', 'Data Item', 'Domain', 'Value'])
        w.writerows(out_rows)

    in_csv = {r['State'] for r in old if r['State'] != 'US TOTAL'}
    for st in sorted(in_csv):
        e = est[st]
        g = e['grain'] if any(r['State'] == st and r['Data Item'] == GR_ITEM for r in old) else None
        states.append(dict(
            state=st, silage=round(e['silage']), silage_se=round(e['silage_se']),
            silage_cv_pct=round(100 * e['silage_se'] / e['silage'], 1) if e['silage'] else None,
            silage_low=max(0, round(e['silage'] - z_s * e['silage_se'])), silage_high=round(e['silage'] + z_s * e['silage_se']),
            grain=round(g) if g else None, grain_se=round(e['grain_se']) if g else None,
            grain_cv_pct=round(100 * e['grain_se'] / g, 1) if g else None,
            grain_low=max(0, round(g - z_g * e['grain_se'])) if g else None, grain_high=round(g + z_g * e['grain_se']) if g else None,
            share_of_non_grain=round(e['share_mean'], 4) if e['share_mean'] is not None else None,
            share_sd=round(e['share_sd'], 4) if e['share_sd'] is not None else None, share_base=e['share_kind']))

    def bt_summary(kind):
        b = back[kind]
        m = b['winner']
        p = b['pooled'][m]
        if kind == 'silage':
            yrs = {t: v for t, v in b['per_year'][m].items()}
            rws = rows['sil']
            us_total = {}
            for t in yrs:
                ry = [r for r in rws if str(r['year']) == str(t)]
                e_, t_ = sum(r[m] for r in ry), sum(r['truth'] for r in ry)
                us_total[t] = dict(est=round(e_), truth=round(t_), pct_error=round(100 * (e_ - t_) / t_, 2))
        else:
            us_total = {str(r['year']): dict(est=round(r[m]), truth=round(r['truth']),
                                             pct_error=round(100 * (r[m] - r['truth']) / r['truth'], 2)) for r in rows['gr_us']}
        return dict(state_years=p['state_years'], median_abs_pct_error=round(p['median_ape'], 1),
                    mean_abs_pct_error=round(p['mean_ape'], 1),
                    covered_by_95_interval=b['interval']['leave_one_year_out'], us_total=us_total)

    rel_g = [(r['truth'] - r[g_method]) / r[g_method] for r in rows['gr']]
    summary = dict(
        method=(f'forecast_v2 (pre-registered backtest winner). grain = latest pre-January NASS grain-area forecast '
                f'(Nov 14 2025; Sep 12 2025 where November omits the state) as is ({GRAIN_METHODS[g_method]}). '
                f'silage = {SILAGE_METHODS[s_method]}, i.e. the average of method D (forecast/estimate_2025.py, shares over '
                '2022-2024) and last year\'s silage acres. Chosen by the lowest acre-weighted absolute % error over '
                '2018-2024 state-years among 6 pre-registered candidates. SE = estimate x the backtest RMS relative '
                'error of its size class; 95% range = estimate +/- z SE with z the 95th percentile of backtest |error|/SE; '
                'covered_by_95_interval is leave-one-year-out. US: SE = estimate x RMS of the backtest US relative '
                'errors, 95% range = +/- t(0.975, n-1) SE. Each convergence date is re-estimated with only what was '
                'known then and gets its own range, calibrated on the backtest errors of that release.'),
        answer_key_excluded=('Crop Production Annual Summary, January 2026 (cropan26), the judges\' file and every 2025 '
                             'YEAR value are never read; the planted export\'s 2025 YEAR rows were removed before commit.'),
        sources={k_: dict(title=v['title'], released=v['released'], url=v['url']) for k_, v in FC1.SOURCES['reports'].items()},
        silage_method=dict(chosen=s_method, description=SILAGE_METHODS[s_method],
                           backtest_acre_weighted_abs_pct_error={m: round(v['acre_weighted_mape'], 2) for m, v in back['silage']['pooled'].items()},
                           candidates=SILAGE_METHODS,
                           rule=('lowest acre-weighted absolute % error over 2018-2024 state-years (simplest candidate within '
                                 '0.20 pp); pre-registered in forecast_v2/PREREGISTRATION.md; 2025 answers never used')),
        grain_revision_rel_sd=round(math.sqrt(sum(x * x for x in rel_g) / len(rel_g)), 4),
        interval_z=dict(silage=round(z_s, 2), grain=round(z_g, 2)),
        backtest=dict(silage=bt_summary('silage'), grain=bt_summary('grain')),
        us=dict(silage=round(us_sil), silage_se=round(us_sil * us_rel_s),
                silage_low=round(us_sil * (1 - us_t_s * us_rel_s)), silage_high=round(us_sil * (1 + us_t_s * us_rel_s)),
                silage_cv_pct=round(100 * us_rel_s, 2),
                grain=round(us_gr), grain_se=round(us_gr * us_rel_g), grain_cv_pct=round(100 * us_rel_g, 2),
                grain_low=round(us_gr * (1 - us_t_g * us_rel_g)), grain_high=round(us_gr * (1 + us_t_g * us_rel_g))),
        convergence=by_date, states=states)
    (OUT / 'summary.json').write_text(json.dumps(summary, indent=1), encoding='utf-8', newline='\n')
    md = next(s for s in states if s['state'] == 'MARYLAND')
    print(json.dumps(dict(us=summary['us'], maryland=md, interval_z=summary['interval_z']), indent=1))


if __name__ == '__main__':
    main()
