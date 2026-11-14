"""Rule-based baseline, readable by a skeptic. ML can replace it via predictions.parquet.

Per field-year, using only clear observations on or before as_of:
  1. Too few clear looks              -> Insufficient (abstain)
  2. Find the biggest drop in NDVI between consecutive clear looks.
  3. Green before (>= GREEN), bare after (<= BARE), drop before SILAGE_BY,
     and little residue after (NDTI <= RESIDUE)   -> Silage
  4. A drop that fails those tests                -> Grain
  5. No sharp drop but NDVI already low (gradual browning) -> Grain
  6. Still green, no drop yet                      -> Pending
"""
from __future__ import annotations

import json

import pandas as pd

MIN_CLEAR = 0.5      # scene counts as clear if clear_share >= this
MIN_LOOKS = 4        # fewer clear looks than this -> Insufficient
GREEN = 0.60         # NDVI before the drop
BARE = 0.35          # NDVI after the drop
DROP = 0.25          # minimum NDVI drop to call it a harvest
SILAGE_BY = 268      # day of year (~Sep 25)
RESIDUE = 0.09       # NDTI after harvest; above = stalk residue (grain)
MODEL = "rule_baseline_v1"


def _one(g: pd.DataFrame) -> dict:
    g = g.sort_values("date")
    if len(g) < MIN_LOOKS:
        return dict(p_silage=None, cls="Insufficient", abstain=True,
                    feats=[{"name": "clear_looks", "value": len(g), "weight": None}])
    nd = g["ndvi"].to_numpy()
    drops = nd[:-1] - nd[1:]
    i = int(drops.argmax())
    pre, post, d = nd[i], nd[i + 1], drops[i]
    when = g["date"].iloc[i + 1]
    post_ndti = float(g["ndti"].iloc[i + 1:i + 3].mean())
    feats = [
        {"name": "pre_drop_ndvi", "value": round(float(pre), 3), "weight": None},
        {"name": "post_drop_ndvi", "value": round(float(post), 3), "weight": None},
        {"name": "drop_doy", "value": int(when.dayofyear), "weight": None},
        {"name": "post_ndti", "value": round(post_ndti, 3), "weight": None},
    ]
    if d < DROP or post > BARE:
        if nd[-1] <= BARE and nd.max() >= GREEN:  # browned down slowly: grain pattern
            return dict(p_silage=0.1, cls="Grain", abstain=False, feats=feats)
        return dict(p_silage=None, cls="Pending", abstain=False, feats=feats)
    tests = [pre >= GREEN, when.dayofyear <= SILAGE_BY, post_ndti <= RESIDUE]
    p = float(sum(tests)) / 3  # share of silage tests passed; crude but explainable
    return dict(p_silage=round(p, 3), cls="Silage" if all(tests) else "Grain",
                abstain=False, feats=feats)


def predict(field_dates: pd.DataFrame, as_of: str, year: int | None = None) -> pd.DataFrame:
    fd = field_dates.copy()
    fd["date"] = pd.to_datetime(fd["date"])
    cut = pd.Timestamp(as_of)
    if year is not None:
        fd = fd[fd["year"] == year]
    fd = fd[(fd["date"] <= cut) & (fd["clear_share"] >= MIN_CLEAR) & fd["ndvi"].notna()]
    rows = []
    for (oid, yr), g in fd.groupby(["OBJECTID", "year"]):
        r = _one(g)
        rows.append({"OBJECTID": int(oid), "year": int(yr), "as_of": as_of,
                     "p_silage": r["p_silage"], "class": r["cls"], "abstain": r["abstain"],
                     "top_features": json.dumps(r["feats"]), "model": MODEL})
    return pd.DataFrame(rows, columns=["OBJECTID", "year", "as_of", "p_silage", "class",
                                       "abstain", "top_features", "model"])
