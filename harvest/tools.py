"""LangChain tool wrappers for the agent: `from harvest.tools import TOOLS`.

Same eight tools as backend/app/tools.py. classify, evaluate and aggregate also take an
optional as_of date (YYYY-MM-DD): the model then only sees satellite months complete by
that date (see harvest/asof.py). Results are JSON strings; failures come back as
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


AGENT_TOOLS = {**core.TOOLS, 'classify': classify, 'evaluate': evaluate, 'aggregate': aggregate}


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
