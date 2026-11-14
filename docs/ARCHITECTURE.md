# Current architecture

```text
Source BARC polygons + labels     Public Sentinel-2 L2A COGs
              \                  /
              baseline/run_baseline.py (offline CLI workflow)
                     |
         baseline/cache/ and baseline/outputs/
                     |
      backend/app/artifacts.py (read + validate)
                     |
      backend/app/main.py (FastAPI, localhost:8000)
                     |
           /api via Vite development proxy
                     |
      frontend/src/api.ts -> App.tsx (localhost:5173)
```

## Ownership

**Analysis** owns satellite access, masking/calibration, feature extraction,
reference-label handling, grouped model evaluation, and generated artifacts.
It can run independently of the app. The existing command-line workflow is
preserved instead of moving it while teammates start work.

**Backend** owns the HTTP contract and reads versioned analysis outputs, the
source GeoPackage field table (read-only via SQLite), and an optional QuickStats CSV.
Pydantic validates public responses. Missing or invalid artifacts yield HTTP 503
with a clear message. Health indicates the API process is alive; it does not
claim that baseline artifacts exist. There are no writes, training jobs, or
live satellite requests in the API.

**Frontend** owns rendering and loading/error states. It uses relative `/api`
URLs through one HTTP client. It displays saved held-out predictions, not
fresh inference. Reference labels, model labels, and estimated probabilities
are separate fields.

## API contract

| Method and path | Response |
| --- | --- |
| `GET /api/health` | `{"status": "ok"}` |
| `GET /api/baseline/summary` | Evaluation counts, quality counts, logistic and always-Grain metrics |
| `GET /api/baseline/predictions` | List of field ID, year, reference/predicted labels, probability, fold, valid dates |
| `GET /api/baseline/rollup` | Per-year acres: reference silage, predicted silage, expected silage with 95% interval and CV%, and the misclassification-adjusted share (q - FPR)/(TPR - FPR) using rates from the other years (labeled field-years only) |
| `GET /api/baseline/rollup.csv` | The roll-up in the lab QuickStats file's exact columns (`value`, `cv_percent`, ...), as a CSV download |
| `GET /api/fields` | Field ID, farm, field name, acres from the source GeoPackage (read-only, no geometry) |
| `GET /api/fields/{id}/observations?year=` | Saved per-scene NDVI, clear fraction, cloud percent, status; 404 if none |
| `GET /api/quickstats?state=&year=&crop_use=&level=` | Lab QuickStats rows (domain TOTAL) from optional `QUICKSTATS_CSV`, with value, `cv_percent`, source; suppressed `(D)` values are null; 503 if unset |
| `POST /api/agent/run` `{query}` | `{run_id}`; starts `agent.run.run_agent(query, run_id)` in the background; 501 until the agent exists |
| `GET /api/agent/trace/{run_id}` | Trace lines logged so far from `<traces>/<run_id>.jsonl` (the folder `agent/trace.py` writes; `/workspace/data/handoff/traces` on Keeboh, `agent_runs/traces` locally, or `AGENT_TRACES_DIR`); `[]` before the first step |
| `GET /docs` | Interactive generated API documentation |
| `GET /openapi.json` | Machine-readable response schemas |

Python models in `backend/app/schemas.py` are authoritative. TypeScript shapes
in `frontend/src/api.ts` mirror them. Test response changes at both ends.
Field ID maps to source `OBJECTID`; `(field_id, year)` identifies a prediction.
Silage is the positive class. Matrices are true rows / predicted columns,
ordered Grain then Silage.

## Agent tools

`backend/app/tools.py` exposes eight read-only tools over saved outputs
(`get_fields`, `get_timeseries`, `classify`, `evaluate`, `aggregate`,
`get_quickstats`, `get_chip`, `write_report`) as OpenAI-style `TOOL_SPECS` and
a `call_tool(name, args)` dispatcher that returns `{"error": ...}` instead of
raising. `log_step(run_id, ...)` writes the trace the UI polls. `harvest/tools.py`
wraps the same tools as LangChain tools (`from harvest.tools import TOOLS`)
for the LangGraph agent. Traces and reports are the only writes, and are not
committed. `evaluate` adds Wilson 95% intervals for precision and recall of
both classes and counts by year and class.

## One command

```sh
python -m harvest.run --year 2022 --as-of 2022-10-12 --out runs/2022-10-12
```

Writes `predictions.csv`, `metrics.json`, `rollup.json`, `quickstats_export.csv`
(the lab QuickStats file's columns) and `run.json`. An as-of date uses only the
monthly NDVI medians complete by then: before Nov 30 the baseline's logistic
pipeline is refit on the saved field folds with those features (needs
scikit-learn); from Nov 30 the saved predictions are used; before Jul 31 every
field is Pending. This is a command-line step, not an API route.

## Deliberate limits

There is no database, login, deployment configuration, uploaded-AOI inference,
model-serving endpoint, or asynchronous worker. The current task needs a shared
working foundation for existing results. Add those components when a concrete
feature needs persistence, controlled access, deployment, or long-running jobs.
The Vite proxy is for local development; a deployed frontend will need an API
route/reverse proxy selected with its hosting setup.
