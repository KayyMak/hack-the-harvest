#!/usr/bin/env python3
"""After the fact only: compare forecast_v2's 2025 score with the current forecast's, from the two benchmark
reports (python -m harvest.benchmark output). Never used to build or choose anything.

    python forecast_v2/compare_2025.py   ->  forecast_v2/outputs/compare_2025.json
"""
import json
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RUNS = {'current (forecast/)': (ROOT / 'forecast/outputs/benchmark.json', ROOT / 'forecast/outputs/summary.json'),
        'forecast_v2 round 1 (S5)': (HERE / 'outputs/round1/benchmark.json', HERE / 'outputs/round1/summary.json'),
        'forecast_v2 round 2 (R2, submitted)': (HERE / 'outputs/benchmark.json', HERE / 'outputs/summary.json')}
PLAINS = ['NORTH DAKOTA', 'SOUTH DAKOTA', 'NEBRASKA', 'KANSAS', 'OKLAHOMA', 'TEXAS']


def metrics(bench_path, summary_path):
    b = json.loads(bench_path.read_text(encoding='utf-8'))
    s = json.loads(summary_path.read_text(encoding='utf-8'))
    ranges = {(st['state'], 'Silage'): (st['silage_low'], st['silage_high']) for st in s['states']}
    ranges.update({(st['state'], 'Grain'): (st['grain_low'], st['grain_high']) for st in s['states'] if st['grain']})
    rows = [c for c in b['comparisons'] if c['status'] == 'scored']
    out = {'missing_prediction': [(c['geography'], c['crop_use']) for c in b['comparisons'] if c['status'] == 'missing_prediction']}
    for crop in ('Silage', 'Grain'):
        st = [c for c in rows if c['geo_kind'] == 'STATE' and c['crop_use'] == crop and c['relative_error'] is not None]
        us = next(c for c in rows if c['geo_kind'] == 'NATIONAL' and c['crop_use'] == crop)
        md = next(c for c in st if c['geography'] == 'MARYLAND')
        ape = [abs(c['relative_error']) for c in st]
        inside = [ranges[(c['geography'], crop)][0] <= c['reference_value'] <= ranges[(c['geography'], crop)][1]
                  for c in st if (c['geography'], crop) in ranges]
        out[crop.lower()] = dict(
            us_pct_error=round(100 * us['relative_error'], 2), md_pct_error=round(100 * md['relative_error'], 2),
            md_estimate=md['prediction_value'], states=len(st),
            within_10pct=sum(a <= 0.10 for a in ape),
            state_mean_abs_pct_error=round(100 * statistics.mean(ape), 1),
            state_median_abs_pct_error=round(100 * statistics.median(ape), 1),
            state_acre_weighted_abs_pct_error=round(100 * sum(c['absolute_error'] for c in st) / sum(c['reference_value'] for c in st), 2),
            inside_95_range=f'{sum(inside)}/{len(inside)}',
            plains_pct_error={c['geography']: round(100 * c['relative_error'], 1) for c in st if c['geography'] in PLAINS})
    out['us_silage_range'] = [s['us']['silage_low'], s['us']['silage_high']]
    return out


def main():
    res = {name: metrics(*paths) for name, paths in RUNS.items()}
    (HERE / 'outputs' / 'compare_2025.json').write_text(json.dumps(res, indent=1), encoding='utf-8', newline='\n')
    print(json.dumps(res, indent=1))


if __name__ == '__main__':
    main()
