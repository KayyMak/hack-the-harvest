"""Run from backend/: python -m uvicorn app.main:app --reload."""
from fastapi import FastAPI, HTTPException

from .artifacts import (ArtifactUnavailable, compute_rollup, read_fields, read_observations,
    read_predictions, read_quickstats, read_summary)
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
