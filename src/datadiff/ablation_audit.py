from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from datadiff.reporter import latest_experiment_manifest, write_experiment_summary
from datadiff.util import REPORTS_DIR, ensure_dirs


DEFAULT_TRUSTED_PRESETS = ("baseline", "guided", "no_feedback", "metamorphic")
DEFAULT_ABLATION_PRESETS = ("no_type_aware", "no_normalizer")


def analyze_ablation_audit(
    manifest_file: Path | None = None,
    *,
    trusted_presets: list[str] | None = None,
    ablation_presets: list[str] | None = None,
    refresh: bool = False,
) -> tuple[Path, Path]:
    ensure_dirs()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    manifest_file = manifest_file or latest_experiment_manifest()
    summary_md, _ = write_experiment_summary(manifest_file, refresh=refresh)
    aggregate_csv = summary_md.with_name(f"{summary_md.stem}-aggregates.csv")
    rows = _read_csv(aggregate_csv)

    trusted = tuple(trusted_presets or DEFAULT_TRUSTED_PRESETS)
    ablations = tuple(ablation_presets or DEFAULT_ABLATION_PRESETS)
    audit = _build_audit(rows, trusted, ablations)

    md_path = REPORTS_DIR / f"ablation-audit-{manifest_file.stem}.md"
    csv_path = REPORTS_DIR / f"ablation-audit-{manifest_file.stem}.csv"
    _write_markdown(md_path, manifest_file, aggregate_csv, trusted, ablations, audit)
    _write_csv(csv_path, audit["family_rows"])
    return md_path, csv_path


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _build_audit(rows: list[dict[str, str]], trusted: tuple[str, ...], ablations: tuple[str, ...]) -> dict[str, Any]:
    preset_totals: dict[str, Counter[str]] = defaultdict(Counter)
    family_by_preset: dict[str, Counter[str]] = defaultdict(Counter)
    family_suites: dict[str, set[str]] = defaultdict(set)
    family_presets: dict[str, set[str]] = defaultdict(set)

    for row in rows:
        preset = row.get("preset", "")
        totals = preset_totals[preset]
        for key in ("cases", "findings", "candidate_bug_cases", "semantic_divergence_count", "false_positive_count"):
            totals[key] += _int(row.get(key, "0"))
        for family, count in _parse_family_counts(row.get("top_candidate_bug_families", "")):
            family_by_preset[preset][family] += count
            family_suites[family].add(row.get("target_suite", ""))
            family_presets[family].add(preset)

    trusted_families = set()
    for preset in trusted:
        trusted_families.update(family_by_preset.get(preset, {}))

    family_rows = []
    for family in sorted(set().union(*[set(counter) for counter in family_by_preset.values()]) if family_by_preset else set()):
        trusted_count = sum(family_by_preset.get(preset, Counter()).get(family, 0) for preset in trusted)
        ablation_count = sum(family_by_preset.get(preset, Counter()).get(family, 0) for preset in ablations)
        all_count = sum(counter.get(family, 0) for counter in family_by_preset.values())
        status = _family_status(family, trusted_count, ablation_count)
        family_rows.append(
            {
                "family": family,
                "status": status,
                "trusted_count": trusted_count,
                "ablation_count": ablation_count,
                "total_count": all_count,
                "presets": ",".join(sorted(family_presets[family])),
                "target_suites": ",".join(sorted(suite for suite in family_suites[family] if suite)),
            }
        )

    return {
        "preset_totals": preset_totals,
        "family_rows": family_rows,
        "trusted_families": trusted_families,
        "trusted_cases": sum(preset_totals.get(preset, Counter()).get("cases", 0) for preset in trusted),
        "trusted_false_positives": sum(
            preset_totals.get(preset, Counter()).get("false_positive_count", 0) for preset in trusted
        ),
        "ablation_cases": sum(preset_totals.get(preset, Counter()).get("cases", 0) for preset in ablations),
        "ablation_false_positives": sum(
            preset_totals.get(preset, Counter()).get("false_positive_count", 0) for preset in ablations
        ),
    }


def _parse_family_counts(text: str) -> list[tuple[str, int]]:
    if not text or text == "none":
        return []
    families = []
    for chunk in text.split(";"):
        chunk = chunk.strip()
        if not chunk or ":" not in chunk:
            continue
        family, count_text = chunk.rsplit(":", 1)
        try:
            count = int(float(count_text.strip()))
        except ValueError:
            continue
        families.append((family.strip(), count))
    return families


def _family_status(family: str, trusted_count: int, ablation_count: int) -> str:
    if trusted_count and ablation_count:
        return "trusted_and_ablation_detected"
    if trusted_count:
        return "trusted_detected"
    if ablation_count:
        return "ablation_only_do_not_count_without_triage"
    return "unclassified"


def _write_markdown(
    path: Path,
    manifest_file: Path,
    aggregate_csv: Path,
    trusted: tuple[str, ...],
    ablations: tuple[str, ...],
    audit: dict[str, Any],
) -> None:
    lines = [
        "# DataDiffFuzz Ablation Audit",
        "",
        f"- Manifest: `{manifest_file}`",
        f"- Aggregate CSV: `{aggregate_csv}`",
        f"- Trusted presets: `{','.join(trusted)}`",
        f"- Ablation presets: `{','.join(ablations)}`",
        "",
        "## Soundness Boundary",
        "",
        (
            f"Trusted presets executed {audit['trusted_cases']} cases with "
            f"{audit['trusted_false_positives']} oracle false positives. "
            f"Ablation presets executed {audit['ablation_cases']} cases with "
            f"{audit['ablation_false_positives']} oracle false positives."
        ),
        "",
        "## Preset Totals",
        "",
        "| preset | cases | findings | candidate cases | semantic divergences | false positives |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for preset in sorted(audit["preset_totals"]):
        totals = audit["preset_totals"][preset]
        lines.append(
            "| {preset} | {cases} | {findings} | {candidate} | {semantic} | {false_positive} |".format(
                preset=preset,
                cases=totals.get("cases", 0),
                findings=totals.get("findings", 0),
                candidate=totals.get("candidate_bug_cases", 0),
                semantic=totals.get("semantic_divergence_count", 0),
                false_positive=totals.get("false_positive_count", 0),
            )
        )
    lines.extend(
        [
            "",
            "## Candidate Family Audit",
            "",
            "| family | status | trusted count | ablation count | total count | presets | target suites |",
            "|---|---|---:|---:|---:|---|---|",
        ]
    )
    for row in audit["family_rows"]:
        lines.append(
            "| {family} | {status} | {trusted_count} | {ablation_count} | {total_count} | {presets} | {target_suites} |".format(
                **row
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "family",
        "status",
        "trusted_count",
        "ablation_count",
        "total_count",
        "presets",
        "target_suites",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _int(value: str | None) -> int:
    return int(float(value or 0))
