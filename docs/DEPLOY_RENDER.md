# Host the saved-results dashboard on Render

The root Dockerfile builds the Cutline dashboard (`web/`) and serves it from FastAPI on
the same origin. Without a `web/dist/` build the API falls back to `frontend/dist/`.
The image contains only the application and the saved artifacts needed by its
HTTP routes. It does not download satellite scenes, train models, or need an
NVIDIA key. Existing local development commands still work.

## Deploy

1. Merge the hosting pull request into `main` after review and passing checks.
2. Sign in at <https://dashboard.render.com/> using GitHub.
3. Choose **New > Blueprint**, connect `KayyMak/hack-the-harvest`, and select
   branch `main`. Grant Render access to this repository if prompted.
4. Render reads `render.yaml`. Review the single **Free** web service named
   `hack-the-harvest`, then create/deploy the Blueprint. No environment variables
   or payment upgrades are required for the saved-results dashboard.
5. Wait for the image build and health check to pass. Open the service's
   assigned `https://...onrender.com` URL. That is the URL to share with judges
   and teammates; do not append a port.
6. Confirm the results table appears. Open `/api/health` (must show
   `{"status":"ok"}`), `/api/baseline/summary`, and `/docs` at the same URL.
   For a fuller check, run `python scripts/check_deployment.py https://YOUR-SERVICE.onrender.com`.

Auto-deploy waits for GitHub checks to pass on `main`. Changes on teammates'
branches do not deploy. Review any Render pricing or upgrade selection before
accepting it; this configuration selects the free plan.

## Scope and limits

- This publishes the current versioned baseline dashboard, not the exploratory
  ML experiments as a new model. Its API also serves fields, observations,
  polygons, and acreage rollups.
- The image includes `agent/`, `harvest/`, and their runtime dependencies.
  Agent and generated market reports require `NVIDIA_API_KEY` on the server;
  saved dashboard views do not. Traces and reports use `/tmp/agent_runs`.
- The image sets `QUICKSTATS_CSV` to the versioned 2025 judge-reference CSV.
  For broader historical context, supply a suitable CSV and override that path.
  Filters still apply to the rows actually available.
- Health checks only show that the API is alive. The deployment smoke check
  also verifies the frontend and saved artifacts.
- Free services sleep after inactivity; the first visit can take time to wake.
  Open the dashboard before a presentation. Free-tier usage/build limits apply.
- Container files are ephemeral. Redeploying replaces them; do not store new
  labels, uploads, or important reports inside this container.
- The URL is public and has no login. Only the frontend build directory is
  exposed as static files; the source GeoPackage is read internally by the API.

## Local production check (requires a running Docker engine)

```sh
docker build -t hack-the-harvest .
docker run --rm -p 8000:8000 hack-the-harvest
```

Open <http://localhost:8000>. In another terminal run
`python scripts/check_deployment.py`. GitHub's Deployment workflow builds this
same image and tests a custom `PORT`, the frontend assets, and data routes.

If Render fails, inspect **Logs** for the first build/start error. A dashboard
error should also be checked against `/api/baseline/summary`; missing data must
stay visible rather than be replaced with example values. To roll back, use
Render's prior successful deploy or revert the faulty change through a PR.

References: [Render Docker](https://render.com/docs/docker),
[Blueprint specification](https://render.com/docs/blueprint-spec),
[free service limits](https://render.com/docs/free).
