#!/usr/bin/env python3
"""
Cross-check against forecast/estimate_2025.py on ITS OWN finals (Annual Summary text, first or
second January print), read only. Separate from backtest.py, which reads only the Quick Stats CSV.

  1. Reproduces grain_revision_rel_sd (0.0448) from the Nov 2023/2024 reports and checks how many
     2023/2024 finals in the Quick Stats export differ from the Annual Summary values it used.
  2. Counts grain backtest rows the forecast fills with the final itself (states the November
     report omits), which have zero error by construction.
  3. Scores plain persistence (silage_t = silage_(t-1)) on the same 2023-2024 state-years and
     finals as the forecast's method-D backtest: a like-for-like comparison.

    python analysis/forecast_backtest/crosscheck_forecast.py
Needs forecast/cache/*.txt (committed); never touches the 2025 answer key (cropan26).
"""
import json
import math
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / 'forecast'))
sys.path.insert(0, str(HERE))
import backtest  # noqa: E402
import estimate_2025 as est  # noqa: E402


def main():
    hist = {**est.annual('cropan23'), **est.annual('cropan24'), **est.annual('cropan25')}
    qs = backtest.load()
    qs_final = {(x.State, x.Year): x.acres for x in qs[(qs['Data Item'] == backtest.GRAIN) & (qs['Period'] == 'YEAR')].itertuples()}
    qs_sil = {(x.State, x.Year): x.acres for x in qs[(qs['Data Item'] == backtest.SILAGE) & (qs['Period'] == 'YEAR')].itertuples()}

    half = backtest.FORECAST['interval_z_grain'] * backtest.FORECAST['grain_revision_rel_sd']
    revs, final_diffs, padded, grain_rows = [], [], 0, 0
    pers_err = pers_tot = 0.0
    pers_pct, d_rows = [], 0
    sil_diffs = 0
    for nov, y in (('crop1123', 2023), ('crop1124', 2024)):
        g = est.grain_report(nov)
        for st, v in g.items():
            f = hist.get((st, y), {}).get('grain')
            if st != 'UNITED STATES' and v and f:
                revs.append((f - v) / v)
                if qs_final.get((st, y)) != f:
                    final_diffs.append(dict(state=st, year=y, annual_summary=f, quickstats=qs_final.get((st, y))))
        planted = {st: hist[(st, y)]['planted'] for (st, yy) in hist if yy == y and hist[(st, y)]['planted']}
        grain_y = {st: g.get(st, hist.get((st, y), {}).get('grain')) for st in planted}
        for st, e in est.run_year(y, planted, grain_y, hist, [y - 3, y - 2, y - 1], 0.0448, 'D').items():
            truth = hist.get((st, y), {})
            if e['grain'] and truth.get('grain'):
                grain_rows += 1
                padded += not g.get(st)
            if truth.get('silage'):
                d_rows += 1
                prev = hist.get((st, y - 1), {}).get('silage')
                if prev is not None:
                    pers_err += abs(prev - truth['silage'])
                    pers_tot += truth['silage']
                    pers_pct.append(abs(prev - truth['silage']) / truth['silage'])
                if qs_sil.get((st, y)) != truth['silage']:
                    sil_diffs += 1
    out = dict(
        grain_revision_rel_sd_reproduced=round(math.sqrt(statistics.mean(r * r for r in revs)), 4),
        nov_state_years=len(revs),
        nov_inside_forecast_interval_annual_summary_finals=round(
            sum(abs(r) <= half + 1e-12 for r in revs) / len(revs), 3),
        nov_inside_count=sum(abs(r) <= half + 1e-12 for r in revs),
        quickstats_grain_finals_differing_from_annual_summary=final_diffs,
        forecast_grain_backtest_rows=grain_rows,
        forecast_grain_rows_filled_with_final=padded,
        silage_persistence_on_forecast_rows=dict(
            state_years=len(pers_pct), of_method_D_rows=d_rows,
            acre_weighted_abs_pct_error=round(100 * pers_err / pers_tot, 2),
            median_abs_pct_error=round(100 * statistics.median(pers_pct), 2),
            mean_abs_pct_error=round(100 * statistics.mean(pers_pct), 2)),
        silage_finals_differing_quickstats_vs_annual_summary=sil_diffs,
    )
    (backtest.OUT / 'crosscheck_forecast.json').write_bytes((json.dumps(out, indent=1) + '\n').encode('utf-8'))
    print(json.dumps(out, indent=1))


if __name__ == '__main__':
    main()
