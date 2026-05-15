import importlib.util
from pathlib import Path
import tarfile

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "build_upstream_issue_bundle.py"
SPEC = importlib.util.spec_from_file_location("build_upstream_issue_bundle", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
bundle_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bundle_module)

collect_issue_paths = bundle_module.collect_issue_paths
validate_paths = bundle_module.validate_paths
write_bundle = bundle_module.write_bundle


def test_collect_issue_paths_uses_only_minimal_upstream_files():
    manifest = {
        "primary_artifact": {
            "upstream_issue_draft": "bugs/x/upstream_issue.md",
            "standalone_reproducer": "bugs/x/standalone.py",
            "triage_json": "bugs/x/triage.json",
            "preflight_boundary_script": "scripts/preflight.py",
            "preflight_boundary_output": "reports/preflight.txt",
            "upstream_issue_checklist": "reports/checklist.md",
        },
        "experiments": [
            {"manifest": "runs/large.json"},
        ],
    }

    assert collect_issue_paths(manifest) == [
        "bugs/x/standalone.py",
        "bugs/x/upstream_issue.md",
        "reports/checklist.md",
        "reports/preflight.txt",
        "scripts/preflight.py",
    ]


def test_validate_paths_reports_missing_and_empty_issue_files(tmp_path):
    (tmp_path / "present.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / "empty.md").write_text("", encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="missing=missing.py; empty=empty.md"):
        validate_paths(["present.py", "missing.py", "empty.md"], root=tmp_path)


def test_write_bundle_contains_minimal_issue_members(tmp_path):
    (tmp_path / "bugs" / "x").mkdir(parents=True)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "bugs" / "x" / "upstream_issue.md").write_text("# issue\n", encoding="utf-8")
    (tmp_path / "scripts" / "preflight.py").write_text("print('check')\n", encoding="utf-8")
    output = tmp_path / "issue.tar.gz"

    write_bundle(["bugs/x/upstream_issue.md", "scripts/preflight.py"], output, root=tmp_path)

    with tarfile.open(output, "r:gz") as tar:
        assert tar.getnames() == [
            "bugs/x/upstream_issue.md",
            "scripts/preflight.py",
        ]
