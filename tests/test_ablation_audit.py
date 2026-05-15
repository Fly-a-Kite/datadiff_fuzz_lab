import csv

from datadiff import ablation_audit
from datadiff.ablation_audit import analyze_ablation_audit
from datadiff.util import dump_json


def test_analyze_ablation_audit_marks_ablation_only_families(tmp_path, monkeypatch):
    reports_dir = tmp_path / "reports"
    manifest = tmp_path / "runs" / "experiment-ablation.json"
    manifest.parent.mkdir(parents=True)
    dump_json({"runs": []}, manifest)
    monkeypatch.setattr(ablation_audit, "REPORTS_DIR", reports_dir)

    def fake_write_experiment_summary(manifest_file, *, refresh=False):
        reports_dir.mkdir(parents=True, exist_ok=True)
        md_path = reports_dir / f"experiment-summary-{manifest_file.stem}.md"
        csv_path = reports_dir / f"experiment-summary-{manifest_file.stem}.csv"
        aggregate_csv_path = reports_dir / f"{md_path.stem}-aggregates.csv"
        md_path.write_text("# Summary\n", encoding="utf-8")
        csv_path.write_text("", encoding="utf-8")
        aggregate_csv_path.write_text(
            "\n".join(
                [
                    "target_suite,preset,cases,findings,candidate_bug_cases,semantic_divergence_count,false_positive_count,top_candidate_bug_families",
                    "core,baseline,100,1,1,0,0,known_family@backend:1",
                    "core,no_type_aware,100,3,3,0,0,known_family@backend:1; weak_only@backend:2",
                    "core,no_normalizer,100,50,0,0,50,none",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        return md_path, csv_path

    monkeypatch.setattr(ablation_audit, "write_experiment_summary", fake_write_experiment_summary)

    md_path, csv_path = analyze_ablation_audit(manifest, refresh=True)

    md = md_path.read_text(encoding="utf-8")
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    known = next(row for row in rows if row["family"] == "known_family@backend")
    weak = next(row for row in rows if row["family"] == "weak_only@backend")
    assert "Trusted presets executed 100 cases with 0 oracle false positives" in md
    assert "Ablation presets executed 200 cases with 50 oracle false positives" in md
    assert known["status"] == "trusted_and_ablation_detected"
    assert weak["status"] == "ablation_only_do_not_count_without_triage"
    assert weak["ablation_count"] == "2"
