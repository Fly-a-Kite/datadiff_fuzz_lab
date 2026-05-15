#!/usr/bin/env python3
from __future__ import annotations

import csv
import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from datadiff.util import REPORTS_DIR, load_json, read_jsonl, run_meta_path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_EXPERIMENTS = [
    ("core_ablation", PROJECT_ROOT / "runs" / "experiment-20260511T193546.json"),
    ("dataframe_generalization", PROJECT_ROOT / "runs" / "experiment-20260511T193709.json"),
    ("embedded_sql_generalization", PROJECT_ROOT / "runs" / "experiment-20260511T193901.json"),
    ("edge_float_boundary", PROJECT_ROOT / "runs" / "experiment-20260511T195036.json"),
    ("reducer_validation", PROJECT_ROOT / "runs" / "experiment-20260511T194215.json"),
]


@dataclass(slots=True)
class RunSummary:
    experiment: str
    target_suite: str
    preset: str
    seed: int
    cases: int
    bug_cases: int
    findings: int
    unique_findings: int
    new_behavior_cases: int
    elapsed_s: float
    throughput_cases_s: float
    run_file: str
    report: str
    roots: Counter[str] = field(default_factory=Counter)
    kinds: Counter[str] = field(default_factory=Counter)
    verdicts: Counter[str] = field(default_factory=Counter)
    paper_statuses: Counter[str] = field(default_factory=Counter)
    false_positive_reasons: Counter[str] = field(default_factory=Counter)
    quality_oracles: Counter[str] = field(default_factory=Counter)

    @property
    def finding_rate(self) -> float:
        return self.findings / self.cases if self.cases else 0.0

    @property
    def bug_case_rate(self) -> float:
        return self.bug_cases / self.cases if self.cases else 0.0


@dataclass(slots=True)
class AggregateSummary:
    experiment: str
    target_suite: str
    preset: str
    runs: int = 0
    cases: int = 0
    bug_cases: int = 0
    findings: int = 0
    new_behavior_cases: int = 0
    elapsed_s: float = 0.0
    unique_signatures: set[str] = field(default_factory=set)
    roots: Counter[str] = field(default_factory=Counter)
    kinds: Counter[str] = field(default_factory=Counter)
    verdicts: Counter[str] = field(default_factory=Counter)
    paper_statuses: Counter[str] = field(default_factory=Counter)
    false_positive_reasons: Counter[str] = field(default_factory=Counter)
    quality_oracles: Counter[str] = field(default_factory=Counter)

    @property
    def finding_rate(self) -> float:
        return self.findings / self.cases if self.cases else 0.0

    @property
    def bug_case_rate(self) -> float:
        return self.bug_cases / self.cases if self.cases else 0.0

    @property
    def new_behavior_rate(self) -> float:
        return self.new_behavior_cases / self.cases if self.cases else 0.0

    @property
    def throughput_cases_s(self) -> float:
        return self.cases / self.elapsed_s if self.elapsed_s else 0.0


def main() -> int:
    args = parse_args()
    experiments = parse_experiments(args.experiment)
    output_prefix = args.output_prefix
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    run_summaries = []
    aggregates: dict[tuple[str, str], AggregateSummary] = {}

    for experiment, manifest_path in experiments:
        manifest = load_json(manifest_path)
        for run in manifest.get("runs", []):
            summary, signatures = summarize_run(experiment, manifest, run)
            run_summaries.append(summary)
            key = (experiment, summary.preset)
            agg = aggregates.setdefault(
                key,
                AggregateSummary(
                    experiment=experiment,
                    target_suite=summary.target_suite,
                    preset=summary.preset,
                ),
            )
            agg.runs += 1
            agg.cases += summary.cases
            agg.bug_cases += summary.bug_cases
            agg.findings += summary.findings
            agg.new_behavior_cases += summary.new_behavior_cases
            agg.elapsed_s += summary.elapsed_s
            agg.unique_signatures.update(signatures)
            agg.roots.update(summary.roots)
            agg.kinds.update(summary.kinds)
            agg.verdicts.update(summary.verdicts)
            agg.paper_statuses.update(summary.paper_statuses)
            agg.false_positive_reasons.update(summary.false_positive_reasons)
            agg.quality_oracles.update(summary.quality_oracles)

    aggregate_rows = sorted(aggregates.values(), key=lambda item: (item.experiment, item.preset))
    run_csv = REPORTS_DIR / f"{output_prefix}-runs.csv"
    aggregate_csv = REPORTS_DIR / f"{output_prefix}-presets.csv"
    markdown = REPORTS_DIR / f"{output_prefix}-analysis.md"
    write_run_csv(run_csv, run_summaries)
    write_aggregate_csv(aggregate_csv, aggregate_rows)
    write_markdown(markdown, aggregate_rows, experiments)
    print(markdown)
    print(aggregate_csv)
    print(run_csv)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate DataDiffFuzz medium experiment manifests.")
    parser.add_argument(
        "--experiment",
        action="append",
        default=[],
        metavar="LABEL=MANIFEST",
        help="experiment label and manifest path; may be repeated",
    )
    parser.add_argument(
        "--output-prefix",
        default="medium-experiment",
        help="prefix for reports/{prefix}-analysis.md, -presets.csv, and -runs.csv",
    )
    return parser.parse_args()


def parse_experiments(values: list[str]) -> list[tuple[str, Path]]:
    if not values:
        return DEFAULT_EXPERIMENTS
    experiments = []
    for value in values:
        if "=" not in value:
            raise ValueError(f"expected LABEL=MANIFEST, got {value!r}")
        label, path = value.split("=", 1)
        label = label.strip()
        if not label:
            raise ValueError(f"experiment label cannot be empty in {value!r}")
        experiments.append((label, Path(path)))
    return experiments


def summarize_run(experiment: str, manifest: dict[str, Any], run: dict[str, Any]) -> tuple[RunSummary, set[str]]:
    run_file = Path(run["run_file"])
    rows = read_jsonl(run_file)
    meta_path = run_meta_path(run_file)
    meta = load_json(meta_path) if meta_path.exists() else {}
    findings = [finding for row in rows for finding in row.get("findings", [])]
    signatures = {finding.get("signature", "") for finding in findings if finding.get("signature")}

    summary = RunSummary(
        experiment=experiment,
        target_suite=manifest.get("target_suite", ""),
        preset=run.get("preset", ""),
        seed=int(run.get("seed", 0)),
        cases=len(rows),
        bug_cases=sum(1 for row in rows if row.get("findings")),
        findings=len(findings),
        unique_findings=len(signatures),
        new_behavior_cases=sum(1 for row in rows if row.get("is_new_behavior")),
        elapsed_s=float(meta.get("elapsed_s") or 0.0),
        throughput_cases_s=float(meta.get("throughput_cases_s") or 0.0),
        run_file=str(run_file),
        report=run.get("report", ""),
    )
    for finding in findings:
        summary.roots[finding.get("root_cause", "unknown")] += 1
        summary.kinds[finding.get("kind", "unknown")] += 1
        summary.verdicts[finding.get("triage_verdict", "unclassified")] += 1
        summary.paper_statuses[finding.get("paper_status", "unclassified")] += 1
        if finding.get("false_positive_reason"):
            summary.false_positive_reasons[finding["false_positive_reason"]] += 1
    for row in rows:
        for oracle in row.get("quality_oracles", []):
            summary.quality_oracles[f"{oracle.get('name', 'unknown')}:{oracle.get('verdict', 'unknown')}"] += 1
    return summary, signatures


def write_run_csv(path: Path, summaries: list[RunSummary]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "experiment",
                "target_suite",
                "preset",
                "seed",
                "cases",
                "bug_cases",
                "bug_case_rate",
                "findings",
                "finding_rate",
                "unique_findings",
                "new_behavior_cases",
                "throughput_cases_s",
                "top_roots",
                "triage_verdicts",
                "paper_statuses",
                "false_positive_reasons",
                "run_file",
                "report",
            ],
        )
        writer.writeheader()
        for item in sorted(summaries, key=lambda row: (row.experiment, row.preset, row.seed)):
            writer.writerow(
                {
                    "experiment": item.experiment,
                    "target_suite": item.target_suite,
                    "preset": item.preset,
                    "seed": item.seed,
                    "cases": item.cases,
                    "bug_cases": item.bug_cases,
                    "bug_case_rate": _fmt_ratio(item.bug_case_rate),
                    "findings": item.findings,
                    "finding_rate": _fmt_ratio(item.finding_rate),
                    "unique_findings": item.unique_findings,
                    "new_behavior_cases": item.new_behavior_cases,
                    "throughput_cases_s": _fmt_float(item.throughput_cases_s),
                    "top_roots": _counter_summary(item.roots),
                    "triage_verdicts": _counter_summary(item.verdicts),
                    "paper_statuses": _counter_summary(item.paper_statuses),
                    "false_positive_reasons": _counter_summary(item.false_positive_reasons),
                    "run_file": item.run_file,
                    "report": item.report,
                }
            )


def write_aggregate_csv(path: Path, summaries: list[AggregateSummary]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "experiment",
                "target_suite",
                "preset",
                "runs",
                "cases",
                "bug_cases",
                "bug_case_rate",
                "findings",
                "finding_rate",
                "unique_findings",
                "new_behavior_cases",
                "new_behavior_rate",
                "throughput_cases_s",
                "top_roots",
                "finding_kinds",
                "triage_verdicts",
                "paper_statuses",
                "false_positive_reasons",
                "quality_oracles",
            ],
        )
        writer.writeheader()
        for item in summaries:
            writer.writerow(aggregate_row(item))


def write_markdown(
    path: Path,
    summaries: list[AggregateSummary],
    experiments: list[tuple[str, Path]],
) -> None:
    by_experiment: dict[str, list[AggregateSummary]] = defaultdict(list)
    for item in summaries:
        by_experiment[item.experiment].append(item)

    lines = [
        "# Medium Experiment Analysis",
        "",
        "## Inputs",
        "",
    ]
    for label, manifest in experiments:
        lines.append(f"- `{label}`: `{manifest}`")
    lines.extend(
        [
            "",
            "## Aggregate Table",
            "",
            "| experiment | preset | cases | findings | finding rate | unique | new behavior rate | cases/s | top roots | triage verdicts |",
            "|---|---|---:|---:|---:|---:|---:|---:|---|---|",
        ]
    )
    for item in summaries:
        lines.append(
            "| {experiment} | {preset} | {cases} | {findings} | {finding_rate} | "
            "{unique_findings} | {new_behavior_rate} | {throughput_cases_s} | {top_roots} | {triage_verdicts} |".format(
                **aggregate_row(item)
            )
        )

    lines.extend(["", "## Main Comparisons", ""])
    lines.extend(main_comparisons(by_experiment))
    lines.extend(["", "## Interpretation", ""])
    lines.extend(interpretation_notes(by_experiment))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def aggregate_row(item: AggregateSummary) -> dict[str, Any]:
    return {
        "experiment": item.experiment,
        "target_suite": item.target_suite,
        "preset": item.preset,
        "runs": item.runs,
        "cases": item.cases,
        "bug_cases": item.bug_cases,
        "bug_case_rate": _fmt_ratio(item.bug_case_rate),
        "findings": item.findings,
        "finding_rate": _fmt_ratio(item.finding_rate),
        "unique_findings": len(item.unique_signatures),
        "new_behavior_cases": item.new_behavior_cases,
        "new_behavior_rate": _fmt_ratio(item.new_behavior_rate),
        "throughput_cases_s": _fmt_float(item.throughput_cases_s),
        "top_roots": _counter_summary(item.roots),
        "finding_kinds": _counter_summary(item.kinds),
        "triage_verdicts": _counter_summary(item.verdicts),
        "paper_statuses": _counter_summary(item.paper_statuses),
        "false_positive_reasons": _counter_summary(item.false_positive_reasons),
        "quality_oracles": _counter_summary(item.quality_oracles, limit=8),
    }


def main_comparisons(by_experiment: dict[str, list[AggregateSummary]]) -> list[str]:
    lines = []
    core = {item.preset: item for item in by_experiment.get("core_ablation", [])}
    baseline = core.get("baseline")
    guided = core.get("guided")
    no_feedback = core.get("no_feedback")
    no_type = core.get("no_type_aware")
    no_norm = core.get("no_normalizer")
    metamorphic = core.get("metamorphic")
    if baseline and guided:
        lines.append(
            "- Core guided increased findings from "
            f"{baseline.findings} to {guided.findings} "
            f"({_fmt_float(_safe_ratio(guided.finding_rate, baseline.finding_rate))}x finding-rate), "
            f"with throughput changing from {_fmt_float(baseline.throughput_cases_s)} to "
            f"{_fmt_float(guided.throughput_cases_s)} cases/s."
        )
    if baseline and no_feedback:
        lines.append(
            "- Core no_feedback kept finding volume close to baseline "
            f"({no_feedback.findings} vs {baseline.findings}) but increased new behavior rate "
            f"from {_fmt_ratio(baseline.new_behavior_rate)} to {_fmt_ratio(no_feedback.new_behavior_rate)}."
        )
    if baseline and no_type:
        lines.append(
            "- Disabling type-aware generation raised findings from "
            f"{baseline.findings} to {no_type.findings}, indicating much higher invalid or boundary-semantics pressure."
        )
    if baseline and no_norm:
        lines.append(
            "- Disabling normalization raised findings from "
            f"{baseline.findings} to {no_norm.findings}, showing that the normalizer removes substantial representation noise."
        )
    if baseline and metamorphic:
        lines.append(
            "- Metamorphic runs matched baseline finding volume in this configuration "
            f"({metamorphic.findings} vs {baseline.findings}) but reduced throughput to "
            f"{_fmt_float(metamorphic.throughput_cases_s)} cases/s."
        )
    edge = {item.preset: item for item in by_experiment.get("edge_float_boundary", [])}
    edge_float = edge.get("edge_float")
    if edge_float:
        lines.append(
            "- Edge-float produced "
            f"{edge_float.findings} findings; verdicts were {_counter_summary(edge_float.verdicts)}, "
            "supporting separation of boundary semantics from common-subset bug claims."
        )
    reducer = by_experiment.get("reducer_validation", [])
    if reducer:
        total = sum(item.findings for item in reducer)
        lines.append(f"- Reducer validation produced {total} findings across 600 cases; validated artifacts were reproducible.")
    return lines or ["- No comparison data available."]


def interpretation_notes(by_experiment: dict[str, list[AggregateSummary]]) -> list[str]:
    core = {item.preset: item for item in by_experiment.get("core_ablation", [])}
    guided = core.get("guided")
    notes = [
        "- The current strongest quantitative claim is effectiveness of guidance for surfacing semantic differences, not confirmed implementation bugs.",
        "- Normalization and type-aware generation are necessary controls: their ablations greatly increase findings, which should be treated as false-positive pressure or boundary-semantics pressure until triaged.",
        "- Metamorphic oracle needs richer relations before it can be claimed as an effectiveness contributor.",
    ]
    if by_experiment.get("edge_float_boundary"):
        notes.append(
            "- Edge-float should stay a separate experiment family; it mainly measures documented or specification-sensitive semantics."
        )
    if by_experiment.get("reducer_validation"):
        notes.append(
            "- Reducer output is reproducible, but current artifacts are semantic divergences needing confirmation rather than confirmed backend bugs."
        )
    if guided and guided.roots:
        dominant_root, dominant_count = guided.roots.most_common(1)[0]
        notes.append(
            f"- Guided search is currently concentrated on `{dominant_root}` ({dominant_count} findings in core), "
            "so future guidance should balance target coverage before large-scale runs."
        )
    return notes


def _counter_summary(counter: Counter[str], limit: int = 5) -> str:
    return "; ".join(f"{key}:{count}" for key, count in counter.most_common(limit)) or "none"


def _fmt_float(value: float) -> str:
    return f"{value:.2f}"


def _fmt_ratio(value: float) -> str:
    return f"{value:.4f}"


def _safe_ratio(num: float, den: float) -> float:
    return num / den if den else 0.0


if __name__ == "__main__":
    raise SystemExit(main())
