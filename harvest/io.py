"""Read/write hand-off files. Every table is validated against contracts.schemas."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd

from contracts.schemas import SCHEMAS, validate

DEFAULT_HANDOFF = "/workspace/data/handoff"


def handoff_dir() -> Path:
    return Path(os.environ.get("HANDOFF_DIR", DEFAULT_HANDOFF))


def _path(name: str, base: Path | None = None) -> Path:
    return (base or handoff_dir()) / f"{name}.parquet"


def read_table(name: str, base: Path | None = None) -> pd.DataFrame:
    """Read <name>.parquet (falls back to .csv) and validate it."""
    p = _path(name, base)
    if not p.exists() and p.with_suffix(".csv").exists():
        p = p.with_suffix(".csv")
    if not p.exists():
        raise FileNotFoundError(f"{name}: no {p.stem}.parquet or .csv in {p.parent}")
    df = pd.read_parquet(p) if p.suffix == ".parquet" else pd.read_csv(p)
    return validate(df, name)


def write_table(df: pd.DataFrame, name: str, base: Path | None = None) -> Path:
    df = validate(df, name)
    p = _path(name, base)
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(p, index=False)
    return p


def read_json(name: str, base: Path | None = None):
    p = (base or handoff_dir()) / name
    return json.loads(p.read_text()) if p.exists() else None


def write_json(obj, name: str, base: Path | None = None) -> Path:
    p = (base or handoff_dir()) / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2, default=str))
    return p


def chip_path(objectid: int, year: int, which: str, base: Path | None = None) -> Path:
    if which not in ("pre", "post"):
        raise ValueError("which must be 'pre' or 'post'")
    return (base or handoff_dir()) / "chips" / f"{objectid}_{year}_{which}.png"


def status(base: Path | None = None) -> dict:
    """Which hand-offs exist. Used by /health and the agent."""
    b = base or handoff_dir()
    out = {n: _path(n, b).exists() or _path(n, b).with_suffix(".csv").exists() for n in SCHEMAS}
    for f in ("metrics.json", "rollup.json", "trace.jsonl"):
        out[f] = (b / f).exists()
    out["chips"] = len(list((b / "chips").glob("*.png"))) if (b / "chips").exists() else 0
    return out
