# Cutline frontend

The main React and TypeScript dashboard uses Vite, Leaflet maps, and Recharts.
For full project setup, see the [root README](../README.md#run-locally).

## Run

Start the FastAPI backend on port 8000, then:

```sh
cd web
npm ci
npm run dev
```

Open the URL Vite prints, normally http://localhost:5173. Requests to `/api`
are proxied to the backend. Optional connection settings are documented in
`.env.example`; browser configuration must never contain an NVIDIA key.

For the saved snapshot fallback on macOS/Linux:

```sh
VITE_STATIC=1 npm run dev
```

In PowerShell, set `$env:VITE_STATIC = '1'` before `npm.cmd run dev`.
Static mode cannot start agent runs or generate hosted reports.

## Data and ownership

- `src/api.ts` owns HTTP access and snapshot file selection.
- `src/adapter.ts` converts API responses into display types.
- The backend's `/openapi.json` is the public contract.
- Views include 2025 state forecasts, BARC validation, fields, model quality,
  agent traces, and market context. Missing optional data remains explicit.
- Saved BARC field acreage is distinct from the submitted state forecast.
- Live agent runs use `agent/run.py` and a server-side NVIDIA key.

`public/snapshot/` contains saved real results. Rebuild commands and input checks
are in `scripts/build-real-snapshot.py`; run it from the project root with its
required analysis packages. The submitted forecast export is built separately
by `forecast_v2/export_dashboard.py`. Do not regenerate snapshots merely to edit
UI or documentation. The separate stub generator makes fabricated fixtures and
must not be used for a results demo.

## Checks and hosting

```sh
npm test
npm run build
```

CI runs both. The production build goes to `web/dist/`. The root Dockerfile
builds this dashboard and the API serves it on the same origin, with
`frontend/dist/` as a fallback. See [hosting](../docs/DEPLOY_RENDER.md).

Presenter keys `1` through `6` switch views. Theme options are defined in
`src/theme.ts`; the design menu is available with `?design`.
