"""As-of predictions: what the model could say on a given date, using only satellite months
complete by then. Shared by the one command (harvest.run) and the agent tools (harvest.tools).

Monthly NDVI medians are complete at month end. Before Nov 30 the baseline's logistic
pipeline is refit on the saved field folds with just those features (needs scikit-learn);
from Nov 30 the saved full-season predictions are used; before Jul 31 every field is Pending.
Results are cached per feature set, so repeated calls (the as-of slider, the agent) are instant.
"""
import csv
import json
import sys
from datetime import date
from functools import lru_cache
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
REFIT = 'refit on months complete by as-of'


def features_as_of(year: int, as_of: date) -> tuple[list[str], str]:
    full = json.loads((artifacts.OUTPUT_DIR / 'metrics.json').read_text(encoding='utf-8'))['features']
    if as_of >= date(year, 11, 30):
        return full, FULL
    usable = [f for f, (m, d) in MONTH_END.items() if as_of >= date(year, m, d)]
    return usable, REFIT if usable else EARLY


@lru_cache(maxsize=16)
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
    with (artifacts.OUTPUT_DIR / 'heldout_predictions.csv').open(encoding='utf-8', newline='') as f:
        rows = list(csv.DictReader(f))
    num = lambda v: np.nan if artifacts._num(v) is None else artifacts._num(v)
    X = np.array([[num(r[c]) for c in features] for r in rows])
    y = np.array([r['label'] == 'Silage' for r in rows], dtype=int)
    folds = np.array([int(r['fold']) for r in rows])
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
    elif mode == REFIT:
        preds = list(_refit(tuple(features)))
    else:
        preds = []
    pending = [] if preds else [p.field_id for p in artifacts.read_predictions() if p.year == year]
    return {'mode': mode, 'features': features, 'predictions': preds, 'pending': pending}
