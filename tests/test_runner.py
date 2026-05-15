import importlib.util
from pathlib import Path

import pytest

from datadiff.config import ExperimentConfig
from datadiff.datagen import generate_case
from datadiff.dsl import Case, ColumnSpec, Program, TableData
from datadiff.runner import run_fuzz, run_loaded_case
from datadiff.util import load_json, read_jsonl, run_meta_path


REQUIRED_BACKENDS = ["pandas", "polars", "duckdb", "sqlite"]
DATAFUSION_BACKENDS = ["pandas", "duckdb", "datafusion"]
PYARROW_BACKENDS = ["pandas", "duckdb", "pyarrow"]


@pytest.mark.skipif(
    any(name != "sqlite" and importlib.util.find_spec(name) is None for name in REQUIRED_BACKENDS),
    reason="data backends are not installed",
)
def test_run_loaded_case_smoke():
    case = generate_case(11)
    row = run_loaded_case(case, REQUIRED_BACKENDS, save_artifact=False)
    assert row["case"]["case_id"] == "case-00000011"
    assert set(row["normalized"]) == set(REQUIRED_BACKENDS)
    assert row["status"] in {"ok", "bug"}
    assert row["behavior_signature"]


@pytest.mark.skipif(
    any(name != "sqlite" and importlib.util.find_spec(name) is None for name in REQUIRED_BACKENDS),
    reason="data backends are not installed",
)
def test_run_loaded_case_supports_join_expressions_and_multi_agg():
    case = Case(
        "case-join-expr",
        99,
        [
            TableData(
                "t0",
                [
                    ColumnSpec("id", "int", nullable=False),
                    ColumnSpec("g", "str"),
                    ColumnSpec("x", "int"),
                ],
                [
                    {"id": 1, "g": "Alpha", "x": 2},
                    {"id": 2, "g": "中文", "x": None},
                    {"id": 3, "g": None, "x": 5},
                ],
            ),
            TableData(
                "t1",
                [
                    ColumnSpec("id", "int", nullable=False),
                    ColumnSpec("j", "int"),
                    ColumnSpec("tag", "str"),
                ],
                [
                    {"id": 1, "j": 10, "tag": "One"},
                    {"id": 1, "j": 20, "tag": "Two"},
                    {"id": 3, "j": None, "tag": "Three"},
                ],
            ),
        ],
        Program(
            "prog-join-expr",
            99,
            [
                {"op": "join", "table": "t1", "left_on": "id", "right_on": "id", "how": "left"},
                {"op": "mutate", "column": "x_mul", "expr": {"kind": "arith_const", "source": "x", "op": "mul", "value": 2}},
                {"op": "mutate", "column": "g_len", "expr": {"kind": "string_length", "source": "g"}},
                {"op": "mutate", "column": "tag_l", "expr": {"kind": "string_lower", "source": "tag"}},
                {
                    "op": "groupby",
                    "keys": ["id"],
                    "aggs": [
                        {"column": "x_mul", "func": "sum", "as": "sum_x_mul"},
                        {"column": "g_len", "func": "max", "as": "max_g_len"},
                        {"column": "j", "func": "count", "as": "count_j"},
                    ],
                },
            ],
        ),
    )
    row = run_loaded_case(case, REQUIRED_BACKENDS, save_artifact=False)
    assert row["status"] == "ok"
    assert set(row["normalized"]) == set(REQUIRED_BACKENDS)


@pytest.mark.skipif(
    any(importlib.util.find_spec(name) is None for name in ["pandas", "duckdb", "datafusion", "pyarrow"]),
    reason="datafusion test backends are not installed",
)
def test_datafusion_backend_matches_common_join_groupby_case():
    case = Case(
        "case-datafusion-join-groupby",
        777,
        [
            TableData(
                "t0",
                [
                    ColumnSpec("id", "int", nullable=False),
                    ColumnSpec("g", "str"),
                    ColumnSpec("x", "int"),
                ],
                [
                    {"id": 1, "g": "alpha", "x": 2},
                    {"id": 2, "g": None, "x": None},
                    {"id": 3, "g": "beta", "x": 5},
                ],
            ),
            TableData(
                "t1",
                [
                    ColumnSpec("id", "int", nullable=False),
                    ColumnSpec("z", "float"),
                    ColumnSpec("tag", "str"),
                ],
                [
                    {"id": 1, "z": 10.0, "tag": "One"},
                    {"id": 1, "z": 20.0, "tag": "Two"},
                    {"id": 3, "z": None, "tag": "Three"},
                ],
            ),
        ],
        Program(
            "prog-datafusion-join-groupby",
            777,
            [
                {"op": "join", "table": "t1", "left_on": "id", "right_on": "id", "how": "left"},
                {"op": "mutate", "column": "x_div", "expr": {"kind": "arith_const", "source": "x", "op": "div", "value": 2}},
                {
                    "op": "groupby",
                    "keys": ["g"],
                    "aggs": [
                        {"column": "x_div", "func": "sum", "as": "sum_x_div"},
                        {"column": "z", "func": "min", "as": "min_z"},
                    ],
                },
            ],
        ),
    )

    row = run_loaded_case(case, DATAFUSION_BACKENDS, save_artifact=False)

    assert row["status"] == "ok"
    assert set(row["normalized"]) == set(DATAFUSION_BACKENDS)


@pytest.mark.skipif(
    any(importlib.util.find_spec(name) is None for name in ["pandas", "duckdb", "datafusion", "pyarrow"]),
    reason="datafusion test backends are not installed",
)
def test_datafusion_backend_applies_limit_to_sorted_rows():
    case = Case(
        "case-datafusion-sort-limit",
        778,
        [
            TableData(
                "t0",
                [ColumnSpec("x", "int")],
                [{"x": 1}, {"x": 5}, {"x": 3}, {"x": 2}],
            )
        ],
        Program(
            "prog-datafusion-sort-limit",
            778,
            [
                {"op": "sort", "columns": ["x"], "ascending": False},
                {"op": "limit", "n": 2},
            ],
        ),
    )

    row = run_loaded_case(
        case,
        DATAFUSION_BACKENDS,
        config=ExperimentConfig(enable_metamorphic_oracle=False),
        save_artifact=False,
    )

    assert row["status"] == "ok"
    assert {tuple(tuple(r) for r in result["rows"]) for result in row["normalized"].values()} == {
        ((3,), (5,))
    }


@pytest.mark.skipif(
    any(importlib.util.find_spec(name) is None for name in ["pandas", "duckdb", "datafusion", "pyarrow"]),
    reason="datafusion test backends are not installed",
)
def test_datafusion_backend_preserves_sort_through_select_before_limit():
    case = Case(
        "case-datafusion-sort-select-limit",
        780,
        [
            TableData(
                "t0",
                [
                    ColumnSpec("id", "int", nullable=False),
                    ColumnSpec("y", "float"),
                    ColumnSpec("flag", "bool"),
                    ColumnSpec("s", "str"),
                ],
                [
                    {"id": 0, "y": -1.0, "flag": True, "s": "alpha"},
                    {"id": 16, "y": None, "flag": True, "s": "alpha"},
                    {"id": 0, "y": 0.5, "flag": True, "s": "wtiApSjd"},
                ],
            ),
            TableData(
                "t1",
                [
                    ColumnSpec("id", "int", nullable=False),
                    ColumnSpec("j", "int"),
                    ColumnSpec("z", "float"),
                    ColumnSpec("tag", "str"),
                ],
                [
                    {"id": 0, "j": 2, "z": -0.5, "tag": "gamma"},
                    {"id": 0, "j": None, "z": 0.5, "tag": "beta"},
                    {"id": 0, "j": 10, "z": -1.0, "tag": "zh"},
                    {"id": 0, "j": -2, "z": 1.0, "tag": "f"},
                    {"id": 16, "j": 16, "z": 16.0, "tag": "tag_16"},
                ],
            ),
        ],
        Program(
            "prog-datafusion-sort-select-limit",
            780,
            [
                {"op": "join", "table": "t1", "left_on": "id", "right_on": "id", "how": "left"},
                {"op": "select", "columns": ["flag", "id", "j", "s", "y", "z"]},
                {"op": "sort", "columns": ["s", "flag", "id", "j", "y", "z"], "ascending": True},
                {"op": "limit", "n": 4},
            ],
        ),
    )

    row = run_loaded_case(
        case,
        DATAFUSION_BACKENDS,
        config=ExperimentConfig(enable_metamorphic_oracle=True, metamorphic_variant_limit=20),
        save_artifact=False,
    )

    assert row["status"] == "ok"
    variant = row["metamorphic"]["sort_select_commutation:swap-1-2"]
    assert variant["normalized"]["datafusion"]["rows"] == row["normalized"]["datafusion"]["rows"]


@pytest.mark.skipif(
    any(importlib.util.find_spec(name) is None for name in ["pandas", "duckdb", "pyarrow"]),
    reason="pyarrow test backends are not installed",
)
def test_pyarrow_backend_matches_common_join_groupby_case():
    case = Case(
        "case-pyarrow-join-groupby",
        779,
        [
            TableData(
                "t0",
                [
                    ColumnSpec("id", "int", nullable=False),
                    ColumnSpec("g", "str"),
                    ColumnSpec("x", "int"),
                ],
                [
                    {"id": 1, "g": "alpha", "x": 2},
                    {"id": 2, "g": None, "x": None},
                    {"id": 3, "g": "beta", "x": 5},
                ],
            ),
            TableData(
                "t1",
                [
                    ColumnSpec("id", "int", nullable=False),
                    ColumnSpec("z", "float"),
                    ColumnSpec("tag", "str"),
                ],
                [
                    {"id": 1, "z": 10.0, "tag": "One"},
                    {"id": 1, "z": 20.0, "tag": "Two"},
                    {"id": 3, "z": None, "tag": "Three"},
                ],
            ),
        ],
        Program(
            "prog-pyarrow-join-groupby",
            779,
            [
                {"op": "join", "table": "t1", "left_on": "id", "right_on": "id", "how": "left"},
                {"op": "mutate", "column": "x_div", "expr": {"kind": "arith_const", "source": "x", "op": "div", "value": 2}},
                {
                    "op": "groupby",
                    "keys": ["g"],
                    "aggs": [
                        {"column": "x_div", "func": "sum", "as": "sum_x_div"},
                        {"column": "z", "func": "min", "as": "min_z"},
                    ],
                },
                {"op": "sort", "columns": ["g", "sum_x_div", "min_z"], "ascending": True},
            ],
        ),
    )

    row = run_loaded_case(case, PYARROW_BACKENDS, save_artifact=False)

    assert row["status"] == "ok"
    assert set(row["normalized"]) == set(PYARROW_BACKENDS)


@pytest.mark.skipif(importlib.util.find_spec("polars") is None, reason="polars is not installed")
def test_polars_backend_preserves_empty_table_schema():
    case = Case(
        "case-empty-polars-schema",
        521,
        [TableData("t0", [ColumnSpec("g", "str")], [])],
        Program(
            "prog-empty-polars-schema",
            521,
            [
                {"op": "mutate", "column": "m_0", "expr": {"kind": "string_length", "source": "g"}},
                {"op": "filter", "column": "m_0", "cmp": "==", "value": -1},
            ],
        ),
    )

    row = run_loaded_case(case, ["polars"], save_artifact=False)

    assert row["normalized"]["polars"]["status"] == "ok"
    assert row["findings"] == []


@pytest.mark.skipif(importlib.util.find_spec("polars") is None, reason="polars is not installed")
def test_polars_lazy_backend_matches_polars_eager_on_common_case():
    case = generate_case(91, profile="bughunt")

    row = run_loaded_case(case, ["polars", "polars_lazy"], save_artifact=False)

    assert row["status"] == "ok"
    assert row["findings"] == []
    assert set(row["normalized"]) == {"polars", "polars_lazy"}


@pytest.mark.skipif(
    any(name != "sqlite" and importlib.util.find_spec(name) is None for name in REQUIRED_BACKENDS),
    reason="data backends are not installed",
)
def test_sql_backends_treat_mutate_as_column_replacement():
    case = Case(
        "case-replace-mutate",
        6534,
        [
            TableData(
                "t0",
                [ColumnSpec("y", "float")],
                [{"y": None}],
            )
        ],
        Program(
            "prog-replace-mutate",
            6534,
            [
                {"op": "filter", "column": "y", "cmp": ">=", "value": 0.0},
                {"op": "mutate", "column": "m_1", "expr": {"kind": "cast", "source": "y", "to": "float"}},
                {"op": "mutate", "column": "m_1", "expr": {"kind": "add_const", "source": "m_1", "value": -1}},
            ],
        ),
    )

    row = run_loaded_case(case, REQUIRED_BACKENDS, save_artifact=False)

    assert row["status"] == "ok"
    assert {tuple(result["columns"]) for result in row["normalized"].values()} == {("m_1", "y")}


@pytest.mark.skipif(
    any(name != "sqlite" and importlib.util.find_spec(name) is None for name in REQUIRED_BACKENDS),
    reason="data backends are not installed",
)
def test_run_fuzz_records_duration_and_feedback():
    run_file = run_fuzz(cases=2, seed=21, backends=REQUIRED_BACKENDS, duration_s=None)
    rows = read_jsonl(run_file)
    assert len(rows) == 2
    assert all("elapsed_s" in row for row in rows)
    assert all("stored_in_feedback_corpus" in row for row in rows)


def test_run_fuzz_can_persist_generated_cases_and_checkpoint(tmp_path):
    case_log = tmp_path / "generated.cases.jsonl"
    run_file = run_fuzz(
        cases=2,
        seed=31,
        backends=[],
        duration_s=None,
        save_cases=True,
        case_log_file=case_log,
        checkpoint_interval_s=0.0,
    )

    generated = read_jsonl(case_log)
    assert len(generated) == 2
    assert [row["seed"] for row in generated] == [31, 32]
    assert generated[0]["case"]["case_id"] == "case-00000031"

    meta = load_json(run_meta_path(run_file))
    checkpoint = load_json(Path(meta["checkpoint_file"]))
    assert meta["case_log_file"] == str(case_log)
    assert meta["executed_cases"] == 2
    assert "preflight" in meta
    assert "quality_oracles" in meta
    rows = read_jsonl(run_file)
    assert all("quality_oracles" in row for row in rows)
    assert all("preflight" in row for row in rows)
    assert checkpoint["status"] == "completed"
    assert checkpoint["next_seed"] == 33


def test_run_fuzz_records_guidance_metadata(tmp_path):
    case_log = tmp_path / "guided.cases.jsonl"
    config = ExperimentConfig(
        guidance_strategy="guided",
        guidance_candidate_pool=4,
        guidance_targets=["groupby"],
    )

    run_file = run_fuzz(cases=1, seed=41, backends=[], config=config, case_log_file=case_log)

    row = read_jsonl(run_file)[0]
    case_log_row = read_jsonl(case_log)[0]
    meta = load_json(run_meta_path(run_file))
    assert row["guidance"]["candidate_count"] == 4
    assert row["guidance"]["contributing_candidate_count"] >= 1
    assert row["guidance"]["pruned_candidate_count"] >= 0
    assert "frontier_conformance" in row["guidance"]
    assert "data_sensitivity" in row["guidance"]
    assert "path_coverage_proxy" in row["guidance"]
    assert case_log_row["candidate_pool_size"] == 4
    assert meta["guidance"]["strategy"] == "guided"
    assert meta["next_seed"] == 45


def test_run_fuzz_compact_log_omits_repeated_run_metadata():
    run_file = run_fuzz(cases=1, seed=51, backends=[], duration_s=None)

    row = read_jsonl(run_file)[0]
    meta = load_json(run_meta_path(run_file))
    assert run_file.name.endswith(".jsonl.gz")
    assert meta["log_level"] == "compact"
    assert "environment" not in row
    assert "targets" not in row
    assert "config" not in row
    assert "tables" not in row["case"]
    assert "normalized" in row


def test_run_fuzz_minimal_log_keeps_only_backend_status():
    config = ExperimentConfig(log_level="minimal")

    run_file = run_fuzz(cases=1, seed=52, backends=[], config=config)

    row = read_jsonl(run_file)[0]
    assert "normalized" not in row
    assert "raw_results" not in row
    assert row["backend_status"] == {}
    assert "frontier_conformance" in row["guidance"]


def test_run_fuzz_can_disable_run_log_compression():
    config = ExperimentConfig(compress_run_log=False)

    run_file = run_fuzz(cases=1, seed=53, backends=[], config=config)

    assert run_file.name.endswith(".jsonl")
    assert not run_file.name.endswith(".jsonl.gz")
    assert load_json(run_meta_path(run_file))["config"]["compress_run_log"] is False


def test_run_loaded_case_honors_metamorphic_variant_limit():
    case = generate_case(61, profile="bughunt")
    config = ExperimentConfig(enable_metamorphic_oracle=True, metamorphic_variant_limit=2)

    row = run_loaded_case(case, [], config=config, save_artifact=False)

    assert len(row["metamorphic"]) <= 2
    assert row["config"]["metamorphic_variant_limit"] == 2
