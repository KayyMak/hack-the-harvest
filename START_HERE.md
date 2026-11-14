# Hack the Harvest: teammate setup

Start here for the application scaffold. The original README, source notebooks,
and data files are preserved. Read [AGENTS.md](AGENTS.md) before using an AI
coding tool in this repository.

## What works now

- A React + TypeScript frontend displays real, saved BARC model metrics,
  observation quality, a confusion matrix, and held-out field-year predictions.
- A FastAPI backend reads the saved outputs without downloading satellite data
  or importing the geospatial/modeling packages.
- `baseline/` contains the working satellite extraction and logistic regression
  experiment, numerical caches, reference labels, and reproducible results.
- No API keys or environment variables are needed for local development.

## Repository layout

```text
frontend/                React/TypeScript app (Vite)
  src/api.ts             HTTP client and matching TypeScript response types
  src/App.tsx            Initial results screen
backend/                 Python API
  app/main.py            HTTP routes
  app/schemas.py         Public response models / OpenAPI contract
  app/artifacts.py       Read-only access to baseline output files
  tests/                 API contract and failure-path checks
baseline/                Satellite extraction, modeling, caches, results
docs/                    Architecture and model review
scripts/                 Local frontend/API integration smoke check
.github/workflows/       Frontend build and backend test checks
AGENTS.md                Instructions for AI coding assistants
CONTRIBUTING.md          Team workflow and commit conventions
```

Source notebooks, `BARC_Corn.2021-2023.gpkg`, `field_aoi.geojson`, and
`data_sources.md` remain at the project root. Numerical caches and small result
artifacts are versioned so a fresh clone works offline after package setup.
Local runtimes, virtual environments, node_modules, credentials, and frontend
build products are ignored by Git.

## Prerequisites

Use **Python 3.12** and **Node.js 22.12+** (Node 24 is also supported).
The app requires no database, Docker, cloud account, or geospatial installation.
The analysis pipeline has its own heavier requirements in `baseline/`.
Frontend versions are locked in `frontend/package-lock.json`; tested backend
and test dependency versions are pinned in `backend/constraints.txt`.

## Windows / PowerShell

From the project root, create the backend environment:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8000
```

In a second terminal:

```powershell
cd frontend
npm.cmd ci
npm.cmd run dev
```

These commands do not require PowerShell activation scripts or changes to
execution policy. On this machine, `baseline\.runtime\python.exe` is an
existing local Python 3.12 alternative; that runtime is not uploaded to GitHub.

## macOS / Linux

From the project root:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-dev.txt
.venv/bin/python -m uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8000
```

In a second terminal:

```sh
cd frontend
npm ci
npm run dev
```

Open **http://127.0.0.1:5173**. API documentation is at
**http://127.0.0.1:8000/docs**. Vite forwards `/api` requests to the backend, so
no browser CORS configuration is required for this local setup. Both processes
must run. Stop either with Ctrl+C.

## Checks before a pull request

Frontend, from `frontend/`:

```sh
npm ci
npm run build
```

Backend, from `backend/` (Windows):

```powershell
..\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

On macOS/Linux use `../.venv/bin/python` instead. CI runs these same checks.
The production frontend build is output to `frontend/dist/`; production hosting
and API routing are not configured in this local scaffold.

With ports 8000 and 5173 free and frontend dependencies installed, run
`python scripts/smoke_test.py` using the backend environment to start both
services, check the frontend-to-API proxy, and stop the services automatically.
This checks HTTP integration; browser rendering is a separate manual check.

## Analysis work

Read [baseline/README.md](baseline/README.md) for the separate analysis setup,
pilot-first extraction, label/CRS checks, and offline evaluation commands.
The API reads `baseline/outputs/metrics.json` and
`baseline/outputs/heldout_predictions.csv` on each request. Regenerating valid
outputs and refreshing the page is sufficient to display updated results.
Never start extraction or training inside an HTTP request.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for component boundaries and
[baseline/outputs/results.md](baseline/outputs/results.md) for measured results.
Read [docs/MODEL_REVIEW.md](docs/MODEL_REVIEW.md) for the six error cases and
an interpretation of what the current evaluation supports.
