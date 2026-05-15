import csv

from datadiff import pattern_analysis
from datadiff.pattern_analysis import analyze_pattern_variants
from datadiff.util import append_jsonl, dump_json


def _append_case(path, *, agg_func, ascending, candidate):
    alias = f"{agg_func}_x"
    findings = []
    if candidate:
        findings.append(
            {
                "root_cause": "grouped_topk_null_sort_key",
                "triage_verdict": "candidate_implementation_bug",
                "suspicious_backends": ["datafusion"],
            }
        )
    append_jsonl(
        {
            "case": {
                "program": {
                    "operations": [
                        {
                            "op": "groupby",
                            "keys": ["g"],
                            "aggs": [{"column": "x", "func": agg_func, "as": alias}],
                        },
                        {"op": "select", "columns": [alias]},
                        {"op": "sort", "columns": [alias], "ascending": ascending},
                        {"op": "limit", "n": 20},
                    ]
                }
            },
            "findings": findings,
        },
        path,
    )


def test_analyze_pattern_variants_counts_null_agg_topk_variants(tmp_path, monkeypatch):
    reports_dir = tmp_path / "reports"
    monkeypatch.setattr(pattern_analysis, "REPORTS_DIR", reports_dir)
    runs_dir = tmp_path / "runs"
    run_file = runs_dir / "run.jsonl.gz"
    _append_case(run_file, agg_func="min", ascending=True, candidate=True)
    _append_case(run_file, agg_func="max", ascending=False, candidate=True)
    _append_case(run_file, agg_func="sum", ascending=True, candidate=False)
    manifest = runs_dir / "experiment-pattern.json"
    dump_json(
        {
            "runs": [
                {
                    "target_suite": "core_datafusion",
                    "preset": "null_agg_topk",
                    "run_file": str(run_file),
                }
            ]
        },
        manifest,
    )

    md_path, csv_path = analyze_pattern_variants(manifest)

    md = md_path.read_text(encoding="utf-8")
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    min_row = next(row for row in rows if row["agg_func"] == "min")
    max_row = next(row for row in rows if row["agg_func"] == "max")
    sum_row = next(row for row in rows if row["agg_func"] == "sum")
    assert "Candidate cases: 2" in md
    assert min_row["sort_direction"] == "asc"
    assert min_row["candidate_cases"] == "1"
    assert max_row["sort_direction"] == "desc"
    assert max_row["top_candidate_bug_families"] == "grouped_topk_null_sort_key@datafusion:1"
    assert sum_row["candidate_cases"] == "0"
