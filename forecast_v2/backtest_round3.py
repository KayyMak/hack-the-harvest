#!/usr/bin/env python3
"""Round 3 of the forecast_v2 backtest (PREREGISTRATION_ROUND3.md). Written after round 2's 2025 score was
seen; selection uses the backtest only. Reads only committed inputs, no 2025 value of any kind:

    python forecast_v2/backtest_round3.py   ->  forecast_v2/outputs/round3/backtest_round3.json
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import backtest as bt  # noqa: E402
from common import (GRAIN_METHODS, HERE, ROUND2_METHODS, ROUND3_GRAIN, ROUND3_METHODS,  # noqa: E402
                    ROUND3_SIMPLICITY, load_quickstats)

INCUMBENT_S, INCUMBENT_G = 'R2', 'G1'
TIE_PP = 0.20
MIN_GAIN_PP = 0.50
MEDIAN_SLACK_PP = 0.50
GRAIN_MIN_GAIN_PP = 0.05
OUT = HERE / 'outputs' / 'round3'


def run():
    finals, inseason = load_quickstats()
    assert not any(y > 2024 for (_, y) in finals), 'a final after 2024 was loaded'
    sil = bt.silage_rows(finals, inseason, bt.SILAGE_YEARS)
    rob = bt.silage_rows(finals, inseason, bt.SILAGE_ROBUST_YEARS)
    fp = bt.first_print_rows(inseason)
    gr, gr_us = bt.grain_rows(finals, inseason, bt.GRAIN_YEARS)

    s_methods = [INCUMBENT_S] + list(ROUND3_METHODS)
    pooled = {m: bt.score(sil, m) for m in s_methods}
    floor = min(pooled[m]['acre_weighted_mape'] for m in ROUND3_METHODS)
    challenger = next(m for m in ROUND3_SIMPLICITY if pooled[m]['acre_weighted_mape'] <= floor + TIE_PP)
    gain = pooled[INCUMBENT_S]['acre_weighted_mape'] - pooled[challenger]['acre_weighted_mape']
    median_change = pooled[challenger]['median_ape'] - pooled[INCUMBENT_S]['median_ape']
    s_win = challenger if gain >= MIN_GAIN_PP and median_change <= MEDIAN_SLACK_PP else INCUMBENT_S

    g_methods = [INCUMBENT_G] + list(ROUND3_GRAIN)
    g_pooled = {m: bt.score(gr, m) for m in g_methods}
    g_gain = g_pooled['G1']['acre_weighted_mape'] - g_pooled['GB5']['acre_weighted_mape']
    g_win = 'GB5' if g_gain >= GRAIN_MIN_GAIN_PP else INCUMBENT_G

    out = dict(
        preregistration='forecast_v2/PREREGISTRATION_ROUND3.md (written after round 2\'s 2025 score was seen)',
        silage=dict(window=f'{bt.SILAGE_YEARS[0]}-{bt.SILAGE_YEARS[-1]}',
                    methods={INCUMBENT_S: ROUND2_METHODS[INCUMBENT_S], **ROUND3_METHODS},
                    pooled=pooled, per_year={m: bt.by_year(sil, m) for m in s_methods},
                    robustness_2013_2024={m: bt.score(rob, m) for m in s_methods},
                    first_print_check_2023_2024={m: bt.score(fp, m) for m in s_methods},
                    best_challenger=challenger, gain_vs_incumbent_pp=round(gain, 3),
                    median_change_vs_incumbent_pp=round(median_change, 2),
                    rule=dict(min_gain_pp=MIN_GAIN_PP, median_slack_pp=MEDIAN_SLACK_PP, tie_pp=TIE_PP,
                              simplicity=ROUND3_SIMPLICITY),
                    winner=s_win, interval=bt.coverage(sil, s_win, bt.SILAGE_CLASSES)),
        grain=dict(window=f'{bt.GRAIN_YEARS[0]}-{bt.GRAIN_YEARS[-1]}',
                   methods={INCUMBENT_G: GRAIN_METHODS[INCUMBENT_G], **ROUND3_GRAIN},
                   pooled=g_pooled, per_year={m: bt.by_year(gr, m) for m in g_methods},
                   gain_vs_incumbent_pp=round(g_gain, 3), min_gain_pp=GRAIN_MIN_GAIN_PP, winner=g_win,
                   interval=bt.coverage(gr, g_win, bt.GRAIN_CLASSES)),
    )
    return out


def main():
    out = run()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'backtest_round3.json').write_text(json.dumps(out, indent=1), encoding='utf-8', newline='\n')
    for kind in ('silage', 'grain'):
        b = out[kind]
        for m, v in b['pooled'].items():
            extra = ''
            if kind == 'silage':
                extra = (f"  | 2013-24 {b['robustness_2013_2024'][m]['acre_weighted_mape']:6.2f}"
                         f"  first-print {b['first_print_check_2023_2024'][m]['acre_weighted_mape']:6.2f}")
            print(f"{kind} {m:4s} awMAPE {v['acre_weighted_mape']:7.3f}  median {v['median_ape']:5.2f}"
                  f"  w10 {v['within_10pct']:.3f}{extra}")
        print(kind, 'winner', b['winner'], 'gain vs incumbent', b['gain_vs_incumbent_pp'])


if __name__ == '__main__':
    main()
