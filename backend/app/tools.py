"""Agent tool library over saved outputs. No network, no model fitting, no new dependencies.

Usage from the agent (repo root on sys.path, backend/ on sys.path):
    from app.tools import TOOL_SPECS, call_tool, log_step
    TOOL_SPECS  -> OpenAI-style function specs (works with Nemotron on build.nvidia.com)
    call_tool(name, args_dict) -> JSON-safe dict; failures come back as {"error": ...}
    log_step(run_id, node=..., type=..., ...) -> appends one line to <TRACES_DIR>/<run_id>.jsonl
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
_HANDOFF_TRACES = Path('/workspace/data/handoff/traces')
# Same folder agent/trace.py writes to: <dir>/<run_id>.jsonl
TRACES_DIR = Path(os.environ.get('AGENT_TRACES_DIR')
                  or (_HANDOFF_TRACES if _HANDOFF_TRACES.parent.exists() else RUNS_DIR / 'traces'))
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
    return classify_predictions(artifacts.read_predictions(), year, field_ids,
                                'logistic regression, held out by field (saved)')


def classify_predictions(predictions, year: int | None = None, field_ids: list[int] | None = None,
                         model: str = '', only: list[str] | None = None) -> dict:
    """classify() on any list of Prediction objects (used for as-of runs). `only` limits the
    evidence to the features the model actually saw, so an as-of call never shows later months."""
    feats = {}
    try:
        features = json.loads((artifacts.OUTPUT_DIR / 'metrics.json').read_text(encoding='utf-8'))['features']
        if not isinstance(features, list) or not features or not all(isinstance(f, str) for f in features):
            raise ValueError('Invalid model feature list')
        if only is not None:
            features = [f for f in features if f in only]
        with (artifacts.OUTPUT_DIR / 'heldout_predictions.csv').open(encoding='utf-8', newline='') as f:
            for r in csv.DictReader(f):
                feats[(int(r['OBJECTID']), int(r['year']))] = {
                    k: artifacts._num(r[k]) for k in features}
    except (OSError, KeyError, ValueError, TypeError) as exc:
        raise ArtifactUnavailable('Saved prediction feature evidence is missing or invalid.') from exc
    rows = []
    for p in predictions:
        if year is not None and p.year != year:
            continue
        if field_ids and p.field_id not in field_ids:
            continue
        rows.append({**p.model_dump(), 'evidence': feats.get((p.field_id, p.year), {})})
    return {'model': model, 'n': len(rows), 'predictions': rows}


def wilson(successes: int, n: int, z: float = 1.96) -> list[float] | None:
    """Wilson score interval for a proportion; None when n is 0."""
    if n == 0:
        return None
    phat = successes / n
    centre = (phat + z * z / (2 * n)) / (1 + z * z / n)
    half = z * ((phat * (1 - phat) / n + z * z / (4 * n * n)) ** 0.5) / (1 + z * z / n)
    return [round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4)]


def evaluate(year: int | None = None) -> dict:
    """Held-out metrics vs always-Grain, with Wilson 95% intervals on precision and recall for
    both classes. Overall adds the saved metrics.json; per year is computed from saved predictions."""
    return evaluate_predictions(artifacts.read_predictions(), year)


def evaluate_predictions(predictions, year: int | None = None) -> dict:
    """evaluate() on any list of Prediction objects (used by the one command for as-of runs)."""
    preds = [p for p in predictions if year is None or p.year == year]
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
           'always_grain_balanced_accuracy': 0.5,
           'per_class': {
               'Silage': {'precision': tp / (tp + fp) if tp + fp else None, 'precision_95ci': wilson(tp, tp + fp),
                          'recall': rec, 'recall_95ci': wilson(tp, tp + fn), 'n_reference': tp + fn},
               'Grain': {'precision': tn / (tn + fn) if tn + fn else None, 'precision_95ci': wilson(tn, tn + fn),
                         'recall': spec, 'recall_95ci': wilson(tn, tn + fp), 'n_reference': tn + fp}},
           'counts_by_year_and_class': _counts(preds)}
    if year is None:
        s = artifacts.read_summary()
        out.update(protocol=s.protocol, logistic=s.logistic.model_dump(), always_grain=s.always_grain.model_dump())
    return out


def _counts(preds) -> dict:
    out: dict[str, dict[str, int]] = {}
    for p in preds:
        row = out.setdefault(str(p.year), {'Grain': 0, 'Silage': 0})
        row[p.reference_label] += 1
    return out


def aggregate(year: int | None = None) -> dict:
    """Silage acre roll-up with 95% interval next to reference silage acres, per year."""
    r = artifacts.compute_rollup().model_dump()
    if year is not None:
        r['years'] = [y for y in r['years'] if y['year'] == year]
    return r


def get_quickstats(state: str = 'MARYLAND', year: int | None = None, crop_use: str | None = None,
                   level: str | None = None) -> dict:
    """NASS QuickStats corn acres (domain TOTAL) for a state; crop_use is grain or silage, level is
    STATE or COUNTY. Suppressed values are null, never zero."""
    rows = [q.model_dump() for q in artifacts.read_quickstats(state, year, crop_use, level)]
    return {'state': state, 'year': year, 'crop_use': crop_use, 'level': level, 'n': len(rows), 'rows': rows}


def get_chip(field_id: int, year: int) -> dict:
    """Paths of pre/post-harvest image chips for a field-year, if they have been exported."""
    out = {}
    for which in ('pre', 'post'):
        p = CHIPS_DIR / f'{field_id}_{year}_{which}.png'
        out[which] = {'path': str(p.relative_to(artifacts.ROOT)), 'exists': p.exists()}
    return out


def write_report(run_id: str, markdown: str) -> dict:
    """Save the agent's final markdown report for a run."""
    p = RUNS_DIR / 'reports' / f'{_check_run_id(run_id)}.md'
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(markdown, encoding='utf-8')
    return {'path': str(p), 'bytes': len(markdown.encode())}


def log_step(run_id: str, **fields) -> dict:
    """Append one trace line ({run_id, step, ts, node, type, ...}) to <TRACES_DIR>/<run_id>.jsonl,
    the same file and format as agent/trace.py."""
    p = TRACES_DIR / f'{_check_run_id(run_id)}.jsonl'
    p.parent.mkdir(parents=True, exist_ok=True)
    step = len(p.read_text(encoding='utf-8').splitlines()) + 1 if p.exists() else 1
    line = {**fields, 'run_id': run_id, 'step': step,
            'ts': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}
    with p.open('a', encoding='utf-8') as f:
        f.write(json.dumps(line, default=str) + '\n')
    return line


def read_trace(run_id: str) -> list[dict]:
    """Read complete records; an unfinished final JSON record waits for the next poll."""
    p = TRACES_DIR / f'{_check_run_id(run_id)}.jsonl'
    try:
        lines = p.read_text(encoding='utf-8').splitlines(keepends=True)
    except FileNotFoundError:
        return []
    except (OSError, UnicodeError) as exc:
        raise ArtifactUnavailable('Agent trace cannot be read.') from exc
    records = []
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            if index == len(lines) - 1 and not line.endswith(('\n', '\r')):
                break
            raise ArtifactUnavailable('Agent trace contains a corrupt record.') from exc
        if not isinstance(record, dict):
            raise ArtifactUnavailable('Agent trace contains a non-object record.')
        records.append(record)
    return records


_INT, _STR = {'type': 'integer'}, {'type': 'string'}
_PARAMS = {
    'get_fields': ({}, []),
    'get_timeseries': ({'field_id': _INT, 'year': _INT}, ['field_id', 'year']),
    'classify': ({'year': _INT, 'field_ids': {'type': 'array', 'items': _INT}}, []),
    'evaluate': ({'year': _INT}, []),
    'aggregate': ({'year': _INT}, []),
    'get_quickstats': ({'state': _STR, 'year': _INT, 'crop_use': {'type': 'string', 'enum': ['grain', 'silage']},
                        'level': {'type': 'string', 'enum': ['STATE', 'COUNTY']}}, []),
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
