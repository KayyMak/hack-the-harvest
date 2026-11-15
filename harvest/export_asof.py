"""Save mid-season (as-of) calls once, so the API can serve them without training.

    python -m harvest.export_asof

For each year and NASS-style release date it asks harvest.asof what the model could
say using only satellite months complete by that date (the logistic pipeline refit on
the saved field folds with those months), and writes baseline/outputs/asof.json.
Needs scikit-learn; makes no network or satellite requests. The API only reads the
saved file: no model is fitted inside an HTTP request.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for extra in (str(ROOT), str(ROOT / 'backend')):
    if extra not in sys.path:
        sys.path.insert(0, extra)

from app import artifacts, tools  # noqa: E402
from harvest import asof  # noqa: E402
from harvest.asof import predictions_as_of  # noqa: E402

YEARS = (2021, 2022, 2023)
MONTH_DAYS = ('08-12', '09-12', '10-12', '11-12', '11-30')
OUT = artifacts.OUTPUT_DIR / 'asof.json'


def build() -> dict:
    dates, pooled = [], {}
    for year in YEARS:
        for month_day in MONTH_DAYS:
            as_of = f'{year}-{month_day}'
            state = predictions_as_of(year, as_of)
            mine = [p for p in state['predictions'] if p.year == year]
            dates.append({'year': year, 'as_of': as_of, 'mode': state['mode'], 'features': state['features'],
                'predictions': [{'field_id': p.field_id, 'predicted_label': p.predicted_label,
                                 'silage_probability': round(p.silage_probability, 6),
                                 'reference_label': p.reference_label} for p in mine],
                'pending_field_ids': sorted(state['pending'])})
            pooled.setdefault(month_day, {'decided': [], 'pending': 0})
            pooled[month_day]['decided'] += mine
            pooled[month_day]['pending'] += len(state['pending'])
    summary = []
    for month_day, group in pooled.items():
        decided = group['decided']
        scores = tools.evaluate_predictions(decided) if decided else {}
        correct = sum(p.predicted_label == p.reference_label for p in decided)
        total = len(decided) + group['pending']
        summary.append({'month_day': month_day, 'field_years': total, 'decided': len(decided),
            'share_decided': len(decided) / total if total else None,
            'accuracy_decided': correct / len(decided) if decided else None,
            'balanced_accuracy': scores.get('balanced_accuracy'),
            'silage_recall': scores.get('silage_recall'),
            'confusion_matrix': scores.get('confusion_matrix')})
    v2 = any(d['mode'] == asof.REFIT_V1 for d in dates)
    method = ('Logistic pipeline refit on the saved field folds using only monthly NDVI medians '
              'complete by each date; the saved full-season model from Nov 30')
    if v2:
        method = ('Before Nov 30: the v1 logistic pipeline (C = 1) refit on the saved field folds using only monthly '
                  'NDVI medians complete by each date (model v2 needs the full season and was not validated on '
                  'truncated series). From Nov 30: the saved full-season model v2 (NDVI and harvest-timing '
                  'features, L1).')
    return {'scope': 'Labeled BARC field-years, held out by field; pooled over 2021-2023 in `pooled`',
            'method': method,
            'years': list(YEARS), 'month_days': list(MONTH_DAYS), 'dates': dates, 'pooled': summary}


def main() -> None:
    data = build()
    OUT.write_text(json.dumps(data, indent=1) + '\n', encoding='utf-8', newline='\n')
    for row in data['pooled']:
        print(row['month_day'], 'decided', row['decided'], 'of', row['field_years'],
              'balanced accuracy', row['balanced_accuracy'], 'silage recall', row['silage_recall'])


if __name__ == '__main__':
    main()
