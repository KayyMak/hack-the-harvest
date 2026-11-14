"""Fake hand-off data that matches the frozen schemas, so API/web/agent can work
before geo and ML deliver. Run: python -m harvest.stub --out <dir>

Fake rows are tagged model='stub' so they are never confused with real output.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from harvest.io import write_json, write_table

LAT0, LON0 = 39.03, -76.93  # roughly BARC, Beltsville MD
YEARS = (2021, 2022, 2023)


def _square(lon, lat, d=0.003):
    pts = [(lon, lat), (lon + d, lat), (lon + d, lat + d), (lon, lat + d), (lon, lat)]
    return "POLYGON ((" + ", ".join(f"{x:.6f} {y:.6f}" for x, y in pts) + "))"


def _series(rng, silage: bool, year: int):
    """Weekly NDVI-ish curve. Silage drops sharply ~early Sep, grain browns into Oct."""
    dates = pd.date_range(f"{year}-05-01", f"{year}-11-30", freq="7D")
    doy = dates.dayofyear.to_numpy()
    green = 0.2 + 0.65 / (1 + np.exp(-(doy - 165) / 8))
    if silage:
        cut = rng.integers(235, 255)
        ndvi = np.where(doy < cut, green, 0.18)
        ndti = np.where(doy < cut, 0.05, 0.03)  # bare soil, low residue
    else:
        ndvi = green - np.clip((doy - 225) / 60, 0, 1) * 0.55
        cut = rng.integers(280, 310)
        ndvi = np.where(doy < cut, ndvi, 0.22)
        ndti = np.where(doy < cut, 0.05, 0.14)  # stalk residue
    ndvi = np.clip(ndvi + rng.normal(0, 0.03, len(doy)), -1, 1)
    clear = rng.uniform(0, 1, len(doy))
    return pd.DataFrame({
        "date": dates.date.astype(str),
        "sensor": rng.choice(["S2", "L8", "L9"], len(doy), p=[0.6, 0.2, 0.2]),
        "ndvi": ndvi,
        "evi": ndvi * 0.8,
        "ndre": ndvi * 0.6,
        "ndti": ndti + rng.normal(0, 0.01, len(doy)),
        "clear_share": clear.round(2),
    })[clear > 0.3]  # cloudy scenes dropped, like real data


def make(out: Path, n_fields: int = 20, seed: int = 0):
    rng = np.random.default_rng(seed)
    ids = np.arange(1, n_fields + 1)
    fields = pd.DataFrame({
        "OBJECTID": ids,
        "FARM": [f"Farm{(i - 1) // 5 + 1}" for i in ids],
        "FIELD": [f"F{i}" for i in ids],
        "ACRES": rng.uniform(5, 40, n_fields).round(1),
        "geometry": [_square(LON0 + (i % 5) * 0.004, LAT0 + (i // 5) * 0.004) for i in ids],
    })
    fields.insert(4, "area_m2", (fields["ACRES"] * 4046.86).round(0))
    write_table(fields, "fields", out)

    lab_rows, ts = [], []
    for y in YEARS:
        for i in rng.choice(ids, 15, replace=False):
            silage = rng.random() < 0.27  # ~12/44 like BARC
            lab_rows.append((int(i), y, "Silage" if silage else "Grain"))
            s = _series(rng, silage, y)
            s.insert(0, "year", y)
            s.insert(0, "OBJECTID", int(i))
            ts.append(s)
    labels = pd.DataFrame(lab_rows, columns=["OBJECTID", "year", "label"])
    write_table(labels, "labels", out)
    write_table(pd.concat(ts, ignore_index=True), "field_dates", out)

    preds = labels.copy()
    preds["as_of"] = preds["year"].astype(str) + "-10-12"
    p = np.where(preds["label"] == "Silage", rng.uniform(0.5, 0.95, len(preds)), rng.uniform(0.02, 0.6, len(preds)))
    preds["p_silage"] = p.round(3)
    preds["abstain"] = rng.random(len(preds)) < 0.1
    preds["class"] = np.where(preds["abstain"], "Insufficient", np.where(p >= 0.5, "Silage", "Grain"))
    preds["top_features"] = [json.dumps([{"name": "pre_drop_ndvi", "value": 0.8, "weight": 1.2},
                                         {"name": "post_ndti", "value": 0.05, "weight": -0.9}])] * len(preds)
    preds["model"] = "stub"
    write_table(preds.drop(columns="label"), "predictions", out)
    write_json({"model": "stub", "note": "fake numbers"}, "metrics.json", out)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    print("stub written to", make(Path(a.out)))
