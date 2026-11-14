"""Agent tool library over saved outputs. No network, no model fitting, no new dependencies.

Usage from the agent (repo root on sys.path, backend/ on sys.path):
    from app.tools import TOOL_SPECS, call_tool, log_step
    TOOL_SPECS  -> OpenAI-style function specs (works with Nemotron on build.nvidia.com)
    call_tool(name, args_dict) -> JSON-safe dict; failures come back as {"error": ...}
    log_step(run_id, node=..., ...) -> appends one line to the run's trace.jsonl
LangChain users can wrap each entry of TOOLS with StructuredTool.from_function.
"""
import csv
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from . import artifacts
from .artifacts import ArtifactUnavailable

RUNS_DIR = Path(os.environ.get('AGENT_RUNS_DIR', artifacts.ROOT / 'agent_runs'))
CHIPS_DIR = artifacts.OUTPUT_DIR / 'chips'
RUN_ID = re.compile(r'^[A-Za-z0-9_.-]{1,64}$')


def _check_run_id(run_id: str) -> str:
    if not RUN_ID.match(run_id or ''):
        raise ValueError('run_id must be 1-64 letters, digits, dot, dash or underscore')
    return run_id


def get_fields() -> dict:
    """List all BARC fields with farm, field name and acres."""
    rows = [f.model_dump() for f in artifacts.read_fields()]
    return {'n_fields': len(rows), 'fields': rows}


def get_timeseries(field_id: int, year: int) -> dict:
    """Per-scene NDVI and clear fraction for one field-year, with counts of usable and rejected scenes."""
    rows = [o.model_dump() for o in artifacts.read_observations(field_id, year)]
    if not rows:
        return {'error': f'no saved observations for field {field_id} in {year}'}
    ok = [r for r in rows if r['status'] == 'ok']
    return {'field_id': field_id, 'year': year, 'n_scenes': len(rows), 'n_usable': len(ok),
            'n_rejected': len(rows) - len(ok), 'observations': rows}


def classify(year: int | None = None, field_ids: list[int] | None = None) -> dict:
    """Saved held-out predictions (label, silage probability, fold, usable dates) with the
    feature values behind each call. Reference labels are returned separately as reference_label."""
    feats = {}
    try:
        with (artifacts.OUTPUT_DIR / 'heldout_predictions.csv').open(encoding='utf-8', newline='') as f:
            for r in csv.DictReader(f):
                feats[(int(r['OBJECTID']), int(r['year']))] = {
                    k: artifacts._num(r.get(k)) for k in ('ndvi_08', 'ndvi_09', 'ndvi_10', 'peak_doy',
                                                          'late_ndvi', 'early_minus_late')}
    except OSError:
        pass
    rows = []
    for p in artifacts.read_predictions():
        if year is not None and p.year != year:
            continue
        if field_ids and p.field_id not in field_ids:
            continue
        rows.append({**p.model_dump(), 'evidence': feats.get((p.field_id, p.year), {})})
    return {'model': 'logistic regression, held out by field (saved)', 'n': len(rows), 'predictions': rows}


def evaluate(year: int | None = None) -> dict:
    """Held-out metrics vs always-Grain. Overall from metrics.json; per year computed from saved predictions."""
    preds = [p for p in artifacts.read_predictions() if year is None or p.year == year]
    tp = sum(p.reference_label == 'Silage' and p.predicted_label == 'Silage' for p in preds)
    fn = sum(p.reference_label == 'Silage' and p.predicted_label == 'Grain' for p in preds)
    fp = sum(p.reference_label == 'Grain' and p.predicted_label == 'Silage' for p in preds)
    tn = sum(p.reference_label == 'Grain' and p.predicted_label == 'Grain' for p in preds)
    rec = tp / (tp + fn) if tp + fn else None
    spec = tn / (tn + fp) if tn + fp else None
    out = {'year': year, 'n': len(preds), 'confusion_matrix': [[tn, fp], [fn, tp]],
           'matrix_order': ['Grain', 'Silage'], 'silage_recall': rec,
           'silage_precision': tp / (tp + fp) if tp + fp else None,
           'balanced_accuracy': (rec + spec) / 2 if rec is not None and spec is not None else None,
           'always_grain_balanced_accuracy': 0.5}
    if year is None:
        s = artifacts.read_summary()
        out.update(protocol=s.protocol, logistic=s.logistic.model_dump(), always_grain=s.always_grain.model_dump())
    return out


def aggregate(year: int | None = None) -> dict:
    """Silage acre roll-up with 95% interval next to reference silage acres, per year."""
    r = artifacts.compute_rollup().model_dump()
    if year is not None:
        r['years'] = [y for y in r['years'] if y['year'] == year]
    return r


def get_quickstats(state: str = 'MARYLAND', year: int | None = None) -> dict:
    """NASS QuickStats corn rows for a state; suppressed values are null, never zero."""
    rows = [q.model_dump() for q in artifacts.read_quickstats(state)
            if year is None or q.year == year]
    return {'state': state, 'year': year, 'n': len(rows), 'rows': rows}


def get_chip(field_id: int, year: int) -> dict:
    """Paths of pre/post-harvest image chips for a field-year, if they have been exported."""
    out = {}
    for which in ('pre', 'post'):
        p = CHIPS_DIR / f'{field_id}_{year}_{which}.png'
        out[which] = {'path': str(p.relative_to(artifacts.ROOT)), 'exists': p.exists()}
    return out


def write_report(run_id: str, markdown: str) -> dict:
    """Save the agent's final markdown report for a run."""
    p = RUNS_DIR / _check_run_id(run_id) / 'report.md'
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(markdown, encoding='utf-8')
    return {'path': str(p), 'bytes': len(markdown.encode())}


def log_step(run_id: str, **fields) -> dict:
    """Append one trace line ({ts, run_id, step, ...}) to agent_runs/<run_id>/trace.jsonl."""
    p = RUNS_DIR / _check_run_id(run_id) / 'trace.jsonl'
    p.parent.mkdir(parents=True, exist_ok=True)
    step = sum(1 for _ in p.open(encoding='utf-8')) + 1 if p.exists() else 1
    line = {'ts': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'run_id': run_id,
            'step': step, **fields}
    with p.open('a', encoding='utf-8') as f:
        f.write(json.dumps(line, default=str) + '\n')
    return line


def read_trace(run_id: str) -> list[dict]:
    p = RUNS_DIR / _check_run_id(run_id) / 'trace.jsonl'
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding='utf-8').splitlines() if l.strip()]


_INT, _STR = {'type': 'integer'}, {'type': 'string'}
_PARAMS = {
    'get_fields': ({}, []),
    'get_timeseries': ({'field_id': _INT, 'year': _INT}, ['field_id', 'year']),
    'classify': ({'year': _INT, 'field_ids': {'type': 'array', 'items': _INT}}, []),
    'evaluate': ({'year': _INT}, []),
    'aggregate': ({'year': _INT}, []),
    'get_quickstats': ({'state': _STR, 'year': _INT}, []),
    'get_chip': ({'field_id': _INT, 'year': _INT}, ['field_id', 'year']),
    'write_report': ({'run_id': _STR, 'markdown': _STR}, ['run_id', 'markdown']),
}
TOOLS = {f.__name__: f for f in (get_fields, get_timeseries, classify, evaluate, aggregate,
                                 get_quickstats, get_chip, write_report)}
TOOL_SPECS = [{'type': 'function', 'function': {
    'name': name, 'description': (fn.__doc__ or '').strip().replace('\n', ' '),
    'parameters': {'type': 'object', 'properties': _PARAMS[name][0], 'required': _PARAMS[name][1]}}}
    for name, fn in TOOLS.items()]


def call_tool(name: str, args: dict | None = None) -> dict:
    """Run a tool by name. Never raises: unknown tools, bad arguments and missing data return {'error': ...}."""
    fn = TOOLS.get(name)
    if fn is None:
        return {'error': f'unknown tool {name!r}; available: {sorted(TOOLS)}'}
    try:
        return fn(**(args or {}))
    except ArtifactUnavailable as exc:
        return {'error': str(exc)}
    except (TypeError, ValueError) as exc:
        return {'error': f'bad arguments for {name}: {exc}'}
