"""LangChain tool wrappers for the agent: `from harvest.tools import TOOLS`.

Same eight tools as backend/app/tools.py, plus forecast_2025 (the submitted 2025 acre forecast)
and decline_rule_baseline (the organizers' decline-date rule vs our model). classify, evaluate
and aggregate also take an optional as_of date (YYYY-MM-DD): the model then only sees satellite
months complete by that date (see harvest/asof.py). Results are JSON strings; failures come back as
{"error": ...} instead of raising. Requires langchain-core (a LangGraph dependency).
"""
import inspect
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
for _p in (_ROOT, _ROOT / 'backend'):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from app import artifacts  # noqa: E402
from app import tools as core  # noqa: E402
from app.artifacts import ArtifactUnavailable  # noqa: E402
from app.tools import call_tool, log_step  # noqa: E402,F401
from harvest.asof import model_label, predictions_as_of  # noqa: E402

try:
    from langchain_core.tools import StructuredTool
    from pydantic import ConfigDict, ValidationError, create_model
except ImportError as exc:  # pragma: no cover
    raise ImportError('harvest.tools needs langchain-core: pip install langchain-core') from exc


SCOPE = ('Only BARC field-years that have a Grain or Silage reference label are scored; blank labels are '
         'unknown and excluded. n counts those labeled field-years, not satellite coverage.')


def _scoped(out: dict) -> dict:
    """Say what n counts, so a report never explains it as a data gap."""
    if isinstance(out, dict) and 'error' not in out:
        out.setdefault('scope', SCOPE)
    return out


def classify(year: int | None = None, as_of: str | None = None, field_ids: list[int] | None = None) -> dict:
    """Silage/Grain call per field for a year with silage probability and the NDVI evidence
    behind it. With as_of (YYYY-MM-DD) only satellite months complete by that date are used and
    undecided fields are Pending. Reference labels are returned separately as reference_label."""
    if as_of is None:
        return _scoped(core.classify(year, field_ids))
    if year is None:
        return {'error': 'as_of needs year'}
    s = predictions_as_of(year, as_of)
    out = core.classify_predictions(s['predictions'], year, field_ids, model_label(s['mode']), only=s['features'])
    pending = [f for f in s['pending'] if field_ids is None or f in field_ids]
    out.update(as_of=as_of, features=s['features'], pending=pending, n_pending=len(pending))
    return _scoped(out)


def evaluate(year: int | None = None, as_of: str | None = None) -> dict:
    """Held-out scores vs the BARC labels: confusion matrix, precision and recall for both classes
    with Wilson 95% intervals, counts by year and class, always-Grain comparison. With as_of
    (needs year) the model only sees satellite months complete by that date."""
    if as_of is None:
        return _scoped(core.evaluate(year))
    if year is None:
        return {'error': 'as_of needs year'}
    s = predictions_as_of(year, as_of)
    if not s['predictions']:
        return {'as_of': as_of, 'mode': s['mode'], 'n': 0, 'note': 'no fields decided yet'}
    return _scoped({'as_of': as_of, 'mode': s['mode'], 'features': s['features'],
                    **core.evaluate_predictions(s['predictions'], year)})


def aggregate(year: int | None = None, as_of: str | None = None) -> dict:
    """Silage acres per year: expected acres with 95% interval and CV%, bias-adjusted acres, and
    the reference (labeled) silage acres. With as_of (needs year) only months complete by then."""
    if as_of is None:
        return core.aggregate(year)
    if year is None:
        return {'error': 'as_of needs year'}
    s = predictions_as_of(year, as_of)
    if not s['predictions']:
        return {'as_of': as_of, 'mode': s['mode'], 'years': [], 'note': 'no fields decided yet'}
    r = artifacts.compute_rollup(s['predictions']).model_dump()
    r['years'] = [y for y in r['years'] if y['year'] == year]
    return {'as_of': as_of, 'mode': s['mode'], 'features': s['features'], **r}


# NASS-style margin of error of the forecast (backtest RMSE of the US totals), as shown on the dashboard.
RELIABILITY_JSON = _ROOT / 'web' / 'public' / 'forecast_2025.json'
FORECAST_NOTE = ('Built only from USDA NASS reports and Quick Stats in-season values released before January 2026; '
                 'no 2025 final (January 2026) value was used to fit or choose it.')
_FORECAST_KEYS = ('silage', 'silage_se', 'silage_cv_pct', 'silage_low', 'silage_high',
                  'grain', 'grain_se', 'grain_cv_pct', 'grain_low', 'grain_high')


def _reliability() -> dict | None:
    """The dashboard's margin-of-error block, or None when the file is missing or unreadable."""
    try:
        rel = json.loads(RELIABILITY_JSON.read_text(encoding='utf-8')).get('reliability')
    except (OSError, ValueError, AttributeError):
        return None
    return rel if isinstance(rel, dict) else None


def forecast_2025(state: str | None = None) -> dict:
    """The team's submitted 2025 forecast of corn acres harvested for silage and for grain (the graded
    2025 estimate): use it for any question about the 2025 estimate, forecast or how sure we are. Returns
    the US and one state (default MARYLAND): estimate, SE, CV%, 95% low/high, the method, the NASS-style
    margin of error, and NASS's final 2025 acres for comparison when available. Acres, not BARC fields."""
    name = (state or 'MARYLAND').strip().upper()
    if name in ('US', 'USA', 'U.S.', 'UNITED STATES', 'US TOTAL'):
        name = 'MARYLAND'  # the US row is always returned; Maryland is the default state beside it
    data = artifacts.read_forecast_2025()
    summary = data.summary.model_dump()
    rows = {s['state']: s for s in summary['states']}
    if name not in rows:
        return {'error': f'no 2025 forecast for state {name!r}; available: {sorted(rows)}'}
    whole = lambda v: int(v) if isinstance(v, float) and v.is_integer() else v  # noqa: E731  (36648, not 36648.0)
    pick = lambda row: {k: whole(row[k]) for k in _FORECAST_KEYS if row.get(k) is not None}  # noqa: E731
    out = {'year': 2025, 'unit': 'acres harvested', 'note': FORECAST_NOTE,
           'us': pick(summary['us']), 'state': name, name.lower(): pick(rows[name]),
           'interval': '95% range = estimate +/- z SE (see method)', 'method': summary['method']}
    nass = data.nass_2025.model_dump() if data.nass_2025 else None
    if nass:
        finals = {'source': nass['source'], 'us': nass['us']}
        if name == 'MARYLAND':
            finals['maryland'] = nass['maryland']
        out['nass_2025_final'] = finals
    else:
        out['nass_2025_final'] = 'not available (the NASS 2025 reference file could not be read)'
    rel = _reliability()
    if rel:
        out['margin_of_error'] = {'what': ('NASS-style margin of error of the US totals: rmse_pct is the root mean '
                                           'square backtest % error over the years shown; margin90_pct is the 90% '
                                           'margin of error in percent'), **rel}
    return out


def decline_rule_baseline() -> dict:
    """The organizers' NDVI decline-date rule compared with our model on the same BARC field-years:
    balanced accuracy, silage precision/recall, false positive rate and confusion matrices for the rule,
    our logistic model and always-Grain, overall and by year. Season-end only (scored on BARC labels)."""
    out = artifacts.read_decline_rule().model_dump()
    out['scope'] = ('Season-end comparison scored against the BARC Grain/Silage reference labels; all three rows '
                    'use the same labeled field-years. Confusion matrices: rows = true class, columns = predicted, '
                    'order [Grain, Silage].')
    return out


AGENT_TOOLS = {**core.TOOLS, 'classify': classify, 'evaluate': evaluate, 'aggregate': aggregate,
               'forecast_2025': forecast_2025, 'decline_rule_baseline': decline_rule_baseline}


def _schema(name, fn):
    fields = {}
    for param in inspect.signature(fn).parameters.values():
        default = ... if param.default is inspect.Parameter.empty else param.default
        fields[param.name] = (param.annotation, default)
    return create_model(f'{name}_args', __config__=ConfigDict(extra='forbid', strict=True), **fields)


SCHEMAS = {name: _schema(name, fn) for name, fn in AGENT_TOOLS.items()}


def call(name: str, args: dict | None = None) -> dict:
    """Run an agent tool by name; never raises."""
    fn = AGENT_TOOLS.get(name)
    if fn is None:
        return {'error': f'unknown tool {name!r}; available: {sorted(AGENT_TOOLS)}'}
    try:
        validated = SCHEMAS[name].model_validate({} if args is None else args)
        return fn(**validated.model_dump())
    except (ArtifactUnavailable, RuntimeError) as exc:
        return {'error': str(exc)}
    except (TypeError, ValueError, ValidationError) as exc:
        return {'error': f'bad arguments for {name}: {exc}'}


def _wrap(name: str, fn) -> StructuredTool:
    schema = SCHEMAS[name]

    def run(**kwargs) -> str:
        args = {k: v for k, v in kwargs.items() if v is not None}
        return json.dumps(call(name, args), default=str)

    return StructuredTool.from_function(func=run, name=name, args_schema=schema,
        description=inspect.getdoc(fn) or name, handle_validation_error=True)


TOOLS = [_wrap(name, fn) for name, fn in AGENT_TOOLS.items()]
