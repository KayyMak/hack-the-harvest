#!/usr/bin/env python3
"""Round 2 of the forecast_v2 backtest (PREREGISTRATION.md, "Round 2"). Written after round 1's 2025 score was
seen; selection still uses the backtest only. Reads only committed inputs:

    python forecast_v2/backtest_round2.py   ->  forecast_v2/outputs/backtest_round2.json
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import backtest as bt  # noqa: E402
from common import HERE, ROUND2_METHODS, ROUND2_SIMPLICITY, SILAGE_METHODS, load_quickstats  # noqa: E402

TIE_PP = 0.20
MIN_GAIN_PP = 0.50       # must beat S5's acre-weighted MAPE by at least this
MEDIAN_SLACK_PP = 0.50   # and not worsen S5's median APE by more than this


def run():
    finals, inseason = load_quickstats()
    sil = bt.silage_rows(finals, inseason, bt.SILAGE_YEARS)
    rob = bt.silage_rows(finals, inseason, bt.SILAGE_ROBUST_YEARS)
    fp = bt.first_print_rows(inseason)
    methods = ['S1', 'S5'] + list(ROUND2_METHODS)
    pooled = {m: bt.score(sil, m) for m in methods}
    floor = min(pooled[m]['acre_weighted_mape'] for m in ROUND2_METHODS)
    r2 = next(m for m in ROUND2_SIMPLICITY if pooled[m]['acre_weighted_mape'] <= floor + TIE_PP)
    s5 = pooled['S5']
    gain = s5['acre_weighted_mape'] - pooled[r2]['acre_weighted_mape']
    median_change = pooled[r2]['median_ape'] - s5['median_ape']
    qualifies = gain >= MIN_GAIN_PP and median_change <= MEDIAN_SLACK_PP
    out = dict(
        preregistration='forecast_v2/PREREGISTRATION.md, section "Round 2" (written after round 1\'s 2025 score was seen)',
        window=f'{bt.SILAGE_YEARS[0]}-{bt.SILAGE_YEARS[-1]}',
        methods={**{m: SILAGE_METHODS[m] for m in ('S1', 'S5')}, **ROUND2_METHODS},
        pooled=pooled, per_year={m: bt.by_year(sil, m) for m in methods},
        robustness_2013_2024={m: bt.score(rob, m) for m in methods},
        first_print_check_2023_2024={m: bt.score(fp, m) for m in methods},
        round2_winner=r2, gain_vs_s5_pp=round(gain, 3), median_change_vs_s5_pp=round(median_change, 2),
        rule=dict(min_gain_pp=MIN_GAIN_PP, median_slack_pp=MEDIAN_SLACK_PP, tie_pp=TIE_PP, simplicity=ROUND2_SIMPLICITY),
        qualifies=qualifies, final_silage_method=r2 if qualifies else 'S5',
        interval=bt.coverage(sil, r2, bt.SILAGE_CLASSES),
    )
    if qualifies:
        out['per_release'], _ = bt.per_release(finals, inseason, r2, 'G1')
    return out


def main():
    out = run()
    (HERE / 'outputs' / 'backtest_round2.json').write_text(json.dumps(out, indent=1), encoding='utf-8', newline='\n')
    for m, v in out['pooled'].items():
        print(f"{m} awMAPE {v['acre_weighted_mape']:7.3f}  median {v['median_ape']:5.2f}  mean {v['mean_ape']:5.2f}  w10 {v['within_10pct']:.3f}"
              f"  | 2013-24 {out['robustness_2013_2024'][m]['acre_weighted_mape']:6.2f}  first-print {out['first_print_check_2023_2024'][m]['acre_weighted_mape']:6.2f}")
    print('round-2 winner', out['round2_winner'], 'gain', out['gain_vs_s5_pp'], 'median change', out['median_change_vs_s5_pp'],
          'qualifies', out['qualifies'], '-> final', out['final_silage_method'])


if __name__ == '__main__':
    main()
