import importlib.util
from pathlib import Path
import tarfile

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "build_ubuntu_artifact_bundle.py"
SPEC = importlib.util.spec_from_file_location("build_ubuntu_artifact_bundle", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
bundle_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bundle_module)

collect_manifest_paths = bundle_module.collect_manifest_paths
bundle_members = bundle_module.bundle_members
validate_paths = bundle_module.validate_paths
write_bundle = bundle_module.write_bundle


def test_collect_manifest_paths_deduplicates_and_sorts():
    manifest = {
        "summary_document": "reports/summary.md",
        "ablation_audit": {"markdown": "reports/audit.md", "csv": "reports/audit.csv"},
        "pattern_analyses": {"null_agg_topk": "reports/pattern.md", "null_agg_topk_csv": "reports/pattern.csv"},
        "environment": {"pip": "reports/pip.txt"},
        "primary_artifact": {"triage": "bugs/x/triage.json"},
        "experiments": [
            {
                "manifest": "runs/e.json",
                "summary": "reports/s.md",
                "analysis": "reports/a.md",
                "aggregate_csv": "reports/s-aggregates.csv",
            },
            {
                "manifest": "runs/e.json",
                "summary": "reports/s.md",
                "analysis": "reports/a2.md",
                "aggregate_csv": "reports/s2-aggregates.csv",
            },
        ],
    }

    assert collect_manifest_paths(manifest) == [
        "bugs/x/triage.json",
        "reports/a.md",
        "reports/a2.md",
        "reports/audit.csv",
        "reports/audit.md",
        "reports/pattern.csv",
        "reports/pattern.md",
        "reports/pip.txt",
        "reports/s-aggregates.csv",
        "reports/s.md",
        "reports/s2-aggregates.csv",
        "reports/summary.md",
        "runs/e.json",
    ]


def test_validate_paths_reports_missing_and_empty_files(tmp_path):
    (tmp_path / "present.txt").write_text("ok", encoding="utf-8")
    (tmp_path / "empty.txt").write_text("", encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="missing=missing.txt; empty=empty.txt"):
        validate_paths(["present.txt", "missing.txt", "empty.txt"], root=tmp_path)


def test_bundle_members_expands_directories_without_duplicates(tmp_path):
    bug_dir = tmp_path / "bugs" / "bug_x"
    bug_dir.mkdir(parents=True)
    (bug_dir / "case.json").write_text("{}", encoding="utf-8")
    (bug_dir / "triage.json").write_text("{}", encoding="utf-8")

    assert bundle_members(
        [
            "bugs/bug_x",
            "bugs/bug_x/triage.json",
        ],
        root=tmp_path,
    ) == [
        "bugs/bug_x/case.json",
        "bugs/bug_x/triage.json",
    ]


def test_write_bundle_has_unique_members_when_directory_and_child_are_listed(tmp_path):
    bug_dir = tmp_path / "bugs" / "bug_x"
    bug_dir.mkdir(parents=True)
    (bug_dir / "case.json").write_text("{}", encoding="utf-8")
    (bug_dir / "triage.json").write_text("{}", encoding="utf-8")
    output = tmp_path / "bundle.tar.gz"

    write_bundle(["bugs/bug_x", "bugs/bug_x/triage.json"], output, root=tmp_path)

    with tarfile.open(output, "r:gz") as tar:
        names = tar.getnames()
    assert names == [
        "bugs/bug_x/case.json",
        "bugs/bug_x/triage.json",
    ]
