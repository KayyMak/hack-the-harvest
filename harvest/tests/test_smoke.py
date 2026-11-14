"""Smoke tests on stub data: python -m pytest harvest/tests -q"""
import json

import pandas as pd
import pytest

from contracts.schemas import SchemaError, validate


@pytest.fixture(scope="module")
def stub(tmp_path_factory):
    import os
    d = tmp_path_factory.mktemp("handoff")
    os.environ["HANDOFF_DIR"] = str(d)
    from harvest import stub as s
    s.make(d)
    return d


def test_schema_rejects_bad():
    with pytest.raises(SchemaError):
        validate(pd.DataFrame({"OBJECTID": [1], "year": [2022], "label": ["Corn"]}), "labels")


def test_classify_and_evaluate(stub):
    from harvest import tools
    p = tools.classify(2022, "2022-11-30", "baseline")
    validate(pd.DataFrame(p), "predictions")
    e = tools.evaluate(p, 2022)
    json.dumps(e)
    assert e["always_grain_balanced_accuracy"] == 0.5
    assert len(e["confusion_matrix"]["values"]) == 2


def test_early_date_is_pending(stub):
    from harvest import tools
    p = tools.classify(2022, "2022-08-01", "baseline")
    assert {r["class"] for r in p} <= {"Pending", "Insufficient"}


def test_rollup_interval(stub):
    from harvest import tools
    r = tools.aggregate(tools.classify(2022, "2022-11-30", "baseline"))
    lo, hi = r["silage_acres_95ci"]
    assert lo <= r["silage_acres_expected"] <= hi


def test_run_writes_outputs(stub, tmp_path):
    from harvest.run import run
    run(2022, "2022-10-12", tmp_path / "out", "baseline")
    for f in ["predictions.parquet", "metrics.json", "rollup.json", "asof_sweep.json",
              "fields.geojson", "quickstats_export.csv"]:
        assert (tmp_path / "out" / f).exists(), f
