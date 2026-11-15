# public/snapshot — offline fallback data

This folder contains real BARC field polygons, reference labels, saved held-out
predictions, model evaluation, and available NDVI series. Rebuild it from the
versioned sources using `python web/scripts/build-real-snapshot.py` (needs pyproj).
Metadata records unavailable products; missing files must remain explicit.

The separate `make-stub-snapshot.mjs` script generates fabricated development
fixtures and sets `stub: true`. Those fixtures are not scientific results. Static
mode cannot execute an agent, and no fabricated agent trace is included here.

`VITE_STATIC=1` makes the app read these files instead of calling the API.
Backend's snapshot export must use the same names and the same shapes as the
API responses (see `web/src/types.ts`):

| Route | File |
| --- | --- |
| — | `_meta.json` (`{stub, note, years, as_of_dates}`) |
| `GET /fields?year=Y` | `fields_Y.json` |
| `POST /predict {year: Y, as_of: D}` | `predict_Y_D.json` |
| `GET /evaluate?split=S` | `evaluate_S.json` |
| `GET /rollup?year=Y` | `rollup_Y.json` (+ the CSV its `csv_url` names) |
| `GET /fields/{id}/series?year=Y` | `series_{id}_Y.json` |
| `POST /agent/run` | `agent_run.json` (`{run_id}`) |
| `GET /agent/trace/{run_id}` | `agent_trace_{run_id}.json` |
| `/chips/{id}_{Y}_{pre,post}.png` | `chips/{id}_{Y}_{pre,post}.png` |

Only the exporter should set `stub: false` after reading real inputs. Never
relabel fabricated fixtures as real data by editing metadata.
