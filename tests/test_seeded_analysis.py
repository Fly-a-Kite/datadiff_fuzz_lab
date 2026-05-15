import csv

from datadiff import seeded_analysis
from datadiff.seeded_analysis import analyze_seeded_sensitivity
from datadiff.util import append_jsonl, dump_json, run_meta_path


def _write_seeded_run(path, *, expected_indexes, other_candidate_indexes):
    for idx in range(4):
        findings = []
        if idx in expected_indexes:
            findings.append(
                {
                    "kind": "semantic_output_mismatch",
                    "root_cause": "join_semantics",
                    "triage_verdict": "candidate_implementation_bug",
                    "suspicious_backends": ["buggy_join"],
                }
            )
        if idx in other_candidate_indexes:
            findings.append(
                {
                    "kind": "semantic_output_mismatch",
                    "root_cause": "groupby_aggregation",
                    "triage_verdict": "candidate_implementation_bug",
                    "suspicious_backends": ["buggy_join"],
                }
            )
        append_jsonl({"case_index": idx, "findings": findings}, path)
    dump_json({"elapsed_s": 2.0}, run_meta_path(path))


def test_analyze_seeded_sensitivity_counts_expected_root_separately(tmp_path, monkeypatch):
    reports_dir = tmp_path / "reports"
    monkeypatch.setattr(seeded_analysis, "REPORTS_DIR", reports_dir)
    runs_dir = tmp_path / "runs"
    baseline = runs_dir / "run-baseline.jsonl.gz"
    guided = runs_dir / "run-guided.jsonl.gz"
    _write_seeded_run(baseline, expected_indexes={2}, other_candidate_indexes={0, 1})
    _write_seeded_run(guided, expected_indexes={0, 1, 2}, other_candidate_indexes={3})
    manifest = runs_dir / "experiment-seeded.json"
    dump_json(
        {
            "runs": [
                {"target_suite": "seeded_join", "preset": "baseline", "seed": 1, "run_file": str(baseline)},
                {"target_suite": "seeded_join", "preset": "guided_join", "seed": 1, "run_file": str(guided)},
            ]
        },
        manifest,
    )

    md_path, csv_path = analyze_seeded_sensitivity(manifest)

    md = md_path.read_text(encoding="utf-8")
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    baseline_row = next(row for row in rows if row["row_type"] == "aggregate" and row["preset"] == "baseline")
    guided_row = next(row for row in rows if row["row_type"] == "aggregate" and row["preset"] == "guided_join")
    comparison = next(row for row in rows if row["row_type"] == "targeted_comparison")
    assert "Expected roots are counted separately" in md
    assert baseline_row["expected_fault_cases"] == "1"
    assert baseline_row["candidate_bug_cases"] == "3"
    assert guided_row["expected_fault_cases"] == "3"
    assert comparison["expected_fault_case_rate_ratio"] == "3.0"
