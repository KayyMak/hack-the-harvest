"""One command, end to end:
    python -m harvest.run --year 2022 --as-of 2022-10-12 --out <dir>

Writes into <dir> (never into the shared hand-off folder):
  predictions.parquet / predictions.json   field predictions as of the date
  metrics.json                             balanced metrics vs labels (if labeled year)
  rollup.json                              silage acres + 95% CI + NASS rows
  quickstats_export.csv                    our estimate in QuickStats shape
  asof_sweep.json                          metrics/rollup at several as-of dates (slider)
  fields.geojson                           polygons + prediction, ready for Leaflet
  timeseries/<OBJECTID>_<year>.json        per-field series for drill-down
The static files let the dashboard run from a laptop if Keeboh can't serve a port.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd

from contracts.schemas import validate
from harvest import io, tools

SWEEP = ["07-15", "08-01", "08-15", "09-01", "09-15", "10-01", "10-15", "11-01", "11-15", "12-01"]


def _ring(txt: str) -> list:
    return [[float(x), float(y)] for x, y in (p.split()[:2] for p in txt.split(","))]


def wkt_to_geojson(wkt: str) -> dict:
    """Minimal WKT -> GeoJSON for POLYGON / MULTIPOLYGON (no shapely needed)."""
    w = wkt.strip()
    if w.upper().startswith("MULTIPOLYGON"):
        polys = re.findall(r"\(\(([^()]*(?:\),\s*\([^()]*)*)\)\)", w)
        return {"type": "MultiPolygon",
                "coordinates": [[_ring(r) for r in re.split(r"\)\s*,\s*\(", p)] for p in polys]}
    if w.upper().startswith("POLYGON"):
        inner = w[w.index("((") + 2: w.rindex("))")]
        return {"type": "Polygon", "coordinates": [_ring(r) for r in re.split(r"\)\s*,\s*\(", inner)]}
    raise ValueError(f"unsupported geometry: {w[:30]}")


def _safe_eval(preds, year):
    try:
        return tools.evaluate(preds, year)
    except FileNotFoundError:
        return None


def run(year: int, as_of: str, out: Path, source: str = "auto", state: str = "MARYLAND") -> dict:
    out.mkdir(parents=True, exist_ok=True)
    if out.resolve() == io.handoff_dir().resolve():
        raise SystemExit("--out must not be the shared hand-off folder")

    preds = tools.classify(year, as_of, source)
    df = validate(pd.DataFrame(preds), "predictions")
    df.to_parquet(out / "predictions.parquet", index=False)
    (out / "predictions.json").write_text(json.dumps(preds, indent=1))

    metrics = _safe_eval(preds, year)
    if metrics:
        io.write_json(metrics, "metrics.json", out)

    roll = tools.aggregate(preds)
    try:
        roll["nass"] = tools.get_quickstats(state, year)
    except FileNotFoundError:
        roll["nass"] = None
    roll.update({"year": year, "as_of": as_of, "state": state})
    io.write_json(roll, "rollup.json", out)

    lo, hi = roll["silage_acres_95ci"]
    pd.DataFrame([{
        "source_desc": "MODEL", "year": year, "reference_period_desc": f"AS OF {as_of}",
        "agg_level_desc": "BARC FIELDS", "state_name": state, "commodity_desc": "CORN",
        "short_desc": "CORN, SILAGE - ACRES HARVESTED", "unit_desc": "ACRES",
        "Value": roll["silage_acres_expected"], "ci95_low": lo, "ci95_high": hi,
    }]).to_csv(out / "quickstats_export.csv", index=False)

    sweep = []
    for md in SWEEP:
        d = f"{year}-{md}"
        p = tools.classify(year, d, source)
        m = _safe_eval(p, year) or {}
        counts = pd.Series([r["class"] for r in p]).value_counts().to_dict() if p else {}
        sweep.append({"as_of": d, "counts": {k: int(v) for k, v in counts.items()},
                      "balanced_accuracy": m.get("balanced_accuracy"),
                      "silage_f1": m.get("silage_f1"), "abstain_rate": m.get("abstain_rate"),
                      "silage_acres_expected": tools.aggregate(p)["silage_acres_expected"] if p else None})
    io.write_json(sweep, "asof_sweep.json", out)

    by_id = {r["OBJECTID"]: r for r in preds}
    feats = []
    for f in tools.get_fields():
        pr = by_id.get(f["OBJECTID"], {})
        props = {k: v for k, v in f.items() if k != "geometry"}
        props.update({"class": pr.get("class", "No data"), "p_silage": pr.get("p_silage"),
                      "top_features": json.loads(pr["top_features"]) if pr.get("top_features") else []})
        feats.append({"type": "Feature", "geometry": wkt_to_geojson(f["geometry"]), "properties": props})
    io.write_json({"type": "FeatureCollection", "features": feats}, "fields.geojson", out)

    ts_dir = out / "timeseries"
    ts_dir.mkdir(exist_ok=True)
    fd = io.read_table("field_dates")
    for oid, g in fd[fd["year"] == year].groupby("OBJECTID"):
        (ts_dir / f"{oid}_{year}.json").write_text(
            g.sort_values("date").to_json(orient="records", date_format="iso"))

    return {"out": str(out), "n_predictions": len(preds), "metrics": bool(metrics),
            "silage_acres_expected": roll["silage_acres_expected"], "ci95": roll["silage_acres_95ci"]}


def main():
    ap = argparse.ArgumentParser(description="Silage or Grain: end-to-end run")
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--as-of", required=True, help="YYYY-MM-DD")
    ap.add_argument("--out", required=True)
    ap.add_argument("--source", default="auto", choices=["auto", "ml", "baseline"])
    ap.add_argument("--state", default="MARYLAND")
    a = ap.parse_args()
    print(json.dumps(run(a.year, a.as_of, Path(a.out), a.source, a.state), indent=2))


if __name__ == "__main__":
    main()
