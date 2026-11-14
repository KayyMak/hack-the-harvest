"""Run from backend/: python -m uvicorn app.main:app --reload."""
import sys
import time

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from .artifacts import (ArtifactUnavailable, compute_rollup, rollup_quickstats_csv, read_fields, read_observations,
    read_predictions, read_quickstats, read_summary)
from . import tools
from .schemas import BaselineSummary, BarcField, Observation, Prediction, QuickStatsRow, Rollup

app = FastAPI(title='Hack the Harvest API', version='0.1.0',
    description='Read-only access to saved, field-held-out BARC baseline results.')


@app.get('/api/health')
def health() -> dict[str, str]:
    return {'status': 'ok'}


def _serve(read, *args):
    try:
        return read(*args)
    except ArtifactUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get('/api/baseline/summary', response_model=BaselineSummary)
def summary() -> BaselineSummary:
    return _serve(read_summary)


@app.get('/api/baseline/predictions', response_model=list[Prediction])
def predictions() -> list[Prediction]:
    return _serve(read_predictions)


@app.get('/api/baseline/rollup', response_model=Rollup)
def rollup() -> Rollup:
    return _serve(compute_rollup)


@app.get('/api/baseline/rollup.csv', response_class=PlainTextResponse)
def rollup_csv() -> PlainTextResponse:
    """Roll-up in QuickStats column shape, for download."""
    return PlainTextResponse(_serve(rollup_quickstats_csv), media_type='text/csv',
        headers={'Content-Disposition': 'attachment; filename="quickstats_export.csv"'})


@app.get('/api/fields', response_model=list[BarcField])
def fields() -> list[BarcField]:
    return _serve(read_fields)


@app.get('/api/fields/{field_id}/observations', response_model=list[Observation])
def observations(field_id: int, year: int) -> list[Observation]:
    rows = _serve(read_observations, field_id, year)
    if not rows:
        raise HTTPException(status_code=404, detail='No saved observations for this field-year.')
    return rows


@app.get('/api/quickstats', response_model=list[QuickStatsRow])
def quickstats(state: str = 'MARYLAND') -> list[QuickStatsRow]:
    return _serve(read_quickstats, state)


class AgentRequest(BaseModel):
    query: str


@app.post('/api/agent/run')
def agent_run(request: AgentRequest, background: BackgroundTasks) -> dict[str, str]:
    """Start agent.run.run_agent(query, run_id) in the background; poll the trace route."""
    root = str(tools.artifacts.ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    try:
        from agent.run import run_agent
    except ImportError as exc:
        raise HTTPException(status_code=501, detail='Agent is not installed yet (agent.run.run_agent).') from exc
    run_id = time.strftime('r-%Y%m%d-%H%M%S')
    background.add_task(run_agent, request.query, run_id)
    return {'run_id': run_id}


@app.get('/api/agent/trace/{run_id}')
def agent_trace(run_id: str) -> list[dict]:
    """Trace lines written so far for a run; empty while the run has not logged anything."""
    try:
        return tools.read_trace(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
