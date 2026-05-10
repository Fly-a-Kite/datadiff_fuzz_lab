from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path

from datadiff.util import REPORTS_DIR, RUNS_DIR, ensure_dirs, read_jsonl, utc_now


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
    backend_status = Counter()
    signatures = Counter(r.get("behavior_signature", "") for r in rows)
    examples: dict[str, list[dict]] = defaultdict(list)

    for row in rows:
        for backend, norm in row.get("normalized", {}).items():
            backend_status[f"{backend}:{norm.get('status')}"] += 1
        for finding in row.get("findings", []):
            finding_kinds[finding["kind"]] += 1
            if len(examples[finding["kind"]]) < 3:
                examples[finding["kind"]].append(
                    {
                        "case_id": row["case"]["case_id"],
                        "seed": row["case"]["seed"],
                        "evidence": finding["evidence"],
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
    lines.append("## Representative Evidence")
    if not examples:
        lines.append("- No findings.")
    for kind, items in examples.items():
        lines.append(f"### {kind}")
        for item in items:
            lines.append(
                f"- `{item['case_id']}` seed={item['seed']}: {item['evidence']} "
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
                        "suspicious_backends": ",".join(finding.get("suspicious_backends", [])),
                        "signature": finding["signature"],
                        "evidence": finding["evidence"],
                        "bug_dir": row.get("bug_dir", ""),
                    }
                )
    return md_path, csv_path
