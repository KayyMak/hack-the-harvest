"""Run from backend/: python -m uvicorn app.main:app --reload."""
from fastapi import FastAPI, HTTPException

from .artifacts import ArtifactUnavailable, read_predictions, read_summary
from .schemas import BaselineSummary, Prediction

app = FastAPI(title='Hack the Harvest API', version='0.1.0',
    description='Read-only access to saved, field-held-out BARC baseline results.')


@app.get('/api/health')
def health() -> dict[str, str]:
    return {'status': 'ok'}


@app.get('/api/baseline/summary', response_model=BaselineSummary)
def summary() -> BaselineSummary:
    try:
        return read_summary()
    except ArtifactUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get('/api/baseline/predictions', response_model=list[Prediction])
def predictions() -> list[Prediction]:
    try:
        return read_predictions()
    except ArtifactUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
