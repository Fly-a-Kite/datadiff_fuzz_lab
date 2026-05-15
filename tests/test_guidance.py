from datadiff.dsl import Case, ColumnSpec, Program, TableData
from datadiff.guidance import GuidanceState, extract_case_features, parse_guidance_targets


def _case(seed: int, operations: list[dict]) -> Case:
    table = TableData(
        name="t0",
        columns=[
            ColumnSpec("id", "int", nullable=False),
            ColumnSpec("g", "str", nullable=True),
            ColumnSpec("x", "int", nullable=True),
        ],
        rows=[
            {"id": 0, "g": "alpha", "x": 1},
            {"id": 1, "g": "中文", "x": None},
            {"id": 1, "g": "", "x": -1},
        ],
    )
    return Case(
        case_id=f"case-{seed:08d}",
        seed=seed,
        tables=[table],
        program=Program(program_id=f"prog-{seed:08d}", seed=seed, operations=operations),
    )


def test_extract_case_features_tracks_structure_and_values():
    case = _case(
        1,
        [
            {"op": "filter", "column": "x", "cmp": ">=", "value": 0},
            {"op": "sort", "columns": ["g", "id", "x"], "ascending": False},
        ],
    )

    features = extract_case_features(case)
    assert "op:filter" in features
    assert "cmp:>=" in features
    assert "op:sort" in features
    assert "sort:desc" in features
    assert "has:null" in features
    assert "has:unicode_string" in features
    assert "has:empty_string" in features


def test_guidance_prefers_targeted_candidate():
    filter_case = _case(1, [{"op": "filter", "column": "x", "cmp": ">", "value": 0}])
    groupby_case = _case(
        2,
        [{"op": "groupby", "keys": ["g"], "aggs": [{"column": "x", "func": "sum", "as": "sum_x"}]}],
    )
    guidance = GuidanceState(targets=["groupby"])

    decision = guidance.choose_case([filter_case, groupby_case])

    assert decision.case is groupby_case
    assert decision.matched_targets == ["groupby"]
    assert decision.candidate_count == 2


def test_guidance_recognizes_null_groupby_topk_pattern():
    ordinary_case = _case(
        1,
        [{"op": "groupby", "keys": ["g"], "aggs": [{"column": "x", "func": "count", "as": "count_x"}]}],
    )
    topk_case = Case(
        "case-null-groupby-topk",
        2,
        [
            TableData(
                "t0",
                [ColumnSpec("x", "int"), ColumnSpec("s", "str")],
                [{"x": 1, "s": None}],
            )
        ],
        Program(
            "prog-null-groupby-topk",
            2,
            [
                {"op": "mutate", "column": "m_0", "expr": {"kind": "string_length", "source": "s"}},
                {
                    "op": "groupby",
                    "keys": ["m_0"],
                    "aggs": [{"column": "x", "func": "count", "as": "count_x"}],
                },
                {"op": "select", "columns": ["m_0"]},
                {"op": "sort", "columns": ["m_0"], "ascending": False},
                {"op": "limit", "n": 5},
            ],
        ),
    )
    guidance = GuidanceState(targets=["null_groupby_topk"])

    features = extract_case_features(topk_case)
    decision = guidance.choose_case([ordinary_case, topk_case])

    assert "groupby:null-key" in features
    assert "sort:null-order" in features
    assert "pattern:null_groupby_topk" in features
    assert decision.case is topk_case
    assert decision.matched_targets == ["null_groupby_topk"]


def test_guidance_recognizes_null_agg_topk_pattern():
    case = Case(
        "case-null-agg-topk",
        3,
        [
            TableData(
                "t0",
                [ColumnSpec("g", "str", nullable=False), ColumnSpec("x", "int")],
                [{"g": "a", "x": None}, {"g": "b", "x": 5}],
            )
        ],
        Program(
            "prog-null-agg-topk",
            3,
            [
                {"op": "groupby", "keys": ["g"], "aggs": [{"column": "x", "func": "min", "as": "min_x"}]},
                {"op": "select", "columns": ["min_x"]},
                {"op": "sort", "columns": ["min_x"], "ascending": True},
                {"op": "limit", "n": 4},
            ],
        ),
    )
    guidance = GuidanceState(targets=["null_agg_topk"])

    features = extract_case_features(case)
    decision = guidance.choose_case([case])

    assert "groupby:null-agg-output" in features
    assert "sort:null-order" in features
    assert "pattern:null_agg_topk" in features
    assert decision.matched_targets == ["null_agg_topk"]


def test_guidance_penalizes_saturated_finding_features():
    join_case = _case(1, [{"op": "join", "table": "t1", "how": "inner", "on": ["id"]}])
    novel_case = _case(2, [{"op": "mutate", "column": "x2", "expr": {"kind": "cast", "column": "x", "to": "str"}}])
    guidance = GuidanceState()

    for idx in range(80):
        guidance.record_result(
            join_case,
            {
                "findings": [
                    {
                        "kind": "semantic_output_mismatch",
                        "root_cause": "join_semantics",
                    }
                ]
            },
        )

    decision = guidance.choose_case([join_case, novel_case])

    assert decision.case is novel_case
    assert decision.score_breakdown["root_saturation_penalty"] <= 0.0


def test_guidance_keeps_target_priority_under_saturation():
    join_case = Case(
        "case-join",
        1,
        [
            TableData(
                "t0",
                [
                    ColumnSpec("id", "int", nullable=False),
                    ColumnSpec("g", "str", nullable=True),
                    ColumnSpec("x", "int", nullable=True),
                ],
                [
                    {"id": 0, "g": "alpha", "x": 1},
                    {"id": 1, "g": "中文", "x": None},
                    {"id": 1, "g": "", "x": -1},
                ],
            ),
            TableData(
                "t1",
                [
                    ColumnSpec("id", "int", nullable=False),
                    ColumnSpec("j", "int", nullable=True),
                ],
                [
                    {"id": 1, "j": 10},
                    {"id": 2, "j": 20},
                ],
            ),
        ],
        Program("prog-join", 1, [{"op": "join", "table": "t1", "left_on": "id", "right_on": "id", "how": "left"}]),
    )
    filter_case = _case(2, [{"op": "filter", "column": "x", "cmp": ">", "value": 0}])
    guidance = GuidanceState(targets=["join"])

    for idx in range(80):
        guidance.record_result(
            join_case,
            {
                "findings": [
                    {
                        "kind": "semantic_output_mismatch",
                        "root_cause": "join_semantics",
                    }
                ]
            },
        )

    decision = guidance.choose_case([join_case, filter_case])

    assert decision.case is join_case
    assert decision.matched_targets == ["join"]
    assert decision.score_breakdown["target_bonus"] == 3.0


def test_guidance_uses_data_sensitivity_and_path_coverage_breakdown():
    simple_case = _case(1, [{"op": "select", "columns": ["id"]}])
    sensitive_case = _case(
        2,
        [
            {"op": "filter", "column": "x", "cmp": ">=", "value": 0},
            {"op": "mutate", "column": "m_0", "expr": {"kind": "string_length", "source": "g"}},
        ],
    )
    guidance = GuidanceState()

    decision = guidance.choose_case([simple_case, sensitive_case])

    assert decision.case is sensitive_case
    assert "data_sensitivity" in decision.score_breakdown
    assert "path_coverage_proxy" in decision.score_breakdown
    assert "frontier_conformance" in decision.score_breakdown
    assert "contribution_potential" in decision.score_breakdown
    assert decision.score_breakdown["data_sensitivity"] > 0.0
    assert decision.score_breakdown["path_coverage_proxy"] > 0.0
    assert decision.score_breakdown["frontier_conformance"] > 0.0


def test_guidance_frontier_conformance_prefers_boundary_case():
    simple_case = _case(1, [{"op": "select", "columns": ["id"]}])
    boundary_case = _case(2, [{"op": "filter", "column": "x", "cmp": "==", "value": 1}])
    guidance = GuidanceState()

    decision = guidance.choose_case([simple_case, boundary_case])

    assert decision.case is boundary_case
    assert "filter:exact-hit" in decision.frontier_buckets
    assert decision.score_breakdown["frontier_conformance"] >= 0.8


def test_guidance_prunes_obviously_redundant_candidates():
    redundant_case = _case(1, [{"op": "select", "columns": ["id"]}])
    useful_case = _case(2, [{"op": "filter", "column": "x", "cmp": "==", "value": 1}])
    guidance = GuidanceState()

    for _ in range(40):
        guidance.record_result(redundant_case, {"findings": []})

    decision = guidance.choose_case([redundant_case, useful_case])

    assert decision.case is useful_case
    assert decision.contributing_candidate_count == 1
    assert decision.pruned_candidate_count == 1


def test_parse_guidance_targets_ignores_empty_parts():
    assert parse_guidance_targets("groupby, ,nulls") == ["groupby", "nulls"]
