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
| `GET /api/baseline/rollup` | Per-year acres: reference silage, predicted silage, expected silage with 95% interval (labeled field-years only) |
| `GET /api/fields` | Field ID, farm, field name, acres from the source GeoPackage (read-only, no geometry) |
| `GET /api/fields/{id}/observations?year=` | Saved per-scene NDVI, clear fraction, cloud percent, status; 404 if none |
| `GET /api/quickstats?state=` | NASS QuickStats rows from optional `QUICKSTATS_CSV`; suppressed values are null; 503 if unset |
| `GET /docs` | Interactive generated API documentation |
| `GET /openapi.json` | Machine-readable response schemas |

Python models in `backend/app/schemas.py` are authoritative. TypeScript shapes
in `frontend/src/api.ts` mirror them. Test response changes at both ends.
Field ID maps to source `OBJECTID`; `(field_id, year)` identifies a prediction.
Silage is the positive class. Matrices are true rows / predicted columns,
ordered Grain then Silage.

## Deliberate limits

There is no database, login, deployment configuration, uploaded-AOI inference,
model-serving endpoint, or asynchronous worker. The current task needs a shared
working foundation for existing results. Add those components when a concrete
feature needs persistence, controlled access, deployment, or long-running jobs.
The Vite proxy is for local development; a deployed frontend will need an API
route/reverse proxy selected with its hosting setup.
