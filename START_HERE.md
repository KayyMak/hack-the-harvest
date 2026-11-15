# Start here

The project has been submitted. Read the [project README](README.md) for the
current overview and cross-platform setup, and the [submission summary](SUBMISSION.md)
for the final CSV, executed notebook, results, and live dashboard.

## Choose your task

| Task | Guide |
| --- | --- |
| Run Cutline and the API | [README setup](README.md#run-locally) |
| Run the CLI, agent, notebook, or static fallback | [Run guide](docs/HOW_TO_RUN.md) |
| Find documentation and research history | [Documentation index](docs/README.md) |
| Understand components and API routes | [Architecture](docs/ARCHITECTURE.md) |
| Work on the main dashboard | [Cutline frontend](web/README.md) |
| Deploy or check hosting | [Render guide](docs/DEPLOY_RENDER.md) |
| Reproduce satellite analysis | [Baseline methods](baseline/README.md) |
| Review submitted forecast methods | [Forecast v2 results](forecast_v2/results.md) |

Use Python 3.12 and Node.js 24. Cutline lives in `web/`; `frontend/` is the
maintained earlier results screen. Saved results require no NVIDIA key.
Hosted agent and market reports use a server-side `NVIDIA_API_KEY`.

Read [ENGINEERING.md](ENGINEERING.md) and [CONTRIBUTING.md](CONTRIBUTING.md)
before editing. Preserve the submitted artifact paths, source data, and unknown
labels. Local environments and dependencies are not committed.
