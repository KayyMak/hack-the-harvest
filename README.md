# Hack the Harvest

**Cutline** is a corn harvest analysis dashboard built for Hack the Harvest.
It combines satellite evidence for field-level Grain/Silage predictions with
2025 harvested-acre forecasts, uncertainty estimates, and a tool-using NVIDIA
Nemotron analyst. Reference labels, model predictions, and official statistics
remain visibly distinct.

**Submitted project:** see [the submission summary](SUBMISSION.md),
[executed notebook](Submission/harvest_submission.ipynb), and
[final acreage CSV](forecast_v2/outputs/state_estimates_2025.csv).
Use the [documentation index](docs/README.md) to find operating guides and research history.

## What is included

- **Cutline dashboard (`web/`):** state forecasts, BARC validation, field maps,
  time series, model-quality views, an agent interface, and a market outlook.
- **FastAPI backend (`backend/`):** validated access to saved metrics,
  predictions, acreage rollups, chips, feature contributions, and forecasts.
- **Research pipeline (`baseline/`):** masked and calibrated Sentinel-2 NDVI
  extraction, grouped model evaluation, diagnostics, and saved experiments.
- **Reporting and agent (`harvest/`, `agent/`):** as-of reports and a LangGraph
  analyst, tools, verifier, and writer workflow with traces and saved reports.
- **Forecast and submission work:** public-report-based 2025 acreage forecasts,
  forecast backtests, benchmark comparisons, and a submission notebook.
- **Earlier frontend (`frontend/`):** a simpler metrics and predictions screen,
  maintained alongside Cutline.

Saved results work offline after package installation. New satellite extraction
needs network access. Hosted Nemotron reports also need an NVIDIA API key.

## Run locally

Use **Python 3.12** and **Node.js 24**, the version used in CI.

```sh
git clone https://github.com/KayyMak/hack-the-harvest.git
cd hack-the-harvest
```

### Windows / PowerShell

Start the backend from the project root:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8000
```

In a second terminal, start Cutline:

```powershell
cd web
npm.cmd ci
npm.cmd run dev
```

No environment activation or PowerShell execution policy changes are needed.

### macOS / Linux

Start the backend from the project root:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-dev.txt
.venv/bin/python -m uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8000
```

In a second terminal:

```sh
cd web
npm ci
npm run dev
```

Open the Vite URL printed in the terminal, normally **http://localhost:5173**.
API documentation is at **http://127.0.0.1:8000/docs**. Both processes must
remain running; Vite proxies `/api` requests to port 8000.

To run the simpler results screen, use `frontend/` instead of `web/`.
See [the run guide](docs/HOW_TO_RUN.md) for the notebook and static API fallback.
Cutline also supports snapshot mode through `VITE_STATIC=1`; see its
[frontend guide](web/README.md).

## BARC validation and model results

The source GeoPackage contains **83 fields**. Its **44 labeled field-years**
span **34 distinct fields**, with 32 Grain and 12 Silage examples from 2021 to
2023. Another 205 field-years have blank labels and are excluded from supervised
training. Separate model calls on unlabeled, corn-screened fields have no
reference label and must remain predictions.

The current saved full-season model is **model v2**: L1 logistic regression on
nine NDVI summaries and four harvest-timing features. Five-fold validation keeps
all years of an `OBJECTID` together. Imputation and scaling use training folds
only; regularization is selected through grouped inner validation.

| Metric | Model v2 | Always Grain |
| --- | ---: | ---: |
| Silage precision | 90.91% | 0% |
| Silage recall | 83.33% | 0% |
| Silage F1 | 86.96% | 0% |
| Grain false positive rate | 3.125% | 0% |
| Balanced accuracy | 90.10% | 50.0% |
| Brier score, lower is better | 0.0649 | 0.2727 |

Silage is the positive class. Always-Grain precision is undefined and reported
as zero by convention. Model v2 identifies 10 of 12 Silage examples and
incorrectly classifies 1 of 32 Grain examples as Silage.

These results describe a small, already inspected, single-site dataset.
Nearby fields can share imagery, weather, and management. The evaluation does
not establish transfer to new regions or future years. Satellite features are
evidence for a prediction, not direct harvest ground truth, and probabilities
are not proven calibrated.

See [current results](baseline/outputs/results.md),
[model v2 experiments](baseline/model_v2/results.md), and
[baseline methods](baseline/README.md). The
[original model backup](baseline/outputs/v1_backup/README.md) and
[earlier experiment overview](docs/ML_EXPERIMENTS.md) preserve comparisons,
including numerical Nemotron predictions and scene-cloud filtering.

## Acreage, forecasts, and market context

BARC rollups summarize the evaluated fields, including probability-weighted
silage acres, intervals, and misclassification adjustments. They are field
subtotals and do not represent state or national acreage.

The submitted 2025 forecast lives in `forecast_v2/` and uses public NASS reports
released before January 2026. Its [method and backtest](forecast_v2/results.md)
and [saved summary](forecast_v2/outputs/summary.json) record methods, source
release dates, uncertainty, and exclusion of the January 2026 answer key.
The first forecast in `forecast/` remains available for comparison.
The dashboard also exposes a separate Maryland satellite-sample estimate and
benchmark comparisons. Official reference totals are shown separately.

The [market workflow](market/README.md) builds an outlook from information
available on a selected date. Saved figures need no key. Optional Nemotron
reports cite retrieved tools and documents, with unsupported claims filtered.

## Generate an as-of report

From the project root, using the installed backend environment:

```powershell
.venv\Scripts\python.exe -m harvest.run --year 2022 --as-of 2022-11-30 --out runs/2022-11-30
```

On macOS/Linux, use `.venv/bin/python`. This writes `predictions.csv`,
`metrics.json`, `rollup.json`, `quickstats_export.csv`, and `run.json`.

Supported years are 2021, 2022, and 2023; the date must fall in the selected
year. From November 30, the CLI uses saved full-season model v2 predictions.
Earlier dates use the explicitly labeled v1 refit on monthly NDVI features
complete by that date. Before July 31, fields remain Pending and no acreage
CSV is written. This is retrospective analysis of saved data.

## API and optional configuration

The authoritative response contract is `/openapi.json`, generated from
`backend/app/schemas.py`. See [the architecture](docs/ARCHITECTURE.md) for the
full route table and component boundaries.

| Routes | Purpose |
| --- | --- |
| `/api/health` | API process health |
| `/api/baseline/summary`, `/api/baseline/predictions` | Saved evaluation and field-year predictions |
| `/api/baseline/asof`, `/api/baseline/convergence` | Saved checkpoints and acreage trajectories |
| `/api/baseline/rollup`, `/api/baseline/rollup.csv` | Labeled-field acreage and CSV export |
| `/api/fields`, `/api/fields.geojson` | Field metadata and polygons |
| `/api/fields/{field_id}/observations?year=2022` | Saved per-scene measurements |
| `/api/forecast_2025`, `/api/estimate_2025` | Separate forecast and sample estimate |
| `/api/quickstats` | Optional local QuickStats context |
| `POST /api/agent/run`, `/api/agent/trace/{run_id}` | Start an analyst run and read its trace |
| `/api/market/outlook`, `POST /api/market/report` | Date-aware outlook and generated report |

Missing or invalid artifacts return explicit errors. Suppressed official values
remain null. API health alone does not verify that all artifacts exist.

| Variable | Purpose |
| --- | --- |
| `QUICKSTATS_CSV` | Optional local QuickStats CSV; its route returns 503 when unset |
| `NVIDIA_API_KEY` | Hosted Nemotron analyst and generated market reports |
| `NEMOTRON_MODEL`, `NEMOTRON_BASE_URL` | Optional analyst model and endpoint overrides |
| `AGENT_RUNS_DIR`, `AGENT_TRACES_DIR` | Override local report and trace directories |

For hosted reports, copy `.env.example` to `.env` and supply the NVIDIA key,
or set it in the server environment. Keys stay on the server. The agent lives
in `agent/run.py`; its LangGraph and LangChain dependencies are included in
backend requirements. See [the run guide](docs/HOW_TO_RUN.md#4-agent-nemotron)
for the request and trace workflow.

## Repository layout

```text
web/                      Cutline dashboard, maps, charts, static snapshots
frontend/                 Earlier metrics and prediction screen
backend/                  FastAPI routes, schemas, artifact readers, tests
harvest/                  Reporting CLI, as-of evaluation, shared agent tools
agent/                    Nemotron analyst graph
baseline/                 Satellite extraction, evaluation, caches, saved results
forecast/                 First 2025 forecast, retained for comparison
forecast_v2/              Submitted 2025 forecast, backtests, and provenance
analysis/                 Forecast backtests and supporting analysis
market/                   NASS context and market timeline generation
data/                     Reference snapshots, extra labels, source metadata
Submission/               Submission notebook
docs/                     Architecture, run guide, deployment, research notes
scripts/                  Smoke checks, static exports, deployment checks
```

The original GeoPackage, starter notebooks, `field_aoi.geojson`, and
`data_sources.md` remain at the root. Analysis runs separately from HTTP
requests. There is no database or login.

## Checks and deployment

From `web/`, run `npm ci`, `npm test`, and `npm run build`.
From `frontend/`, run `npm ci` and `npm run build`.
From `backend/`, run the backend environment's
`python -m unittest discover -s tests -v`.

Analysis uses a separate environment from `baseline/requirements-lock.txt`.
Run `python -m unittest discover -s baseline -p "test_*.py" -v` from the root.
Start new extraction paths with a one-field pilot before a full run.
CI checks both frontends, the API, and analysis tests.

For HTTP integration, install `frontend/` dependencies, leave ports 8000 and
5173 free, and run `python scripts/smoke_test.py` in the backend environment.
It starts both services and checks their proxy connection. Browser rendering
requires a separate manual check.

The root Dockerfile and `render.yaml` support hosting the saved-results app.
The backend prefers a built `web/dist/`, falling back to `frontend/dist/`.
See [Render deployment](docs/DEPLOY_RENDER.md) and verify the deployed
configuration before relying on optional integrations.

Read [ENGINEERING.md](ENGINEERING.md), [CONTRIBUTING.md](CONTRIBUTING.md), and
[the architecture](docs/ARCHITECTURE.md) before changing components. Keep
unknown labels unknown, preserve source provenance, and never commit keys,
environments, installed dependencies, build products, or signed asset URLs.

The [original starter README](docs/original/README.md) is archived byte for byte.
Its unchanged checksum is tracked under the archive path in
`baseline/original_sha256.json`.

## Sources

See [data_sources.md](data_sources.md), [label provenance](data/README.md),
and [the run guide](docs/HOW_TO_RUN.md) for citation guidance, including
[Dulaney et al. (2024)](https://doi.org/10.1002/agg2.20474) and
[Kraatz et al. (2023)](https://doi.org/10.3390/s23208595), plus their datasets.
Imagery comes from [Sentinel-2 L2A on Microsoft Planetary Computer](https://planetarycomputer.microsoft.com/dataset/sentinel-2-l2a).
Aggregate context comes from [USDA NASS](https://quickstats.nass.usda.gov/).
