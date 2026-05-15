import json
from pathlib import Path


def test_ubuntu_datafusion_artifact_manifest_paths_exist():
    root = Path(__file__).resolve().parents[1]
    manifest_path = root / "reports" / "ubuntu-datafusion-artifact-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    paths = [
        manifest["summary_document"],
        manifest["methodology_roadmap"],
        *manifest.get("ablation_audit", {}).values(),
        *manifest.get("pattern_analyses", {}).values(),
        *manifest["environment"].values(),
        *manifest["primary_artifact"].values(),
    ]
    for experiment in manifest["experiments"]:
        paths.extend(
            [
                experiment["manifest"],
                experiment["summary"],
                experiment["analysis"],
                experiment["aggregate_csv"],
            ]
        )

    for rel_path in paths:
        path = root / rel_path
        assert path.exists(), rel_path
        assert path.stat().st_size > 0, rel_path
