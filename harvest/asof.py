"""As-of predictions: what the model could say on a given date, using only satellite months
complete by then. Shared by the one command (harvest.run) and the agent tools (harvest.tools).

Monthly NDVI medians are complete at month end. Before Nov 30 the v1 logistic pipeline
(run_baseline.build_model: C = 1, threshold 0.5) is refit on the saved field folds with just
those features (needs scikit-learn); from Nov 30 the saved full-season predictions are used;
before Jul 31 every field is Pending. Artifacts are read on each call so regenerated outputs
take effect immediately.

When the saved full-season model is model v2 (metrics.json "model_version": "v2"), mid-season
dates still use that v1 month-cut refit and say so in their mode: v2 was selected and validated
only on full-season series (its timing features and November NDVI need the whole season; see
baseline/model_v2/results.md), so a truncated v2 would be a new, unvalidated model.
"""
import csv
import json
import sys
from datetime import date
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1] / 'backend'
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app import artifacts  # noqa: E402
from app.schemas import Prediction  # noqa: E402

MONTH_END = {'ndvi_07': (7, 31), 'ndvi_08': (8, 31), 'ndvi_09': (9, 30), 'ndvi_10': (10, 31),
             'ndvi_11': (11, 30)}
FULL = 'saved full-season model'
EARLY = 'too early: all Pending'
REFIT = 'refit on months complete by as-of'  # saved model is v1: the refit is the same model
REFIT_V1 = 'v1 month-cut refit'  # saved model is v2: mid-season dates use the v1 refit, labelled as such


def model_label(mode: str) -> str:
    """The as-of mode with the model version named, e.g. 'saved full-season model (model v2)'."""
    if mode in (EARLY, REFIT_V1):  # no model yet / already says v1
        return mode
    version = json.loads((artifacts.OUTPUT_DIR / 'metrics.json').read_text(encoding='utf-8')).get('model_version', 'v1')
    return f'{mode} (model {version})'


def features_as_of(year: int, as_of: date) -> tuple[list[str], str]:
    try:
        saved = json.loads((artifacts.OUTPUT_DIR / 'metrics.json').read_text(encoding='utf-8'))
        full, version = saved['features'], saved.get('model_version', 'v1')
        if not isinstance(full, list) or not full or not all(isinstance(f, str) for f in full):
            raise ValueError('Invalid feature list')
        if version not in ('v1', 'v2'):
            raise ValueError('Unknown model version')
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise artifacts.ArtifactUnavailable('Saved model features are missing or invalid.') from exc
    if as_of >= date(year, 11, 30):
        return full, FULL
    usable = [f for f, (m, d) in MONTH_END.items() if as_of >= date(year, m, d)]
    return usable, (REFIT if version == 'v1' else REFIT_V1) if usable else EARLY


def _refit(features: tuple[str, ...]) -> tuple[Prediction, ...]:
    """Same pipeline as baseline/run_baseline.py, same saved folds, fewer features."""
    try:
        import numpy as np
        from sklearn.impute import SimpleImputer
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
    except ImportError as exc:
        raise RuntimeError('as-of dates before Nov 30 need scikit-learn: pip install scikit-learn') from exc
    # Validate labels and grouped folds before any training, including blank labels.
    saved = artifacts.read_predictions()
    try:
        with (artifacts.OUTPUT_DIR / 'heldout_predictions.csv').open(encoding='utf-8', newline='') as f:
            rows = list(csv.DictReader(f))
        num = lambda v: np.nan if artifacts._num(v) is None else artifacts._num(v)
        X = np.array([[num(r[c]) for c in features] for r in rows])
        field_folds = {}
        for p in saved:
            if field_folds.setdefault(p.field_id, p.fold) != p.fold:
                raise ValueError('A field crosses validation folds')
        y = np.array([p.reference_label == 'Silage' for p in saved], dtype=int)
        folds = np.array([p.fold for p in saved])
        if len(set(folds)) < 2 or any(len(set(y[folds != k])) != 2 for k in set(folds)):
            raise ValueError('Each training fold needs both classes')
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise artifacts.ArtifactUnavailable('Saved as-of training data is missing or invalid.') from exc
    prob = np.zeros(len(rows))
    for k in sorted(set(folds)):
        model = make_pipeline(SimpleImputer(strategy='median', keep_empty_features=True), StandardScaler(),
                              LogisticRegression(C=1.0, max_iter=2000, random_state=42))
        model.fit(X[folds != k], y[folds != k])
        prob[folds == k] = model.predict_proba(X[folds == k])[:, 1]
    return tuple(Prediction(field_id=int(r['OBJECTID']), year=int(r['year']), reference_label=r['label'],
        predicted_label='Silage' if p >= 0.5 else 'Grain', silage_probability=float(p),
        fold=int(r['fold']), valid_dates=int(r['valid_dates'])) for r, p in zip(rows, prob))


def predictions_as_of(year: int, as_of: str) -> dict:
    """{'mode', 'features', 'predictions' (all years, for error rates), 'pending' (field ids of `year`)}."""
    day = date.fromisoformat(as_of)
    if day.year != year:
        raise ValueError(f'as_of {as_of} is not in year {year}')
    features, mode = features_as_of(year, day)
    if mode == FULL:
        preds = artifacts.read_predictions()
    elif mode in (REFIT, REFIT_V1):
        preds = list(_refit(tuple(features)))
    else:
        preds = []
    pending = [] if preds else [p.field_id for p in artifacts.read_predictions() if p.year == year]
    return {'mode': mode, 'features': features, 'predictions': preds, 'pending': pending}
