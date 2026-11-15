"""Run from backend/: python -m uvicorn app.main:app --reload."""
import sys
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from .artifacts import (ArtifactUnavailable, compute_rollup, read_asof, rollup_quickstats_csv, read_fields, read_fields_geojson,
    read_estimate_2025, read_observations,
    read_predictions, read_quickstats, read_summary)
from . import tools
from .frontend import mount_first_build
from .schemas import AsOfResults, BaselineSummary, BarcField, Estimate2025, Observation, Prediction, QuickStatsRow, Rollup

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


@app.get('/api/baseline/asof', response_model=AsOfResults)
def asof(year: int | None = None) -> AsOfResults:
    """Saved mid-season calls per year and release date, plus scores pooled over the years.
    Read from baseline/outputs/asof.json; nothing is fitted in this request."""
    data = _serve(read_asof)
    if year is None:
        return data
    entries = [entry for entry in data.dates if entry.year == year]
    if not entries:
        raise HTTPException(status_code=404, detail=f'No saved as-of results for year {year}.')
    return data.model_copy(update={'dates': entries})


@app.get('/api/baseline/rollup', response_model=Rollup)
def rollup() -> Rollup:
    return _serve(compute_rollup)


@app.get('/api/baseline/rollup.csv', response_class=PlainTextResponse)
def rollup_csv() -> PlainTextResponse:
    """Roll-up in QuickStats column shape, for download."""
    return PlainTextResponse(_serve(rollup_quickstats_csv), media_type='text/csv',
        headers={'Content-Disposition': 'attachment; filename="quickstats_export.csv"'})


# Optional keys the saved file does not carry are left out of the response, not sent as null.
@app.get('/api/estimate_2025', response_model=Estimate2025, response_model_exclude_unset=True)
def estimate_2025() -> Estimate2025:
    """Saved 2025 Maryland silage/grain acre estimate from a sample of corn fields, next to
    NASS survey acres harvested. A model estimate, not a USDA/NASS release. 503 until saved."""
    return _serve(read_estimate_2025)


@app.get('/api/fields.geojson')
def fields_geojson() -> dict:
    """All BARC field polygons as GeoJSON (EPSG:4326) with reference labels per year.
    Join model predictions from /api/baseline/predictions on field_id and year."""
    return _serve(read_fields_geojson)


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
def quickstats(state: str = 'MARYLAND', year: int | None = None, crop_use: str | None = None,
               level: str | None = None) -> list[QuickStatsRow]:
    """Lab QuickStats rows (domain TOTAL). Filter by year, crop_use (grain|silage), level (STATE|COUNTY)."""
    return _serve(read_quickstats, state, year, crop_use, level)


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
    run_id = f'r-{uuid4().hex}'
    background.add_task(run_agent, request.query, run_id)
    return {'run_id': run_id}


@app.get('/api/agent/trace/{run_id}')
def agent_trace(run_id: str) -> list[dict]:
    """Trace lines written so far for a run; empty while the run has not logged anything."""
    try:
        return tools.read_trace(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ArtifactUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


# Keep this last so API routes take precedence over static files.
# Cutline (web/) is the hosted dashboard; the original frontend/ build is the fallback.
mount_first_build(app, [tools.artifacts.ROOT / 'web' / 'dist', tools.artifacts.ROOT / 'frontend' / 'dist'])
