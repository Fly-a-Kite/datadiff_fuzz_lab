from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path

from datadiff.util import REPORTS_DIR, RUNS_DIR, ensure_dirs, load_json, read_jsonl, utc_now


def latest_run_file() -> Path:
    files = sorted(RUNS_DIR.glob("run-*.jsonl"))
    if not files:
        raise FileNotFoundError(f"no run logs found in {RUNS_DIR}")
    return files[-1]


def write_report(run_file: Path | None = None) -> tuple[Path, Path]:
    ensure_dirs()
    run_file = run_file or latest_run_file()
    rows = read_jsonl(run_file)
    ts = utc_now().replace(":", "").replace("-", "").replace("Z", "")
    md_path = REPORTS_DIR / f"report-{ts}.md"
    csv_path = REPORTS_DIR / f"findings-{ts}.csv"

    status_counts = Counter(r.get("status", "unknown") for r in rows)
    finding_kinds = Counter()
    root_causes = Counter()
    oracle_counts = Counter()
    confidence_counts = Counter()
    backend_status = Counter()
    signatures = Counter(r.get("behavior_signature", "") for r in rows)
    examples: dict[str, list[dict]] = defaultdict(list)
    meta_path = RUNS_DIR / f"{run_file.stem}.meta.json"
    meta = load_json(meta_path) if meta_path.exists() else {}

    for row in rows:
        for backend, norm in row.get("normalized", {}).items():
            backend_status[f"{backend}:{norm.get('status')}"] += 1
        for finding in row.get("findings", []):
            finding_kinds[finding["kind"]] += 1
            root_causes[finding.get("root_cause", "unknown")] += 1
            oracle_counts[finding.get("oracle", "unknown")] += 1
            confidence_counts[finding.get("confidence", "unknown")] += 1
            if len(examples[finding["kind"]]) < 3:
                examples[finding["kind"]].append(
                    {
                        "case_id": row["case"]["case_id"],
                        "seed": row["case"]["seed"],
                        "evidence": finding["evidence"],
                        "root_cause": finding.get("root_cause", "unknown"),
                        "oracle": finding.get("oracle", "unknown"),
                        "confidence": finding.get("confidence", "unknown"),
                        "bug_dir": row.get("bug_dir", ""),
                    }
                )

    total = len(rows)
    bug_rows = [r for r in rows if r.get("findings")]
    lines = [
        "# DataDiffFuzz Report",
        "",
        f"- Run log: `{run_file}`",
        f"- Cases: {total}",
        f"- Bug-triggering cases: {len(bug_rows)}",
        f"- Bug rate: {len(bug_rows) / total:.1%}" if total else "- Bug rate: n/a",
        f"- Unique behavior signatures: {len(signatures)}",
        f"- New behavior cases: {sum(1 for r in rows if r.get('is_new_behavior'))}",
        f"- Elapsed seconds: {meta.get('elapsed_s', 'n/a')}",
        f"- Throughput cases/s: {meta.get('throughput_cases_s', 'n/a')}",
        f"- Backends: {', '.join(meta.get('backends', [])) if meta.get('backends') else 'n/a'}",
        "",
        "## Status",
    ]
    for key, count in status_counts.most_common():
        lines.append(f"- {key}: {count}")
    lines.append("")
    lines.append("## Backend Status")
    for key, count in backend_status.most_common():
        lines.append(f"- {key}: {count}")
    lines.append("")
    lines.append("## Finding Kinds")
    if finding_kinds:
        for key, count in finding_kinds.most_common():
            lines.append(f"- {key}: {count}")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Root Causes")
    if root_causes:
        for key, count in root_causes.most_common():
            lines.append(f"- {key}: {count}")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Oracle Sources")
    if oracle_counts:
        for key, count in oracle_counts.most_common():
            lines.append(f"- {key}: {count}")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Confidence")
    if confidence_counts:
        for key, count in confidence_counts.most_common():
            lines.append(f"- {key}: {count}")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Representative Evidence")
    if not examples:
        lines.append("- No findings.")
    for kind, items in examples.items():
        lines.append(f"### {kind}")
        for item in items:
            lines.append(
                f"- `{item['case_id']}` seed={item['seed']} "
                f"root={item['root_cause']} oracle={item['oracle']} confidence={item['confidence']}: "
                f"{item['evidence']} "
                f"artifact=`{item['bug_dir']}`"
            )
        lines.append("")
    lines.append("## Ablation-Oriented Interpretation")
    lines.append("")
    lines.append(
        "Each row records the active modules in `config`: type-aware generation, "
        "semantic normalization, differential oracle, feedback, reducer, and artifact generation. "
        "Run the same seed range with modules disabled to quantify their contribution."
    )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "case_id",
                "seed",
                "kind",
                "severity",
                "root_cause",
                "oracle",
                "confidence",
                "suspicious_backends",
                "signature",
                "evidence",
                "bug_dir",
            ],
        )
        writer.writeheader()
        for row in rows:
            for finding in row.get("findings", []):
                writer.writerow(
                    {
                        "case_id": row["case"]["case_id"],
                        "seed": row["case"]["seed"],
                        "kind": finding["kind"],
                        "severity": finding["severity"],
                        "root_cause": finding.get("root_cause", "unknown"),
                        "oracle": finding.get("oracle", "unknown"),
                        "confidence": finding.get("confidence", "unknown"),
                        "suspicious_backends": ",".join(finding.get("suspicious_backends", [])),
                        "signature": finding["signature"],
                        "evidence": finding["evidence"],
                        "bug_dir": row.get("bug_dir", ""),
                    }
                )
    return md_path, csv_path


def latest_experiment_manifest() -> Path:
    files = sorted(RUNS_DIR.glob("experiment-*.json"))
    if not files:
        raise FileNotFoundError(f"no experiment manifests found in {RUNS_DIR}")
    return files[-1]


def write_experiment_summary(manifest_file: Path | None = None) -> tuple[Path, Path]:
    ensure_dirs()
    manifest_file = manifest_file or latest_experiment_manifest()
    manifest = load_json(manifest_file)
    ts = utc_now().replace(":", "").replace("-", "").replace("Z", "")
    md_path = REPORTS_DIR / f"experiment-summary-{ts}.md"
    csv_path = REPORTS_DIR / f"experiment-summary-{ts}.csv"

    rows = []
    for run in manifest.get("runs", []):
        run_file = Path(run["run_file"])
        run_rows = read_jsonl(run_file)
        meta_path = RUNS_DIR / f"{run_file.stem}.meta.json"
        meta = load_json(meta_path) if meta_path.exists() else {}
        findings = [finding for row in run_rows for finding in row.get("findings", [])]
        unique_finding_signatures = {f.get("signature", "") for f in findings}
        root_causes = Counter(f.get("root_cause", "unknown") for f in findings)
        finding_kinds = Counter(f.get("kind", "unknown") for f in findings)
        total = len(run_rows)
        bug_cases = sum(1 for row in run_rows if row.get("findings"))
        rows.append(
            {
                "preset": run.get("preset", ""),
                "seed": run.get("seed", ""),
                "cases": total,
                "bug_cases": bug_cases,
                "bug_rate": bug_cases / total if total else 0.0,
                "findings": len(findings),
                "unique_findings": len(unique_finding_signatures),
                "new_behavior_cases": sum(1 for row in run_rows if row.get("is_new_behavior")),
                "elapsed_s": meta.get("elapsed_s", ""),
                "throughput_cases_s": meta.get("throughput_cases_s", ""),
                "top_root_causes": _counter_summary(root_causes),
                "top_finding_kinds": _counter_summary(finding_kinds),
                "run_file": str(run_file),
                "report": run.get("report", ""),
            }
        )

    lines = [
        "# DataDiffFuzz Experiment Summary",
        "",
        f"- Manifest: `{manifest_file}`",
        f"- Runs: {len(rows)}",
        f"- Presets: {', '.join(manifest.get('presets', []))}",
        f"- Seeds: {', '.join(str(s) for s in manifest.get('seeds', []))}",
        f"- Backends: {', '.join(manifest.get('backends', []))}",
        "",
        "## Runs",
        "",
        "| preset | seed | cases | bug cases | findings | unique findings | new behaviors | cases/s | roots |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            "| {preset} | {seed} | {cases} | {bug_cases} | {findings} | "
            "{unique_findings} | {new_behavior_cases} | {throughput_cases_s} | {top_root_causes} |".format(
                **{
                    **row,
                    "throughput_cases_s": _fmt_float(row["throughput_cases_s"]),
                }
            )
        )
    lines.extend(
        [
            "",
            "## Interpretation Notes",
            "",
            "- Compare `baseline` with `no_type_aware` to measure generator validity and useful behavior discovery.",
            "- Compare `baseline` with `no_normalizer` to estimate false-positive pressure from representation differences.",
            "- Compare `baseline` with `no_feedback` to measure whether corpus feedback improves new behavior discovery.",
            "- Compare `baseline` with `metamorphic` to separate cross-engine differential bugs from single-engine relation violations.",
            "- Use `edge_float` separately from `common`; it studies boundary semantics rather than the default common subset.",
        ]
    )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "preset",
                "seed",
                "cases",
                "bug_cases",
                "bug_rate",
                "findings",
                "unique_findings",
                "new_behavior_cases",
                "elapsed_s",
                "throughput_cases_s",
                "top_root_causes",
                "top_finding_kinds",
                "run_file",
                "report",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    return md_path, csv_path


def _counter_summary(counter: Counter) -> str:
    return "; ".join(f"{key}:{count}" for key, count in counter.most_common(5)) or "none"


def _fmt_float(value) -> str:
    if isinstance(value, (int, float)):
        return f"{value:.2f}"
    return str(value)
