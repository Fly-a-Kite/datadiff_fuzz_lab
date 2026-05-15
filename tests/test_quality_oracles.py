from datadiff.dsl import Case, ColumnSpec, Program, TableData
from datadiff.quality_oracles import feedback_oracle, guidance_oracle, mutation_oracle


def _case() -> Case:
    return Case(
        "case-x",
        1,
        [
            TableData(
                "t0",
                [ColumnSpec("x", "int"), ColumnSpec("g", "str")],
                [{"x": 1, "g": "a"}, {"x": 2, "g": "b"}],
            )
        ],
        Program(
            "prog-x",
            1,
            [{"op": "groupby", "keys": ["g"], "aggs": [{"column": "x", "func": "sum", "as": "sum_x"}]}],
        ),
    )


def test_mutation_oracle_marks_productive_feedback_mutation():
    result = mutation_oracle(
        _case(),
        {"is_new_behavior": True, "findings": []},
        candidate_source="feedback_mutation",
        preflight={"valid": True, "repaired": False, "fallback_used": False},
    )

    assert result.verdict == "productive_mutation"
    assert result.passed is True


def test_feedback_oracle_marks_redundant_behavior():
    result = feedback_oracle(
        {
            "is_new_behavior": False,
            "findings": [],
            "stored_in_feedback_corpus": False,
            "behavior_signature": "abc",
        }
    )

    assert result.verdict == "redundant_behavior"
    assert result.passed is False


def test_guidance_oracle_checks_target_hit_and_productivity():
    result = guidance_oracle(
        _case(),
        {"is_new_behavior": True, "findings": []},
        guidance_decision={
            "score": 3.0,
            "matched_targets": ["groupby"],
            "candidate_count": 4,
            "contributing_candidate_count": 2,
            "pruned_candidate_count": 2,
            "frontier_buckets": ["groupby:mixed-cardinality"],
            "score_breakdown": {"frontier_conformance": 0.9, "contribution_potential": 1.4},
        },
        guidance_strategy="guided",
        guidance_targets=["groupby"],
    )

    assert result.verdict == "guided_productive"
    assert result.passed is True
    assert result.metrics["matched_targets"] == ["groupby"]
    assert result.metrics["pruned_candidate_count"] == 2
    assert result.metrics["frontier_conformance"] == 0.9
