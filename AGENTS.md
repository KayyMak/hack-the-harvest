# Instructions for coding assistants

Read `START_HERE.md`, `docs/ARCHITECTURE.md`, and the files relevant to the task
before editing. The repository contains a small application scaffold plus a
working research baseline. Make the narrowest complete change for the request.

## Component boundaries

- Frontend UI: `frontend/src/`; HTTP calls go through `frontend/src/api.ts`.
- Backend routes: `backend/app/main.py`; public types: `backend/app/schemas.py`;
  saved-artifact access: `backend/app/artifacts.py`.
- Satellite extraction and model evaluation: `baseline/`. The API must not
  import or run this pipeline. See `baseline/README.md` for analysis commands.
- API response models / `/openapi.json` are the contract. Update matching
  TypeScript types and contract tests when changing responses.

## Data and model invariants

- Preserve source notebooks, the GeoPackage, `field_aoi.geojson`,
  `data_sources.md`, and the original root README. Put new work separately.
- `baseline/original_sha256.json` verifies originals. Do not rewrite hashes to
  conceal source changes. The later-added GeoJSON is also treated as source.
  `.gitattributes` preserves source bytes across Windows/Linux checkouts.
- Blank labels are unknown, never Grain. Only Grain/Silage reference labels
  enter supervised training.
- Keep every year of an `OBJECTID` together in validation. Fit imputation and
  scaling on training folds only. Report held-out predictions and compare
  against always-Grain on the same rows.
- Satellite features are evidence for a prediction, not harvest ground truth.
  Keep reference labels and model predictions visibly distinct.
- Missing satellite observations, read failures, and unavailable API artifacts
  must be explicit. Never substitute fabricated data or quietly show zeroes.
- Preserve source CRS metadata; use EPSG:4326 for catalog queries and the
  appropriate projected meter grid for imagery. Verify calibration offsets.

## Verification and collaboration

- Frontend: `cd frontend`, then `npm ci` and `npm run build`.
- Backend: `cd backend`, then `python -m unittest discover -s tests -v` in the
  configured environment. Tests use versioned baseline outputs.
- Analysis changes: run `baseline/test_baseline.py` with its analysis environment
  and the affected pipeline stage. Start new extraction paths with one field-year.
- Do not add a database, authentication, background workers, deployment stack,
  or extra dependencies unless the requested work requires them.
- Do not commit environments, node_modules, build products, secrets, or expiring
  signed asset URLs. Keep numerical caches and their provenance reproducible.
- Use `type(scope): imperative summary` commits, e.g.
  `feat(frontend): add a year filter` or `fix(api): report missing predictions`.
- Do not add AI signatures or co-author trailers to commits or documents.
- Do not overwrite teammates' unrelated changes. Coordinate shared API changes
  and keep PRs scoped. Report checks run and material limitations.
