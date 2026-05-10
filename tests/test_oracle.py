from datadiff.datagen import generate_case
from datadiff.normalizer import NormalizedResult
from datadiff.oracle import evaluate_case


def test_oracle_accept_reject_mismatch():
    case = generate_case(1)
    findings = evaluate_case(
        case,
        {
            "a": NormalizedResult("a", "ok", ["x"], [[1]]),
            "b": NormalizedResult("b", "error", [], [], "ValueError", "bad"),
        },
    )
    assert findings
    assert findings[0].kind == "accept_reject_mismatch"
    assert findings[0].severity == "high"
    assert findings[0].oracle == "differential"
    assert findings[0].root_cause


def test_oracle_semantic_output_mismatch():
    case = generate_case(2)
    findings = evaluate_case(
        case,
        {
            "a": NormalizedResult("a", "ok", ["x"], [[1]]),
            "b": NormalizedResult("b", "ok", ["x"], [[2]]),
        },
    )
    assert findings
    assert findings[0].kind == "semantic_output_mismatch"
    assert findings[0].confidence in {"high", "medium"}


def test_oracle_no_mismatch_for_equal_results():
    case = generate_case(3)
    findings = evaluate_case(
        case,
        {
            "a": NormalizedResult("a", "ok", ["x"], [[1]]),
            "b": NormalizedResult("b", "ok", ["x"], [[1]]),
        },
    )
    assert findings == []
