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
predictions (model v2) are used as is; the 'model' column and field name the version.
Before Jul 31 nothing is decided: every field is Pending.
"""
import argparse
import csv
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
for _p in (_ROOT, _ROOT / 'backend'):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from app import artifacts, tools  # noqa: E402
from app.artifacts import ArtifactUnavailable  # noqa: E402
from harvest.asof import model_label, predictions_as_of  # noqa: E402


def run(year: int, as_of: str, out: Path) -> dict:
    try:
        state = predictions_as_of(year, as_of)
    except (ValueError, RuntimeError) as exc:
        raise SystemExit(str(exc)) from exc
    mode, features, objs = state['mode'], state['features'], state['predictions']
    model = model_label(mode)
    all_preds = [p.model_dump() for p in objs]
    preds = [p for p in all_preds if p['year'] == year]

    out.mkdir(parents=True, exist_ok=True)
    pending = [{'field_id': f, 'year': year} for f in state['pending']]
    with (out / 'predictions.csv').open('w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(['OBJECTID', 'year', 'as_of', 'class', 'p_silage', 'reference_label', 'fold', 'model'])
        for p in preds:
            w.writerow([p['field_id'], year, as_of, p['predicted_label'], round(p['silage_probability'], 4),
                        p['reference_label'], p['fold'], model])
        for p in pending:
            w.writerow([p['field_id'], year, as_of, 'Pending', '', '', '', model])

    metrics = {'as_of': as_of, 'mode': mode, 'model': model, 'features': features}
    if preds:
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

    summary = {'year': year, 'as_of': as_of, 'mode': mode, 'model': model, 'features': features,
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
