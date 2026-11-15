"""Which field model the regenerating scripts use.

    MODEL_VERSION = 'v2'   (override for one shell: HTH_MODEL_VERSION=v1)

v2  model v2 = pre-registered candidate H from baseline/model_v2/ (the submitted model):
    the nine NDVI features plus four harvest-timing features (decline_doy, drop_doy,
    drop_size, regrowth), training-fold median imputation and scaling, L1 logistic
    regression with C chosen by field-grouped inner CV, threshold 0.5.
v1  the original baseline, kept as a working backup: run_baseline.build_model() on the
    nine NDVI features (C = 1, threshold 0.5). With v1 every script writes the same
    columns, numbers and prose as before v2 was adopted (baseline/outputs/v1_backup/).

Scripts that fit a model (run_baseline.py evaluate, export_contributions.py,
unlabeled_calls.py predict, estimate_2025/estimate.py) read the version here when they run.
Readers of saved outputs (harvest/asof.py, the API, the web snapshot) follow the version
recorded in baseline/outputs/metrics.json instead, so they always describe what was saved.
This module imports nothing heavy; the model code is imported only when a model is built.
"""
import json
import os
from pathlib import Path
import sys

MODEL_VERSION = 'v2'
VERSIONS = ('v1', 'v2')
ENV = 'HTH_MODEL_VERSION'
HERE = Path(__file__).resolve().parent

BASE_FEATURES = ['ndvi_07', 'ndvi_08', 'ndvi_09', 'ndvi_10', 'ndvi_11',
                 'peak_ndvi', 'peak_doy', 'late_ndvi', 'early_minus_late']
TIMING_FEATURES = ['decline_doy', 'drop_doy', 'drop_size', 'regrowth']

NAMES = {
    'v1': 'Logistic regression on NDVI',
    'v2': 'Logistic regression on NDVI and harvest-timing features (L1)',
}
DESCRIPTIONS = {
    'v1': 'run_baseline.build_model() (median imputation, standard scaling, logistic regression C=1.0)',
    'v2': ('model v2 (pre-registered candidate H, baseline/model_v2): median imputation, standard scaling, '
           'L1 logistic regression (liblinear) with C chosen by field-grouped inner CV, threshold 0.5'),
}


def current() -> str:
    version = os.environ.get(ENV, MODEL_VERSION).strip().lower()
    if version not in VERSIONS:
        raise ValueError(f'{ENV} must be one of {VERSIONS}, not {version!r}')
    return version


def features(version: str | None = None) -> list[str]:
    version = version or current()
    return BASE_FEATURES + (TIMING_FEATURES if version == 'v2' else [])


def saved_version(metrics_path: Path = HERE / 'outputs' / 'metrics.json') -> str:
    """Version recorded with the saved held-out predictions; files written before v2 have none (v1)."""
    return json.loads(Path(metrics_path).read_text(encoding='utf-8')).get('model_version', 'v1')


def check_saved_matches(version: str | None = None, metrics_path: Path = HERE / 'outputs' / 'metrics.json'):
    """Stop a downstream script from mixing models: its version must match the saved held-out run."""
    version = version or current()
    saved = saved_version(metrics_path)
    if saved != version:
        raise RuntimeError(f'Model version {version} does not match the saved held-out predictions ({saved}); '
                           f'run python baseline/run_baseline.py evaluate first, or set {ENV}={saved}.')


def _candidate():
    path = str(HERE / 'model_v2')
    if path not in sys.path:
        sys.path.insert(0, path)
    import candidate  # noqa: E402  (needs numpy, pandas, scikit-learn only)
    return candidate


def v1_pipeline():
    """The v1 pipeline, identical to run_baseline.build_model() (test_model_version checks this),
    built here so fitting does not import the extraction stack."""
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    return make_pipeline(SimpleImputer(strategy='median', keep_empty_features=True),
        StandardScaler(), LogisticRegression(C=1.0, max_iter=2000, random_state=42))


class V1Model:
    """The v1 pipeline behind the fit(X, y, groups) signature; groups are not used."""

    def __init__(self):
        self.pipeline = v1_pipeline()

    def fit(self, X, y, groups=None):
        self.pipeline.fit(X, y)
        return self

    def predict_proba(self, X):
        return self.pipeline.predict_proba(X)

    def predict(self, X):
        return self.pipeline.predict(X)


def build_model(version: str | None = None):
    """Unfitted model with fit(X, y, groups), predict_proba(X) (n, 2) and predict(X).
    X must be a DataFrame holding features(version). v2 needs field ids as groups."""
    version = version or current()
    return V1Model() if version == 'v1' else _candidate().build_model()


def fitted_pipeline(model):
    """The fitted sklearn pipeline (imputer, scaler, logistic regression) inside a built model."""
    return model.pipeline if isinstance(model, V1Model) else model.fitted_.model


def timing_from_observations(observations) -> dict:
    """The four timing features from one field-year's per-scene records ('date', 'ndvi', 'status')."""
    return _candidate().timing_from_observations(observations)
