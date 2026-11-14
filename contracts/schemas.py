"""Frozen hand-off contracts. Changing anything here needs whole-team sign-off."""
from __future__ import annotations

SCHEMAS = {
    "fields":      ["OBJECTID", "FARM", "FIELD", "ACRES", "area_m2", "geometry"],
    "labels":      ["OBJECTID", "year", "label"],  # Grain | Silage
    "field_dates": ["OBJECTID", "year", "date", "sensor", "ndvi", "evi", "ndre", "ndti", "clear_share"],
    "predictions": ["OBJECTID", "year", "as_of", "p_silage", "class", "abstain", "top_features", "model"],
}
CLASSES = {"Grain", "Silage", "Pending", "Insufficient"}
LABELS = {"Grain", "Silage"}

# Allowed value checks per schema (column -> predicate on the Series)
_CHECKS = {
    "labels": {"label": lambda s: s.isin(LABELS)},
    "field_dates": {
        "clear_share": lambda s: s.between(0, 1) | s.isna(),
    },
    "predictions": {
        "class": lambda s: s.isin(CLASSES),
        "p_silage": lambda s: s.between(0, 1) | s.isna(),
    },
}


class SchemaError(ValueError):
    pass


def validate(df, name: str, strict: bool = True):
    """Check df has exactly the frozen columns (strict) or at least them.

    Returns df with columns reordered to the contract. Raises SchemaError.
    """
    if name not in SCHEMAS:
        raise SchemaError(f"unknown schema '{name}', expected one of {list(SCHEMAS)}")
    want = SCHEMAS[name]
    have = list(df.columns)
    missing = [c for c in want if c not in have]
    extra = [c for c in have if c not in want]
    if missing:
        raise SchemaError(f"{name}: missing columns {missing}")
    if strict and extra:
        raise SchemaError(f"{name}: unexpected columns {extra} (frozen schema)")
    for col, ok in _CHECKS.get(name, {}).items():
        bad = ~ok(df[col])
        if bad.any():
            sample = df.loc[bad, col].head(3).tolist()
            raise SchemaError(f"{name}.{col}: {int(bad.sum())} invalid values, e.g. {sample}")
    return df[want] if strict else df
