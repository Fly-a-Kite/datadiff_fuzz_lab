import importlib.util

import pytest

from datadiff.datagen import generate_case
from datadiff.runner import run_loaded_case


REQUIRED_BACKENDS = ["pandas", "polars", "duckdb"]


@pytest.mark.skipif(
    any(importlib.util.find_spec(name) is None for name in REQUIRED_BACKENDS),
    reason="data backends are not installed",
)
def test_run_loaded_case_smoke():
    case = generate_case(11)
    row = run_loaded_case(case, REQUIRED_BACKENDS, save_artifact=False)
    assert row["case"]["case_id"] == "case-00000011"
    assert set(row["normalized"]) == set(REQUIRED_BACKENDS)
    assert row["status"] in {"ok", "bug"}
    assert row["behavior_signature"]
