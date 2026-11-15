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
COPY baseline/outputs/metrics.json baseline/outputs/heldout_predictions.csv baseline/outputs/observations.csv baseline/outputs/fields.geojson baseline/outputs/asof.json ./baseline/outputs/
COPY BARC_Corn.2021-2023.gpkg ./
COPY --from=frontend /build/dist/ ./web/dist/
USER harvest
EXPOSE 8000
CMD ["sh", "-c", "exec python -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port ${PORT:-8000}"]
