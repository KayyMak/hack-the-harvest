# Documentation index

Start with the [project overview](../README.md). The project has been submitted;
the links below separate the submitted deliverables, current operating guides,
and historical research notes.

## Submitted deliverables

- [Submission summary](../SUBMISSION.md): final outputs, headline results,
  live dashboard, and reproduction commands.
- [Submitted 2025 acreage CSV](../forecast_v2/outputs/state_estimates_2025.csv).
- [Executed submission notebook](../Submission/harvest_submission.ipynb).
- [Forecast method and backtest results](../forecast_v2/results.md).
- [Current BARC model results](../baseline/outputs/results.md).

## Run and maintain the application

- [Setup entry point](../START_HERE.md).
- [Run guide](HOW_TO_RUN.md): API, dashboards, reporting CLI, agent, notebook,
  and static fallback.
- [Architecture and API routes](ARCHITECTURE.md).
- [Cutline frontend](../web/README.md).
- [Render deployment](DEPLOY_RENDER.md).
- [Market data and report generation](../market/README.md).
- [Engineering rules](../ENGINEERING.md) and [contributing](../CONTRIBUTING.md).

## Data and research

- [Source guide](../data_sources.md) and [label provenance](../data/README.md).
- [Satellite baseline methods](../baseline/README.md).
- [Model v2 experiments](../baseline/model_v2/results.md).
- [Forecast backtests](../analysis/forecast_backtest/README.md).
- [Nemotron numerical comparison](../baseline/NEMOTRON_COMPARISON.md).
- [Scene-cloud filter experiment](../baseline/SCENE_FILTER_EXPERIMENT.md).

## Historical context

- [Original starter README](original/README.md): immutable archived source.
- [First model review](MODEL_REVIEW.md): the original nine-feature v1 model,
  before adoption of model v2.
- [Earlier ML experiment snapshot](ML_EXPERIMENTS.md): frozen development
  comparisons, not a description of the current submitted forecast.
- [Original model backup](../baseline/outputs/v1_backup/README.md): preserved
  artifacts used by historical experiments and regression checks.
- [Work breakdown](WORK_BREAKDOWN.md): development task history.

Keep source files, numerical caches, and result snapshots at their existing paths.
Scripts and provenance checks depend on them; this index organizes access without
moving the submitted artifacts.
