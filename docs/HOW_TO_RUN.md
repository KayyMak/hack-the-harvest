# How to run

After installing dependencies, the API, dashboard, one command, notebook and static fallback
work offline from the versioned outputs in `baseline/outputs/`. Only the
satellite extraction (`baseline/run_baseline.py extract`) and the Nemotron agent need network
access. Setup details for Windows are in [START_HERE.md](../START_HERE.md).

## 1. API (FastAPI, port 8000)

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-dev.txt
.venv/bin/python -m uvicorn app.main:app --app-dir backend --port 8000
```

Open http://127.0.0.1:8000/docs. Key routes: `/api/baseline/summary` (metrics and confusion
matrix), `/api/baseline/predictions`, `/api/baseline/rollup` (silage acres, 95% interval, CV%),
`/api/baseline/rollup.csv` (QuickStats-shaped), `/api/fields`,
`/api/fields/{id}/observations?year=`, `/api/quickstats`, `/api/agent/run`,
`/api/agent/trace/{run_id}`. The full table is in [ARCHITECTURE.md](ARCHITECTURE.md).

For NASS context, point the API at the lab's QuickStats file:

```sh
export QUICKSTATS_CSV=/workspace/02_QuickStats/corn_grain_silage_acres_2012_2025.csv
```

## 2. Dashboard (React, port 5173)

```sh
cd frontend && npm ci && npm run dev
```

The Vite dev server proxies `/api` to port 8000.

## 3. One command

```sh
.venv/bin/python -m pip install scikit-learn   # only for as-of dates before Nov 30
.venv/bin/python -m harvest.run --year 2022 --as-of 2022-10-12 --out runs/2022-10-12
```

Writes `predictions.csv`, `metrics.json`, `rollup.json`, `quickstats_export.csv` and
`run.json`. The as-of date uses only the monthly NDVI medians complete by then.

## 4. Agent (Nemotron)

The agent implementation is not included yet. `POST /api/agent/run` returns 501 until
`agent.run.run_agent` is installed. Follow `agent/README.md` when that component lands
for its dependencies, NVIDIA credentials and launch commands. The saved logistic
predictions and the dashboard do not require Nemotron.

**Sample trace for the trace view.** `docs/samples/agent_trace_sample.jsonl` is a 39-step
trace from a scripted run on BARC 2021 as of 2021-10-12 (real tool results, a scripted
stand-in for the model). Each line is
`{run_id, step, ts, node, type, tool?, args?, summary?, code?, ok?}` with `node` in
analyst | tools | verifier | writer and `type` in plan | tool_call | tool_result | flag |
retrieve | check | report | error. It includes a failed tool (QuickStats not configured),
Verifier flags that send the analyst back for more data, a rejected invented number, and the
final report. To serve it through the API:

```sh
mkdir -p agent_runs/traces && cp docs/samples/agent_trace_sample.jsonl agent_runs/traces/r-sample.jsonl
curl -s http://127.0.0.1:8000/api/agent/trace/r-sample
```

## 5. Submission notebook

Install `numpy pandas matplotlib scikit-learn jupyter nbconvert ipykernel` in the notebook
environment. On Keeboh: set `QUICKSTATS_CSV` as above, open
`Submission/harvest_submission.ipynb`, run all cells and save so outputs are stored. Or:

```sh
jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.timeout=1800 \
  Submission/harvest_submission.ipynb
```

## 6. If the API cannot run during the demo

Export every response once, then serve the files with only the standard library:

```sh
.venv/bin/python scripts/export_static.py snapshot/           # while the backend env works
python3 scripts/export_static.py snapshot/ --serve-only        # later: no FastAPI needed
```

It serves the same `/api/...` URLs on port 8000, so the dashboard works unchanged. Agent
runs are not available from a snapshot (read-only; POST returns 501).
QuickStats exports cover Maryland only; requests for another state return 503. Year,
crop-use and level filters apply to saved rows. Missing exports return 503. Re-export
after outputs change; a failed re-export removes the old response for that route.

## 7. Checks

```sh
(cd backend && ../.venv/bin/python -m unittest discover -s tests -v)
(cd frontend && npm run build)
.venv/bin/python scripts/smoke_test.py
```

## 8. Re-running the analysis

```sh
python baseline/test_baseline.py
python baseline/run_baseline.py evaluate     # offline, from versioned caches
```

Full extraction and the pilot gate are described in [baseline/README.md](../baseline/README.md).

## Sources

Data sources and their roles are listed in [data_sources.md](../data_sources.md) and
[baseline/README.md](../baseline/README.md): BARC field polygons and labels (GeoPackage),
Sentinel-2 L2A via Microsoft Planetary Computer, and the lab's NASS QuickStats export.

## Required BARC citations

**Publications**

- Dulaney, W., Anderson, M., Gao, F., Stern, A., Moglen, G., Meyers, G., Daughtry, C., White, W.,
  Akumaga, U., & Showalter, J. (2024). Development of a gridded yield data archive for farm
  management and research at the USDA Beltsville Agricultural Research Center. *Agrosystems,
  Geosciences & Environment*, 7(1), e20474. https://doi.org/10.1002/agg2.20474
- Kraatz, S., Lamb, B., Hively, W., Jennewein, J., Gao, F., Cosh, M., & Siqueira, P. (2023).
  Comparing NISAR (Using Sentinel-1), USDA/NASS CDL, and Ground Truth Crop/Non-Crop Areas in an
  Urban Agricultural Region. *Sensors*, 23(20), 8595. https://doi.org/10.3390/s23208595

**Datasets**

- USDA Beltsville Agricultural Research Center (BARC) Gridded Yield Data Archive, version 1.
  USDA National Agricultural Library, Ag Data Commons.
  https://agdatacommons.nal.usda.gov/articles/dataset/USDA_Beltsville_Agricultural_Research_Center_BARC_Gridded_Yield_Data_Archive_version_1/28950746
- Kraatz, S. (2023). Validating NISAR's cropland mapping approach and the USDA/NASS Cropland Data
  Layer against ground truth data in a fragmented urban agricultural region (Version 1.0.0)
  [Data set]. Zenodo. https://doi.org/10.5281/zenodo.8087301
- Sentinel-2 Level-2A, Microsoft Planetary Computer.
  https://planetarycomputer.microsoft.com/dataset/sentinel-2-l2a
- USDA NASS Quick Stats. https://quickstats.nass.usda.gov/
