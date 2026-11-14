"""One command, end to end, from saved outputs:

    python -m harvest.run --year 2022 --as-of 2022-10-12 --out runs/2022-10-12

Writes into --out:
  predictions.csv        field predictions as of the date (class Grain | Silage | Pending)
  metrics.json           held-out scores vs labels, both classes with Wilson intervals
  rollup.json            silage acres, 95% interval, CV%, adjusted share, NASS context
  quickstats_export.csv  the estimate in the lab QuickStats file's columns
  run.json               what ran: as-of mode, features used, inputs

As-of: monthly NDVI medians are complete at month end, so a date uses only the months
finished by then. Before Nov 30 the same logistic pipeline is refit on the saved field
folds with just those features (needs scikit-learn); from Nov 30 the saved full-season
predictions are used as is. Before Jul 31 nothing is decided: every field is Pending.
"""
import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1] / 'backend'
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app import artifacts, tools  # noqa: E402
from app.artifacts import ArtifactUnavailable, Prediction  # noqa: E402

MONTH_END = {'ndvi_07': (7, 31), 'ndvi_08': (8, 31), 'ndvi_09': (9, 30), 'ndvi_10': (10, 31),
             'ndvi_11': (11, 30)}


def features_as_of(year: int, as_of: date) -> tuple[list[str], str]:
    full = json.loads((artifacts.OUTPUT_DIR / 'metrics.json').read_text(encoding='utf-8'))['features']
    if as_of >= date(year, 11, 30):
        return full, 'saved full-season model'
    usable = [f for f, (m, d) in MONTH_END.items() if as_of >= date(year, m, d)]
    return usable, 'refit on months complete by as-of' if usable else 'too early: all Pending'


def refit_predictions(features: list[str]) -> list[dict]:
    """Same pipeline as baseline/run_baseline.py, same saved folds, fewer features."""
    try:
        import numpy as np
        from sklearn.impute import SimpleImputer
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
    except ImportError as exc:
        raise SystemExit('as-of dates before Nov 30 need scikit-learn: pip install scikit-learn') from exc
    with (artifacts.OUTPUT_DIR / 'heldout_predictions.csv').open(encoding='utf-8', newline='') as f:
        rows = list(csv.DictReader(f))
    X = np.array([[artifacts._num(r[c]) if artifacts._num(r[c]) is not None else np.nan for c in features]
                  for r in rows])
    y = np.array([r['label'] == 'Silage' for r in rows], dtype=int)
    folds = np.array([int(r['fold']) for r in rows])
    prob = np.zeros(len(rows))
    for k in sorted(set(folds)):
        model = make_pipeline(SimpleImputer(strategy='median', keep_empty_features=True), StandardScaler(),
                              LogisticRegression(C=1.0, max_iter=2000, random_state=42))
        model.fit(X[folds != k], y[folds != k])
        prob[folds == k] = model.predict_proba(X[folds == k])[:, 1]
    return [{'field_id': int(r['OBJECTID']), 'year': int(r['year']), 'reference_label': r['label'],
             'predicted_label': 'Silage' if p >= 0.5 else 'Grain', 'silage_probability': float(p),
             'fold': int(r['fold']), 'valid_dates': int(r['valid_dates'])} for r, p in zip(rows, prob)]


def run(year: int, as_of: str, out: Path) -> dict:
    as_of_date = date.fromisoformat(as_of)
    if as_of_date.year != year:
        raise SystemExit('--as-of must fall in --year')
    features, mode = features_as_of(year, as_of_date)
    if mode == 'saved full-season model':
        all_preds = [p.model_dump() for p in artifacts.read_predictions()]
    elif features:
        all_preds = refit_predictions(features)
    else:
        all_preds = []
    preds = [p for p in all_preds if p['year'] == year]

    out.mkdir(parents=True, exist_ok=True)
    pending = [] if preds else [{'field_id': p.field_id, 'year': p.year} for p in artifacts.read_predictions()
                                if p.year == year]
    with (out / 'predictions.csv').open('w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(['OBJECTID', 'year', 'as_of', 'class', 'p_silage', 'reference_label', 'fold', 'model'])
        for p in preds:
            w.writerow([p['field_id'], year, as_of, p['predicted_label'], round(p['silage_probability'], 4),
                        p['reference_label'], p['fold'], mode])
        for p in pending:
            w.writerow([p['field_id'], year, as_of, 'Pending', '', '', '', mode])

    metrics = {'as_of': as_of, 'mode': mode, 'features': features}
    if preds:
        objs = [Prediction(**p) for p in all_preds]
        metrics.update(tools.evaluate_predictions(objs, year))
        rollup = artifacts.compute_rollup(objs)
        rollup.years = [y for y in rollup.years if y.year == year]
    else:
        rollup = None
    (out / 'metrics.json').write_text(json.dumps(metrics, indent=2), encoding='utf-8')

    roll = rollup.model_dump() if rollup else {'years': [], 'note': 'no fields decided yet'}
    try:
        roll['nass_maryland_silage'] = [q.model_dump() for q in
                                        artifacts.read_quickstats('MARYLAND', year, 'silage', 'STATE')]
    except ArtifactUnavailable as exc:
        roll['nass_maryland_silage'] = {'unavailable': str(exc)}
    (out / 'rollup.json').write_text(json.dumps(roll, indent=2), encoding='utf-8')
    if rollup:
        (out / 'quickstats_export.csv').write_text(artifacts.rollup_quickstats_csv(rollup), encoding='utf-8')

    summary = {'year': year, 'as_of': as_of, 'mode': mode, 'features': features,
               'decided': len(preds), 'pending': len(pending), 'out': str(out),
               'balanced_accuracy': metrics.get('balanced_accuracy'),
               'silage_acres_expected': roll['years'][0]['expected_silage_acres'] if roll['years'] else None}
    (out / 'run.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    return summary


def main():
    ap = argparse.ArgumentParser(description='Silage or Grain: one command, end to end')
    ap.add_argument('--year', type=int, required=True, choices=[2021, 2022, 2023])
    ap.add_argument('--as-of', required=True, help='YYYY-MM-DD')
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    print(json.dumps(run(a.year, a.as_of, Path(a.out)), indent=2))


if __name__ == '__main__':
    main()
