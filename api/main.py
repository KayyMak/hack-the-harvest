"""FastAPI backend. Run: uvicorn api.main:app --host 0.0.0.0 --port 8000
Data folder comes from HANDOFF_DIR (default /workspace/data/handoff).
"""
from __future__ import annotations

import json
import uuid
from datetime import date

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from contracts.schemas import SchemaError
from harvest import io, tools

app = FastAPI(title="Silage or Grain API", version="0.1")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class PredictReq(BaseModel):
    year: int
    as_of: date
    source: str = "auto"  # auto | ml | baseline


class AgentReq(BaseModel):
    question: str = "Classify all fields for the year and check the silage total against NASS."
    year: int = 2022
    as_of: date = date(2022, 10, 12)


def _guard(fn, *a, **k):
    """Turn missing hand-offs / schema problems into clear HTTP errors, not 500s."""
    try:
        return fn(*a, **k)
    except FileNotFoundError as e:
        raise HTTPException(503, f"hand-off not ready: {e}")
    except SchemaError as e:
        raise HTTPException(422, f"schema violation: {e}")


@app.get("/health")
def health():
    return {"ok": True, "handoff_dir": str(io.handoff_dir()), "files": io.status()}


@app.get("/fields")
def fields():
    return _guard(tools.get_fields)


@app.get("/fields/{objectid}/timeseries")
def timeseries(objectid: int, year: int):
    return _guard(tools.get_timeseries, objectid, year)


@app.get("/fields/{objectid}/chips/{year}/{which}")
def chip(objectid: int, year: int, which: str):
    if which not in ("pre", "post"):
        raise HTTPException(400, "which must be pre or post")
    p = io.chip_path(objectid, year, which)
    if not p.exists():
        raise HTTPException(404, "chip not available")
    return FileResponse(p, media_type="image/png")


@app.post("/predict")
def predict(req: PredictReq):
    return _guard(tools.classify, req.year, req.as_of.isoformat(), req.source)


@app.get("/evaluate")
def evaluate(year: int | None = None, as_of: date | None = None, source: str = "auto"):
    if year and as_of:
        preds = _guard(tools.classify, year, as_of.isoformat(), source)
        return _guard(tools.evaluate, preds, year)
    saved = io.read_json("metrics.json")
    if saved:
        return saved
    raise HTTPException(400, "pass year and as_of, or provide metrics.json")


@app.get("/rollup")
def rollup(year: int, as_of: date, source: str = "auto", state: str = "MARYLAND"):
    preds = _guard(tools.classify, year, as_of.isoformat(), source)
    out = _guard(tools.aggregate, preds)
    try:
        out["nass"] = tools.get_quickstats(state, year)
    except FileNotFoundError:
        out["nass"] = None
    return out


@app.get("/quickstats")
def quickstats(state: str = "MARYLAND", year: int | None = None):
    return _guard(tools.get_quickstats, state, year)


@app.post("/agent/run")
def agent_run(req: AgentReq):
    """Delegates to agent.run(question, year, as_of, run_id) owned by the agent role."""
    try:
        from agent import run as agent_run_fn  # provided by agent/ (not backend)
    except ImportError:
        raise HTTPException(501, "agent not installed yet (agent.run missing)")
    run_id = uuid.uuid4().hex[:12]
    result = agent_run_fn(req.question, req.year, req.as_of.isoformat(), run_id=run_id)
    return {"run_id": run_id, "result": result}


@app.get("/agent/trace/{run_id}")
def agent_trace(run_id: str):
    p = io.handoff_dir() / "trace.jsonl"
    if not p.exists():
        raise HTTPException(404, "no trace.jsonl yet")
    steps = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    steps = [s for s in steps if s.get("run_id") == run_id]
    if not steps:
        raise HTTPException(404, f"no steps for run_id {run_id}")
    return steps
