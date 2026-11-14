# web — demo dashboard (Frontend)

React + TypeScript (Vite), Leaflet map, Recharts charts.

```bash
cd web
npm install
cp .env.example .env.local      # VITE_API_URL=http://localhost:8000
npm run dev                      # live: talks to the FastAPI backend
VITE_STATIC=1 npm run dev        # offline: reads public/snapshot/*.json
npm run build                    # type-check + production build
VITE_STATIC=1 npm run build      # static backup build (e.g. Vercel)
```

Dev server: http://localhost:5173

- API types live in `src/types.ts` — update them when Backend freezes `contracts/`.
- `src/api.ts` is the only place that talks to the backend; snapshot file names are in `snap`.
- `public/snapshot/` currently holds **FAKE stub data** (see its README). Regenerate with
  `node scripts/make-stub-snapshot.mjs`; replace with Backend's real export before any demo.
- Design variants: header "Design" menu or `?theme=harvest|usda|deck|night`.
- Presenter keys: `1`–`4` switch panels, `←`/`→` step the as-of date.
- No API keys in the browser, ever.
