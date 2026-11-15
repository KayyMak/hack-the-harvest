# Market data (for Cutline's Market outlook tab)

The Market tab shows a sample, forward-looking corn market outlook that updates month by month,
using only what was known on each date. Two kinds of seasons:

- **2025 outlook (US and Maryland).** At each NASS release (Jun 30 Acreage; Aug 12, Sep 12, Nov 14
  Crop Production): NASS's grain acres, yield and production forecasts, plus the team forecast's
  silage acres (`forecast/estimate_2025.py`, built only from reports public before January 2026).
  Compared with the 2024 official baseline: US supply change, grain kept off the market by silage,
  and price pressure under an assumed elasticity range.
- **2021-2023 (BARC model).** The satellite model's calls at Aug 12, Sep 12, Oct 12, Nov 12 and
  Nov 30, with the prior season as the latest official baseline. BARC reference labels are hidden
  until after harvest.

Files (all reproducible, no API key):

| File | Built by | Contents |
| --- | --- | --- |
| `data/nass_market.csv` | `python3 market/fetch_nass.py` | Maryland and US corn acres, yields, production and prices received, 2020-2024, from the NASS Crop Production (cropan23/24/25) and Crop Values (cpvl0223/24/25) annual summaries; each value from the newest release |
| `data/nass_sources.json` | same | download URLs, release dates, SHA-256 |
| `data/market_timeline.json` | `python3 market/build_timeline.py` | the 2025 month-by-month outlook above (reuses the team forecast's NASS parser and cached reports) |

The API (`backend/app/market.py`) serves `/api/market/outlook?season=&as_of=` (no LLM) and
`/api/market/report` (Nemotron). In a report every tool refuses data published after the as-of
date. A date before December 31 of its season is in-season (every date the tab offers is), and then
the tools also hide what is computed from BARC labels recorded after harvest: that season's
reference labels, the model's held-out accuracy (it uses the 2021-2023 labels), and the project's
results documents. Document search then covers only the methods and data-source documents
(`data_sources.md` and this file) and says "project results are hidden for in-season runs".
A season's labels reappear on its December 31; accuracy and results documents only on a December 31
from 2023 on. Every sentence must cite a retrieved tool result or project-document passage, numbers must
appear in the cited source, a second Nemotron pass checks wording, and anything unsupported is
removed. To enable Nemotron, put `NVIDIA_API_KEY` in the repo-root `.env` (template: `.env.example`).
