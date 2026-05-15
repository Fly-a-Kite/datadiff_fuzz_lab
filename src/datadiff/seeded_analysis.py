from __future__ import annotations

import csv
from pathlib import Path
from statistics import median
from typing import Any

from datadiff.experiment_analysis import TARGETED_PRESET_BY_SUITE
from datadiff.reporter import latest_experiment_manifest
from datadiff.util import REPORTS_DIR, ensure_dirs, load_json, read_jsonl, run_meta_path


EXPECTED_ROOTS_BY_SUITE: dict[str, set[str]] = {
    "seeded_filter": {"filter_predicate"},
    "seeded_groupby": {"groupby_aggregation"},
    "seeded_join": {"join_semantics"},
    "seeded_mutate": {"arithmetic_expression", "string_expression", "type_cast"},
}

EXPECTED_BACKEND_BY_SUITE: dict[str, str] = {
    "seeded_filter": "buggy_filter",
    "seeded_groupby": "buggy_groupby",
    "seeded_join": "buggy_join",
    "seeded_mutate": "buggy_mutate",
}


def analyze_seeded_sensitivity(manifest_file: Path | None = None) -> tuple[Path, Path]:
    ensure_dirs()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    manifest_file = manifest_file or latest_experiment_manifest()
    manifest = load_json(manifest_file)
    run_rows = [_summarize_run(run) for run in manifest.get("runs", [])]
    aggregate_rows = _aggregate(run_rows)
    comparisons = _targeted_comparisons(aggregate_rows)

    md_path = REPORTS_DIR / f"seeded-sensitivity-{manifest_file.stem}.md"
    csv_path = REPORTS_DIR / f"seeded-sensitivity-{manifest_file.stem}.csv"
    _write_markdown(md_path, manifest_file, aggregate_rows, comparisons)
    _write_csv(csv_path, aggregate_rows, comparisons)
    return md_path, csv_path


def _summarize_run(run: dict[str, Any]) -> dict[str, Any]:
    suite = str(run["target_suite"])
    preset = str(run["preset"])
    run_file = Path(run["run_file"])
    expected_roots = EXPECTED_ROOTS_BY_SUITE.get(suite, set())
    expected_backend = EXPECTED_BACKEND_BY_SUITE.get(suite, "")
    rows = read_jsonl(run_file)
    expected_indexes = []
    candidate_indexes = []
    for idx, row in enumerate(rows):
        findings = row.get("findings") or []
        if any(_is_candidate_finding(finding) for finding in findings):
            candidate_indexes.append(idx)
        if any(_is_expected_seeded_finding(finding, expected_roots, expected_backend) for finding in findings):
            expected_indexes.append(idx)
    elapsed_s = _elapsed_seconds(run_file)
    return {
        "target_suite": suite,
        "preset": preset,
        "seed": int(run["seed"]),
        "cases": len(rows),
        "expected_fault_cases": len(set(expected_indexes)),
        "candidate_bug_cases": len(set(candidate_indexes)),
        "first_expected_fault_case_index": min(expected_indexes) if expected_indexes else None,
        "elapsed_s": elapsed_s,
    }


def _is_candidate_finding(finding: dict[str, Any]) -> bool:
    return finding.get("triage_verdict") == "candidate_implementation_bug"


def _is_expected_seeded_finding(finding: dict[str, Any], expected_roots: set[str], expected_backend: str) -> bool:
    suspicious = set(finding.get("suspicious_backends") or [])
    return (
        _is_candidate_finding(finding)
        and finding.get("root_cause") in expected_roots
        and expected_backend in suspicious
    )


def _elapsed_seconds(run_file: Path) -> float:
    meta_path = run_meta_path(run_file)
    if not meta_path.exists():
        return 0.0
    return float(load_json(meta_path).get("elapsed_s", 0.0) or 0.0)


def _aggregate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault((row["target_suite"], row["preset"]), []).append(row)
    out = []
    for (suite, preset), items in sorted(grouped.items()):
        cases = sum(int(item["cases"]) for item in items)
        expected = sum(int(item["expected_fault_cases"]) for item in items)
        candidates = sum(int(item["candidate_bug_cases"]) for item in items)
        elapsed_s = sum(float(item["elapsed_s"]) for item in items)
        firsts = [
            int(item["first_expected_fault_case_index"])
            for item in items
            if item["first_expected_fault_case_index"] is not None
        ]
        out.append(
            {
                "target_suite": suite,
                "preset": preset,
                "runs": len(items),
                "cases": cases,
                "expected_fault_cases": expected,
                "expected_fault_case_rate": expected / cases if cases else 0.0,
                "expected_fault_cases_per_s": expected / elapsed_s if elapsed_s > 0 else 0.0,
                "median_first_expected_fault_case_index": median(firsts) if firsts else None,
                "candidate_bug_cases": candidates,
                "candidate_bug_case_rate": candidates / cases if cases else 0.0,
            }
        )
    return out


def _targeted_comparisons(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key = {(row["target_suite"], row["preset"]): row for row in rows}
    comparisons = []
    for suite, targeted_preset in TARGETED_PRESET_BY_SUITE.items():
        baseline = by_key.get((suite, "baseline"))
        targeted = by_key.get((suite, targeted_preset))
        if baseline is None or targeted is None:
            continue
        comparisons.append(
            {
                "target_suite": suite,
                "targeted_preset": targeted_preset,
                "baseline_expected_fault_case_rate": baseline["expected_fault_case_rate"],
                "targeted_expected_fault_case_rate": targeted["expected_fault_case_rate"],
                "expected_fault_case_rate_delta": targeted["expected_fault_case_rate"] - baseline["expected_fault_case_rate"],
                "expected_fault_case_rate_ratio": _ratio(
                    targeted["expected_fault_case_rate"],
                    baseline["expected_fault_case_rate"],
                ),
                "baseline_median_first_expected": baseline["median_first_expected_fault_case_index"],
                "targeted_median_first_expected": targeted["median_first_expected_fault_case_index"],
                "first_expected_delta": _optional_delta(
                    targeted["median_first_expected_fault_case_index"],
                    baseline["median_first_expected_fault_case_index"],
                ),
            }
        )
    return comparisons


def _write_markdown(
    path: Path,
    manifest_file: Path,
    aggregate_rows: list[dict[str, Any]],
    comparisons: list[dict[str, Any]],
) -> None:
    lines = [
        "# Seeded Fault Sensitivity Analysis",
        "",
        f"- Manifest: `{manifest_file}`",
        "- Expected roots are counted separately from all candidate findings.",
        "",
        "## Targeted Preset Contrasts",
        "",
        "| target suite | targeted preset | expected fault case % | delta | ratio | median first expected | first delta |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in comparisons:
        lines.append(
            "| {suite} | {preset} | {rate} | {delta} | {ratio} | {first} | {first_delta} |".format(
                suite=row["target_suite"],
                preset=row["targeted_preset"],
                rate=_fmt_percent(row["targeted_expected_fault_case_rate"]),
                delta=_fmt_signed_percent(row["expected_fault_case_rate_delta"]),
                ratio=_fmt_ratio(row["expected_fault_case_rate_ratio"]),
                first=_fmt_optional(row["targeted_median_first_expected"]),
                first_delta=_fmt_optional_signed(row["first_expected_delta"]),
            )
        )
    lines.extend(
        [
            "",
            "## Aggregate Rows",
            "",
            "| target suite | preset | cases | expected fault cases | expected fault case % | expected cases/s | median first expected | all candidate case % |",
            "|---|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in aggregate_rows:
        lines.append(
            "| {suite} | {preset} | {cases} | {expected} | {rate} | {per_s} | {first} | {candidate_rate} |".format(
                suite=row["target_suite"],
                preset=row["preset"],
                cases=row["cases"],
                expected=row["expected_fault_cases"],
                rate=_fmt_percent(row["expected_fault_case_rate"]),
                per_s=_fmt_float(row["expected_fault_cases_per_s"]),
                first=_fmt_optional(row["median_first_expected_fault_case_index"]),
                candidate_rate=_fmt_percent(row["candidate_bug_case_rate"]),
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_csv(path: Path, aggregate_rows: list[dict[str, Any]], comparisons: list[dict[str, Any]]) -> None:
    rows = [{**row, "row_type": "aggregate"} for row in aggregate_rows]
    rows.extend({**row, "row_type": "targeted_comparison"} for row in comparisons)
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _ratio(numerator: float, denominator: float) -> float | None:
    return None if denominator == 0 else numerator / denominator


def _optional_delta(left: float | int | None, right: float | int | None) -> float | None:
    if left is None or right is None:
        return None
    return float(left) - float(right)


def _fmt_percent(value: float) -> str:
    return f"{value:.1%}"


def _fmt_signed_percent(value: float) -> str:
    return f"{value:+.1%}"


def _fmt_float(value: float) -> str:
    return f"{value:.2f}"


def _fmt_ratio(value: float | None) -> str:
    return "" if value is None else f"{value:.2f}x"


def _fmt_optional(value: float | int | None) -> str:
    return "" if value is None else f"{value:g}"


def _fmt_optional_signed(value: float | int | None) -> str:
    return "" if value is None else f"{value:+g}"
