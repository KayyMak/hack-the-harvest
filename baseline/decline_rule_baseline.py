"""Transparent rule baseline: date of sustained NDVI decline, one threshold.

    python baseline/decline_rule_baseline.py

The challenge names this rule as the baseline any model must beat. It reads only
the saved per-scene observations and the saved field folds, so it needs no
satellite access and no analysis packages (standard library only). It never
modifies the logistic regression artifacts.

Rule, fixed before any result was computed:
  1. Per field-year, keep accepted ("ok") observations and take the median NDVI
     per date, so duplicate processing versions of a scene count once.
  2. Smooth with a centered 3-date rolling median.
  3. Peak = the highest smoothed value.
  4. Decline date = the first date after the peak where smoothed NDVI is at least
     DROP below the peak and is still that low at the next clear date. A low
     final observation counts, because nothing later can contradict it.
  5. Silage if the decline date is on or before day-of-year T, otherwise Grain.
     No sustained decline in the season is Grain (the crop was still standing).

DROP is fixed at 0.25. T is the only fitted value: for each saved fold it is
chosen on the training fields alone (best balanced accuracy over GRID, median of
ties) and applied to that fold's held-out fields. Every year of a field stays in
one fold, exactly as in the logistic baseline. An early decline is a hypothesis
about harvest timing, not proof of silage.
"""
import csv
from datetime import date
import json
from pathlib import Path
import statistics

HERE = Path(__file__).resolve().parent
INPUTS = HERE / 'outputs'
OUT = INPUTS / 'decline_rule'
DROP = 0.25
GRID = range(200, 331)


def daily_series(observations):
    """[(date, median NDVI)] over accepted observations, sorted by date."""
    by_date = {}
    for row in observations:
        if row['status'] == 'ok' and row['ndvi'] not in ('', None):
            by_date.setdefault(row['date'], []).append(float(row['ndvi']))
    return [(day, statistics.median(values)) for day, values in sorted(by_date.items())]


def smooth(values):
    return [statistics.median(values[max(0, i - 1):i + 2]) for i in range(len(values))]


def decline_doy(series, drop=DROP):
    """Day of year of the sustained decline, or None when there is none."""
    if not series:
        return None
    values = smooth([value for _, value in series])
    peak = max(range(len(values)), key=lambda i: values[i])
    low = [value <= values[peak] - drop for value in values]
    for i in range(peak + 1, len(values)):
        if low[i] and (i == len(values) - 1 or low[i + 1]):
            return date.fromisoformat(series[i][0]).timetuple().tm_yday
    return None


def classify(doy, threshold):
    return 'Silage' if doy is not None and doy <= threshold else 'Grain'


def score(truth, predicted):
    tn = sum(a == 'Grain' and b == 'Grain' for a, b in zip(truth, predicted))
    fp = sum(a == 'Grain' and b == 'Silage' for a, b in zip(truth, predicted))
    fn = sum(a == 'Silage' and b == 'Grain' for a, b in zip(truth, predicted))
    tp = sum(a == 'Silage' and b == 'Silage' for a, b in zip(truth, predicted))
    recall = tp / (tp + fn) if tp + fn else None
    specificity = tn / (tn + fp) if tn + fp else None
    return dict(n=len(truth), silage_precision=tp / (tp + fp) if tp + fp else 0.0,
        silage_recall=recall, silage_f1=2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0,
        false_positive_rate=1 - specificity if specificity is not None else None,
        balanced_accuracy=(recall + specificity) / 2 if recall is not None and specificity is not None else None,
        confusion_matrix=[[tn, fp], [fn, tp]], matrix_order=['Grain', 'Silage'],
        matrix_rows='true', matrix_columns='predicted')


def fit_threshold(rows):
    """Best balanced accuracy on these rows; median of tied thresholds."""
    truth = [row['label'] for row in rows]
    scored = [(score(truth, [classify(row['decline_doy'], t) for row in rows])['balanced_accuracy'], t)
              for t in GRID]
    best = max(value for value, _ in scored)
    return int(statistics.median_low([t for value, t in scored if value == best]))


def load():
    with (INPUTS / 'heldout_predictions.csv').open(encoding='utf-8', newline='') as file:
        rows = [dict(OBJECTID=int(r['OBJECTID']), year=int(r['year']), label=r['label'], fold=int(r['fold']),
                     logistic_prediction=r['predicted_label']) for r in csv.DictReader(file)]
    metadata = json.loads((INPUTS / 'metrics.json').read_text(encoding='utf-8'))
    if len(rows) != metadata['evaluated_field_years'] or any(r['label'] not in ('Grain', 'Silage') for r in rows):
        raise ValueError('Saved predictions do not match the saved evaluation, or a label is blank')
    observations = {}
    with (INPUTS / 'observations.csv').open(encoding='utf-8', newline='') as file:
        for r in csv.DictReader(file):
            observations.setdefault((int(r['OBJECTID']), int(r['year'])), []).append(r)
    for row in rows:
        series = daily_series(observations.get((row['OBJECTID'], row['year']), []))
        if not series:
            raise ValueError(f'No accepted observations for field {row["OBJECTID"]} / {row["year"]}')
        row['clear_dates'] = len(series)
        row['decline_doy'] = decline_doy(series)
    return rows, metadata


def evaluate(rows, metadata):
    thresholds = {}
    for fold in metadata['folds']:
        train_fields, test_fields = set(fold['training_fields']), set(fold['test_fields'])
        if train_fields & test_fields:
            raise ValueError('A field is in both the training and held-out side of a fold')
        test = [r for r in rows if r['OBJECTID'] in test_fields]
        if {r['fold'] for r in test} != {fold['fold']}:
            raise ValueError('Saved prediction folds do not match saved split metadata')
        threshold = fit_threshold([r for r in rows if r['OBJECTID'] in train_fields])
        thresholds[fold['fold']] = threshold
        for row in test:
            row['threshold_doy'] = threshold
            row['rule_prediction'] = classify(row['decline_doy'], threshold)
    if any('rule_prediction' not in r for r in rows):
        raise ValueError('Saved folds do not cover every evaluated field-year')
    truth = [r['label'] for r in rows]
    by = lambda key, subset: score([r['label'] for r in subset], [r[key] for r in subset])
    return dict(
        protocol='Saved field-grouped folds; threshold fitted on training fields only; '
                 'DROP fixed at 0.25 before any result was computed',
        drop=DROP, threshold_grid=[GRID.start, GRID.stop - 1], thresholds_by_fold=thresholds,
        evaluated_field_years=len(rows), no_sustained_decline=sum(r['decline_doy'] is None for r in rows),
        decline_rule=by('rule_prediction', rows), logistic_same_rows=by('logistic_prediction', rows),
        always_grain_same_rows=score(truth, ['Grain'] * len(rows)),
        by_year={str(year): dict(decline_rule=by('rule_prediction', subset),
                                 logistic=by('logistic_prediction', subset))
                 for year in sorted({r['year'] for r in rows})
                 for subset in [[r for r in rows if r['year'] == year]]},
        limitations=['Exploratory comparison on already-inspected BARC data; not an independent test.',
                     'Twelve Silage field-years: differences of one or two rows are not distinguishable.',
                     'An early NDVI decline is a hypothesis about harvest timing, not proof of silage.',
                     'Cloud gaps can delay or hide the decline date; no residue (SWIR) evidence is used.'])


def write(rows, report):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'metrics.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8', newline='\n')
    with (OUT / 'predictions.csv').open('w', encoding='utf-8', newline='') as file:
        names = ['OBJECTID', 'year', 'fold', 'label', 'clear_dates', 'decline_doy', 'threshold_doy',
                 'rule_prediction', 'logistic_prediction']
        writer = csv.DictWriter(file, fieldnames=names, lineterminator='\n')
        writer.writeheader()
        for row in rows:
            writer.writerow({name: '' if row[name] is None else row[name] for name in names})
    rule, logistic, grain = (report[k] for k in ['decline_rule', 'logistic_same_rows', 'always_grain_same_rows'])
    fmt = lambda value: 'n/a' if value is None else f'{value:.4f}'
    lines = ['# Decline-date rule baseline', '',
        'One transparent rule on the date of sustained NDVI decline, scored on the same 44 held-out',
        'BARC field-years and the same field folds as the logistic regression. The day-of-year',
        'threshold is fitted on training fields only; the 0.25 NDVI drop was fixed beforehand.', '',
        '| Metric | Decline rule | Logistic regression | Always Grain |', '| --- | ---: | ---: | ---: |']
    for label, key in [('Silage precision', 'silage_precision'), ('Silage recall', 'silage_recall'),
                       ('Silage F1', 'silage_f1'), ('False positive rate', 'false_positive_rate'),
                       ('Balanced accuracy', 'balanced_accuracy')]:
        lines.append(f'| {label} | {fmt(rule[key])} | {fmt(logistic[key])} | {fmt(grain[key])} |')
    (tn, fp), (fn, tp) = rule['confusion_matrix']
    lines += ['', f'Decline rule confusion (rows true, columns predicted): Grain {tn} / {fp}, Silage {fn} / {tp}.',
        f'Thresholds by fold (day of year): {report["thresholds_by_fold"]}.',
        f'{report["no_sustained_decline"]} field-years had no sustained decline in the season and are called Grain.',
        '', '## Limits', ''] + [f'- {item}' for item in report['limitations']]
    (OUT / 'results.md').write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')


def main():
    rows, metadata = load()
    report = evaluate(rows, metadata)
    write(rows, report)
    print(json.dumps({k: report[k] for k in ['thresholds_by_fold', 'no_sustained_decline', 'decline_rule',
                                               'logistic_same_rows', 'always_grain_same_rows']}, indent=2))


if __name__ == '__main__':
    main()
