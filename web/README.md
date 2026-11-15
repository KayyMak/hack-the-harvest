# web — demo dashboard (Frontend)

React + TypeScript (Vite), Leaflet map, Recharts charts.

```bash
cd web
npm install
cp .env.example .env.local      # optional; defaults to same-origin /api
npm run dev                      # live: talks to the FastAPI backend
VITE_STATIC=1 npm run dev        # offline: reads public/snapshot/*.json
npm run build                    # type-check + production build
VITE_STATIC=1 npm run build      # static backup build (e.g. Vercel)
```

Dev server: http://localhost:5173

- Backend `/openapi.json` is the contract. `src/adapter.ts` converts its saved-artifact responses into the display types in `src/types.ts`.
- `src/api.ts` is the only place that talks to the backend; snapshot file names are in `snap`.
- `public/snapshot/` contains real BARC season-end results. Rebuild it with
  `python web/scripts/build-real-snapshot.py` from the repo root (requires pyproj).
  The separate stub generator creates fabricated fixtures and must not be used for a results demo.
- Live mode uses `/api/fields.geojson`, `/api/baseline/summary`, `/api/baseline/predictions`,
  and saved observations. Start the existing FastAPI server on port 8000; Vite proxies `/api`.
- Only season-end predictions exist. Statewide rollups, chips, and feature contributions
  remain explicitly unavailable. The saved BARC acreage subtotal is not a statewide estimate.
- Static mode cannot run an agent. Live agent requests report the backend's 501 until implemented.
- Run `npm test` and `npm run build`; CI checks both dashboards. Render still serves `frontend/`.
- Design variants: header "Design" menu or `?theme=harvest|usda|deck|night`.
- Presenter keys: `1`–`4` switch panels, `←`/`→` step the as-of date.
- No API keys in the browser, ever.
