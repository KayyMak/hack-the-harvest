FROM node:24-bookworm-slim AS frontend
WORKDIR /build
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend/requirements.txt backend/constraints.txt ./backend/
RUN python -m pip install --no-cache-dir -r backend/requirements.txt \
    && useradd --create-home harvest
COPY backend/app/ ./backend/app/
# Nemotron agent (POST /api/agent/run imports agent.run) and the LangChain tools it uses.
COPY agent/ ./agent/
COPY harvest/ ./harvest/
# The app runs as a non-root user: agent traces and reports go to a writable folder (backend/app/tools.py).
ENV AGENT_RUNS_DIR=/tmp/agent_runs
COPY baseline/outputs/metrics.json baseline/outputs/heldout_predictions.csv baseline/outputs/observations.csv baseline/outputs/fields.geojson baseline/outputs/asof.json baseline/outputs/feature_contributions.csv ./baseline/outputs/
COPY baseline/outputs/chips/ ./baseline/outputs/chips/
COPY baseline/outputs/decline_rule/metrics.json ./baseline/outputs/decline_rule/metrics.json
COPY baseline/outputs/unlabeled/summary.json baseline/outputs/unlabeled/predictions.csv ./baseline/outputs/unlabeled/
COPY data/reference/quickstats_2025_judges.csv ./data/reference/quickstats_2025_judges.csv
ENV QUICKSTATS_CSV=/app/data/reference/quickstats_2025_judges.csv
COPY market/data/nass_market.csv market/data/nass_sources.json market/data/market_timeline.json ./market/data/
COPY forecast/outputs/summary.json ./forecast/outputs/summary.json
# Project documents the market report retrieves from (backend/app/docsearch.py CORPUS).
COPY data_sources.md ./
COPY data/README.md ./data/README.md
COPY docs/MODEL_REVIEW.md docs/ML_EXPERIMENTS.md ./docs/
COPY baseline/README.md baseline/NEMOTRON_COMPARISON.md baseline/SCENE_FILTER_EXPERIMENT.md ./baseline/
COPY baseline/outputs/results.md ./baseline/outputs/results.md
COPY baseline/outputs/decline_rule/results.md ./baseline/outputs/decline_rule/results.md
COPY market/README.md ./market/README.md
COPY BARC_Corn.2021-2023.gpkg ./
COPY --from=frontend /build/dist/ ./web/dist/
USER harvest
EXPOSE 8000
CMD ["sh", "-c", "exec python -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port ${PORT:-8000}"]
