"""Tool functions shared by the API and the agent. All return JSON-safe dicts/lists."""
from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from contracts.schemas import validate
from harvest import baseline, io

QUICKSTATS_CSV = os.environ.get(
    "QUICKSTATS_CSV", "/workspace/02_QuickStats/corn_grain_silage_acres_2012_2025.csv")


def _records(df: pd.DataFrame) -> list[dict]:
    return json.loads(df.to_json(orient="records", date_format="iso"))


def get_fields() -> list[dict]:
    """All field polygons (WKT, EPSG:4326) with OBJECTID, FARM, FIELD, ACRES."""
    return _records(io.read_table("fields"))


def get_timeseries(objectid: int, year: int) -> list[dict]:
    """Per-date index values for one field-year, sorted by date."""
    fd = io.read_table("field_dates")
    fd = fd[(fd["OBJECTID"] == objectid) & (fd["year"] == year)].sort_values("date")
    return _records(fd)


def classify(year: int, as_of: str, source: str = "auto") -> list[dict]:
    """Predictions for every field in `year` using data up to `as_of`.

    source: 'ml' = ML hand-off predictions.parquet, 'baseline' = rule baseline,
    'auto' = ML rows matching year/as_of if present, else baseline.
    """
    if source in ("ml", "auto"):
        try:
            p = io.read_table("predictions")
            p = p[(p["year"] == year) & (p["as_of"].astype(str) == as_of)]
            if len(p) or source == "ml":
                return _records(p)
        except FileNotFoundError:
            if source == "ml":
                raise
    p = validate(baseline.predict(io.read_table("field_dates"), as_of, year), "predictions")
    return _records(p)


def _f1(p, r):
    return 2 * p * r / (p + r) if p + r else 0.0


def evaluate(predictions: list[dict] | None = None, year: int | None = None,
             as_of: str | None = None) -> dict:
    """Compare predictions to labels. Balanced metrics, plus the 'always grain' score."""
    if predictions is None:
        predictions = classify(year, as_of) if year and as_of else _records(io.read_table("predictions"))
    pr = pd.DataFrame(predictions)
    lab = io.read_table("labels")
    if year is not None:
        lab = lab[lab["year"] == year]
    m = lab.merge(pr, on=["OBJECTID", "year"], how="left")
    m["class"] = m["class"].fillna("Insufficient")
    decided = m[m["class"].isin(["Grain", "Silage"])]
    y, yhat = decided["label"], decided["class"]
    tp = int(((y == "Silage") & (yhat == "Silage")).sum())
    fn = int(((y == "Silage") & (yhat == "Grain")).sum())
    fp = int(((y == "Grain") & (yhat == "Silage")).sum())
    tn = int(((y == "Grain") & (yhat == "Grain")).sum())
    rec_s = tp / (tp + fn) if tp + fn else float("nan")
    rec_g = tn / (tn + fp) if tn + fp else float("nan")
    prec_s = tp / (tp + fp) if tp + fp else 0.0
    n = len(decided)
    cm = pd.crosstab(m["label"], m["class"]).reindex(
        index=["Grain", "Silage"], columns=["Grain", "Silage", "Pending", "Insufficient"], fill_value=0)

    def clean(x):
        x = float(x)
        return None if math.isnan(x) else round(x, 3)

    return {
        "n_labeled": int(len(m)), "n_decided": n,
        "abstain_rate": clean(1 - n / len(m)) if len(m) else None,
        "accuracy": clean((tp + tn) / n) if n else None,
        "balanced_accuracy": clean((rec_s + rec_g) / 2),
        "silage_precision": clean(prec_s), "silage_recall": clean(rec_s),
        "silage_f1": clean(_f1(prec_s, rec_s if not math.isnan(rec_s) else 0)),
        "always_grain_accuracy": clean((lab["label"] == "Grain").mean()) if len(lab) else None,
        "always_grain_balanced_accuracy": 0.5,
        "confusion_matrix": {"rows_true": cm.index.tolist(), "cols_pred": cm.columns.tolist(),
                             "values": cm.values.tolist()},
        "models": sorted(pr["model"].dropna().unique().tolist()) if "model" in pr else [],
    }


def aggregate(predictions: list[dict]) -> dict:
    """Roll field predictions up to acres with a 95% interval on silage acres.

    Expected silage acres = sum(p_silage * acres) over decided fields.
    Interval treats fields as independent Bernoulli: var = sum(acres^2 p (1-p)).
    Pending/Insufficient acres are reported separately, not guessed.
    """
    pr = pd.DataFrame(predictions)
    f = io.read_table("fields")[["OBJECTID", "ACRES"]]
    m = pr.merge(f, on="OBJECTID", how="left")
    by_class = {k: float(v) for k, v in m.groupby("class")["ACRES"].sum().round(1).items()}
    d = m[m["class"].isin(["Grain", "Silage"])].copy()
    p = d["p_silage"].fillna((d["class"] == "Silage").astype(float))
    exp = float((p * d["ACRES"]).sum())
    sd = float(((d["ACRES"] ** 2) * p * (1 - p)).sum() ** 0.5)
    return {
        "acres_by_class": by_class,
        "silage_acres_hard": round(float(d.loc[d["class"] == "Silage", "ACRES"].sum()), 1),
        "silage_acres_expected": round(exp, 1),
        "silage_acres_95ci": [round(max(0.0, exp - 1.96 * sd), 1), round(exp + 1.96 * sd, 1)],
        "silage_share_of_decided": round(exp / float(d["ACRES"].sum()), 3) if len(d) else None,
        "undecided_acres": round(float(m.loc[~m["class"].isin(["Grain", "Silage"]), "ACRES"].sum()), 1),
    }


def get_quickstats(state: str = "MARYLAND", year: int | None = None) -> list[dict]:
    """NASS QuickStats corn grain/silage acres. (D)/(S)/(H) suppressed values dropped."""
    df = pd.read_csv(QUICKSTATS_CSV, dtype=str)
    cols = {c.lower(): c for c in df.columns}
    if "state_name" in cols or "state" in cols:
        sc = cols.get("state_name", cols.get("state"))
        df = df[df[sc].str.upper() == state.upper()]
    if year is not None and "year" in cols:
        df = df[df[cols["year"]] == str(year)]
    vc = cols.get("value")
    if vc:
        v = df[vc].str.strip().str.replace(",", "", regex=False)
        df = df[~v.str.match(r"^\(.*\)$", na=True)].copy()
        df[vc] = pd.to_numeric(v[df.index], errors="coerce")
    return _records(df)


def get_chip(objectid: int, year: int) -> dict:
    """Paths to pre/post harvest image chips and whether they exist."""
    out = {}
    for w in ("pre", "post"):
        p = io.chip_path(objectid, year, w)
        out[w] = {"path": str(p), "exists": p.exists()}
    return out


def write_report(markdown: str, name: str | None = None) -> dict:
    """Save an agent/analyst report to <handoff>/reports/."""
    name = name or datetime.now(timezone.utc).strftime("report_%Y%m%dT%H%M%SZ.md")
    p = io.handoff_dir() / "reports" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(markdown)
    return {"path": str(p), "bytes": len(markdown)}


# Registry for the agent: name -> (function, one-line description)
TOOLS = {f.__name__: (f, (f.__doc__ or "").strip().splitlines()[0]) for f in
         (get_fields, get_timeseries, classify, evaluate, aggregate,
          get_quickstats, get_chip, write_report)}
