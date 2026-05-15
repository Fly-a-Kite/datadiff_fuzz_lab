import json
import os

from datadiff import cli
from datadiff.cli import _experiment_target_runs, _preset_config, build_parser
from datadiff.dsl import Case, ColumnSpec, Program, TableData
from datadiff.util import append_jsonl


def test_cli_parses_fuzz_ablation_flags():
    parser = build_parser()
    args = parser.parse_args(
        [
            "fuzz",
            "--cases",
            "10",
            "--seed",
            "5",
            "--duration",
            "10s",
            "--profile",
            "edge_float",
            "--disable-normalizer",
            "--disable-feedback",
            "--disable-preflight-repair",
            "--persist-feedback-corpus",
            "--feedback-persist-limit",
            "12",
            "--metamorphic-variant-limit",
            "9",
            "--log-level",
            "minimal",
        ]
    )
    assert args.cmd == "fuzz"
    assert args.cases == 10
    assert args.seed == 5
    assert args.duration == "10s"
    assert args.profile == "edge_float"
    assert args.disable_normalizer is True
    assert args.disable_feedback is True
    assert args.disable_preflight_repair is True
    assert args.persist_feedback_corpus is True
    assert args.feedback_persist_limit == 12
    assert args.metamorphic_variant_limit == 9
    assert args.log_level == "minimal"
    assert args.no_compress_run_log is False


def test_cli_parses_no_compress_run_log():
    parser = build_parser()
    args = parser.parse_args(["fuzz", "--no-compress-run-log"])
    assert args.cmd == "fuzz"
    assert args.no_compress_run_log is True


def test_cli_parses_artifact_limit():
    parser = build_parser()
    args = parser.parse_args(["longrun", "--artifact-limit", "25"])
    assert args.cmd == "longrun"
    assert args.artifact_limit == 25


def test_cli_parses_guided_fuzz_options():
    parser = build_parser()
    args = parser.parse_args(
        [
            "fuzz",
            "--strategy",
            "guided",
            "--candidate-pool",
            "12",
            "--targets",
            "groupby,nulls",
        ]
    )
    assert args.cmd == "fuzz"
    assert args.strategy == "guided"
    assert args.candidate_pool == 12
    assert args.targets == "groupby,nulls"


def test_cli_parses_workflow_profile():
    parser = build_parser()
    args = parser.parse_args(["fuzz", "--profile", "workflow"])
    assert args.cmd == "fuzz"
    assert args.profile == "workflow"


def test_cli_parses_bughunt_profile():
    parser = build_parser()
    args = parser.parse_args(["fuzz", "--profile", "bughunt"])
    assert args.cmd == "fuzz"
    assert args.profile == "bughunt"


def test_cli_parses_bughunt_no_groupby_profile():
    parser = build_parser()
    args = parser.parse_args(["fuzz", "--profile", "bughunt_no_groupby"])
    assert args.cmd == "fuzz"
    assert args.profile == "bughunt_no_groupby"


def test_cli_parses_null_groupby_topk_profile():
    parser = build_parser()
    args = parser.parse_args(["fuzz", "--profile", "null_groupby_topk"])
    assert args.cmd == "fuzz"
    assert args.profile == "null_groupby_topk"

    args = parser.parse_args(["longrun", "--profile", "null_groupby_topk"])
    assert args.cmd == "longrun"
    assert args.profile == "null_groupby_topk"


def test_cli_parses_null_agg_topk_profile():
    parser = build_parser()
    args = parser.parse_args(["fuzz", "--profile", "null_agg_topk"])
    assert args.cmd == "fuzz"
    assert args.profile == "null_agg_topk"

    args = parser.parse_args(["longrun", "--profile", "null_agg_topk"])
    assert args.cmd == "longrun"
    assert args.profile == "null_agg_topk"


def test_cli_parses_float_group_key_profile():
    parser = build_parser()
    args = parser.parse_args(["fuzz", "--profile", "float_group_key"])
    assert args.cmd == "fuzz"
    assert args.profile == "float_group_key"

    args = parser.parse_args(["longrun", "--profile", "float_group_key"])
    assert args.cmd == "longrun"
    assert args.profile == "float_group_key"


def test_cli_parses_target_suite():
    parser = build_parser()
    args = parser.parse_args(["fuzz", "--target-suite", "dataframe"])
    assert args.cmd == "fuzz"
    assert args.target_suite == "dataframe"
    assert args.backends is None


def test_cli_parses_targets_command():
    parser = build_parser()
    args = parser.parse_args(["targets"])
    assert args.cmd == "targets"


def test_cli_parses_targets_json_command():
    parser = build_parser()
    args = parser.parse_args(["targets", "--json"])
    assert args.cmd == "targets"
    assert args.json is True


def test_cli_prune_corpus_dry_run_and_yes(tmp_path, monkeypatch, capsys):
    corpus_dir = tmp_path / "corpus"
    interesting = corpus_dir / "interesting"
    interesting.mkdir(parents=True)
    files = []
    for idx in range(3):
        path = interesting / f"{idx}.json"
        path.write_text("{}", encoding="utf-8")
        os.utime(path, (idx + 1, idx + 1))
        files.append(path)
    monkeypatch.setattr(cli, "CORPUS_DIR", corpus_dir)

    parser = build_parser()
    args = parser.parse_args(["prune-corpus", "--keep", "1"])
    assert args.func(args) == 0
    assert all(path.exists() for path in files)
    assert "dry_run=true" in capsys.readouterr().out

    args = parser.parse_args(["prune-corpus", "--keep", "1", "--yes"])
    assert args.func(args) == 0
    remaining = sorted(path.name for path in interesting.glob("*.json"))
    assert remaining == ["2.json"]


def test_cli_parses_experiment_command():
    parser = build_parser()
    args = parser.parse_args(
        [
            "experiment",
            "--cases",
            "5",
            "--seeds",
            "1,2",
            "--presets",
            "baseline,metamorphic",
        ]
    )
    assert args.cmd == "experiment"
    assert args.cases == 5
    assert args.seeds == "1,2"
    assert args.presets == "baseline,metamorphic"
    assert args.no_compress_run_log is False
    assert args.target_suites is None
    assert args.metamorphic_variant_limit is None


def test_cli_parses_multi_target_suite_experiment():
    parser = build_parser()
    args = parser.parse_args(
        [
            "experiment",
            "--cases",
            "5",
            "--target-suites",
            "dataframe,embedded_sql,cross_family",
        ]
    )
    assert args.cmd == "experiment"
    assert args.target_suites == "dataframe,embedded_sql,cross_family"
    assert _experiment_target_runs(args) == [
        ("dataframe", ["pandas", "polars"]),
        ("embedded_sql", ["duckdb", "sqlite"]),
        ("cross_family", ["pandas", "duckdb"]),
    ]


def test_cli_parses_workflow_experiment_preset():
    parser = build_parser()
    args = parser.parse_args(["experiment", "--presets", "workflow"])
    assert args.cmd == "experiment"
    assert args.presets == "workflow"


def test_cli_parses_workflow_metamorphic_experiment_preset():
    parser = build_parser()
    args = parser.parse_args(["experiment", "--presets", "workflow_metamorphic"])
    assert args.cmd == "experiment"
    assert args.presets == "workflow_metamorphic"
    config = _preset_config(args.presets)
    assert config.generator_profile == "workflow"
    assert config.enable_metamorphic_oracle is True
    assert config.oracle_mode == "both"


def test_cli_parses_edge_float_guided_experiment_preset():
    parser = build_parser()
    args = parser.parse_args(["experiment", "--presets", "edge_float_guided"])
    assert args.cmd == "experiment"
    config = _preset_config(args.presets)
    assert config.generator_profile == "edge_float"
    assert config.guidance_strategy == "guided"
    assert config.guidance_candidate_pool == 8
    assert config.guidance_targets == ["edge_float", "numeric", "expressions"]


def test_cli_parses_edge_float_metamorphic_experiment_preset():
    parser = build_parser()
    args = parser.parse_args(["experiment", "--presets", "edge_float_metamorphic"])
    assert args.cmd == "experiment"
    config = _preset_config(args.presets)
    assert config.generator_profile == "edge_float"
    assert config.enable_metamorphic_oracle is True
    assert config.oracle_mode == "both"


def test_cli_parses_targeted_guided_experiment_presets():
    assert _preset_config("guided_filter").guidance_targets == ["filter"]
    assert _preset_config("guided_join").generator_profile == "bughunt_no_groupby"
    assert _preset_config("guided_join").guidance_targets == ["join", "sort_limit"]
    assert _preset_config("guided_mutate").guidance_targets == ["mutate", "expressions"]
    assert _preset_config("null_groupby_topk").generator_profile == "null_groupby_topk"
    assert _preset_config("null_groupby_topk").guidance_targets[0] == "null_groupby_topk"
    assert _preset_config("null_agg_topk").generator_profile == "null_agg_topk"
    assert _preset_config("null_agg_topk").guidance_targets[0] == "null_agg_topk"
    assert _preset_config("null_agg_topk_metamorphic").enable_metamorphic_oracle is True
    assert _preset_config("float_group_key").generator_profile == "float_group_key"
    assert _preset_config("float_group_key").guidance_targets[0] == "float_group_key"
    assert _preset_config("float_group_key_metamorphic").enable_metamorphic_oracle is True


def test_cli_parses_bughunt_guided_metamorphic_preset():
    config = _preset_config("bughunt_guided_metamorphic")
    assert config.generator_profile == "bughunt"
    assert config.enable_metamorphic_oracle is True
    assert config.guidance_strategy == "guided"
    assert config.metamorphic_variant_limit == 8


def test_cli_parses_bughunt_no_groupby_guided_metamorphic_preset():
    config = _preset_config("bughunt_no_groupby_guided_metamorphic")
    assert config.generator_profile == "bughunt_no_groupby"
    assert config.enable_metamorphic_oracle is True
    assert config.guidance_strategy == "guided"
    assert "groupby" not in config.guidance_targets
    assert config.metamorphic_variant_limit == 8


def test_cli_parses_bughunt_experiment_presets():
    assert _preset_config("bughunt").generator_profile == "bughunt"
    assert _preset_config("bughunt_no_groupby").generator_profile == "bughunt_no_groupby"
    guided = _preset_config("bughunt_guided")
    assert guided.generator_profile == "bughunt"
    assert guided.guidance_strategy == "guided"
    assert guided.guidance_targets == ["join", "groupby", "mutate", "filter", "expressions"]
    no_groupby_guided = _preset_config("bughunt_no_groupby_guided")
    assert no_groupby_guided.generator_profile == "bughunt_no_groupby"
    assert no_groupby_guided.guidance_targets == ["join", "mutate", "filter", "expressions", "sort_limit"]
    metamorphic = _preset_config("bughunt_metamorphic")
    assert metamorphic.generator_profile == "bughunt"
    assert metamorphic.enable_metamorphic_oracle is True
    no_groupby_metamorphic = _preset_config("bughunt_no_groupby_metamorphic")
    assert no_groupby_metamorphic.generator_profile == "bughunt_no_groupby"
    assert no_groupby_metamorphic.enable_metamorphic_oracle is True


def test_cli_experiment_duration_can_run_without_case_cap():
    parser = build_parser()
    args = parser.parse_args(["experiment", "--duration", "1s", "--seeds", "1"])
    assert args.cmd == "experiment"
    assert args.cases is None
    assert args.duration == "1s"


def test_cli_parses_analyze_experiment_command():
    parser = build_parser()
    args = parser.parse_args(
        [
            "analyze-experiment",
            "--manifest",
            "runs/experiment-x.json",
            "--baseline-preset",
            "baseline",
            "--compare-presets",
            "guided_filter,guided_join",
            "--refresh",
        ]
    )
    assert args.cmd == "analyze-experiment"
    assert args.manifest == "runs/experiment-x.json"
    assert args.baseline_preset == "baseline"
    assert args.compare_presets == "guided_filter,guided_join"
    assert args.refresh is True


def test_cli_parses_analyze_seeded_sensitivity_command():
    parser = build_parser()
    args = parser.parse_args(
        [
            "analyze-seeded-sensitivity",
            "--manifest",
            "runs/experiment-seeded.json",
        ]
    )
    assert args.cmd == "analyze-seeded-sensitivity"
    assert args.manifest == "runs/experiment-seeded.json"


def test_cli_parses_analyze_ablation_audit_command():
    parser = build_parser()
    args = parser.parse_args(
        [
            "analyze-ablation-audit",
            "--manifest",
            "runs/experiment-ablation.json",
            "--trusted-presets",
            "baseline,guided",
            "--ablation-presets",
            "no_type_aware,no_normalizer",
            "--refresh",
        ]
    )
    assert args.cmd == "analyze-ablation-audit"
    assert args.manifest == "runs/experiment-ablation.json"
    assert args.trusted_presets == "baseline,guided"
    assert args.ablation_presets == "no_type_aware,no_normalizer"
    assert args.refresh is True


def test_cli_parses_analyze_pattern_variants_command():
    parser = build_parser()
    args = parser.parse_args(
        [
            "analyze-pattern-variants",
            "--manifest",
            "runs/experiment-pattern.json",
            "--pattern",
            "null_agg_topk",
        ]
    )
    assert args.cmd == "analyze-pattern-variants"
    assert args.manifest == "runs/experiment-pattern.json"
    assert args.pattern == "null_agg_topk"


def test_classify_run_refresh_recomputes_current_oracle_roots(tmp_path, capsys):
    case = Case(
        "case-stale-root",
        14,
        [TableData("t0", [ColumnSpec("x", "int")], [{"x": 0}, {"x": 0}])],
        Program(
            "prog-stale-root",
            14,
            [
                {"op": "mutate", "column": "m_0", "expr": {"kind": "add_const", "source": "x", "value": -1}},
                {"op": "filter", "column": "m_0", "cmp": "==", "value": -1},
                {"op": "mutate", "column": "m_1", "expr": {"kind": "arith_const", "op": "mul", "source": "m_0", "value": 10}},
                {"op": "mutate", "column": "m_3", "expr": {"kind": "arith_const", "op": "div", "source": "m_1", "value": 3}},
                {"op": "groupby", "keys": ["m_3"], "aggs": [{"column": "m_0", "func": "min", "as": "min_m_0"}]},
            ],
        ),
    )
    run_file = tmp_path / "run-stale.jsonl"
    append_jsonl(
        {
            "status": "bug",
            "case": case.to_dict(),
            "findings": [
                {
                    "kind": "semantic_output_mismatch",
                    "root_cause": "groupby_aggregation",
                    "triage_verdict": "candidate_implementation_bug",
                    "suspicious_backends": ["b"],
                    "signature": "stale",
                    "confidence": "high",
                }
            ],
            "normalized": {
                "a": {"backend": "a", "status": "ok", "columns": ["m_3", "min_m_0"], "rows": [[-3.3333333333, -1]]},
                "c": {"backend": "c", "status": "ok", "columns": ["m_3", "min_m_0"], "rows": [[-3.3333333333, -1]]},
                "b": {
                    "backend": "b",
                    "status": "ok",
                    "columns": ["m_3", "min_m_0"],
                    "rows": [[-3.3333333333, -1], [-3.3333333333, -1]],
                },
            },
        },
        run_file,
    )

    parser = build_parser()
    args = parser.parse_args(["classify-run", "--run-file", str(run_file), "--refresh"])
    assert args.func(args) == 0
    out = capsys.readouterr().out

    assert "refresh=true" in out
    assert "float_group_key_instability@b: 1" in out
    assert "root=float_group_key_instability" in out


def test_cli_experiment_parses_no_compress_run_log():
    parser = build_parser()
    args = parser.parse_args(["experiment", "--no-compress-run-log"])
    assert args.cmd == "experiment"
    assert args.no_compress_run_log is True


def test_cli_experiment_parses_artifact_limit():
    parser = build_parser()
    args = parser.parse_args(["experiment", "--artifact-limit", "20"])
    assert args.cmd == "experiment"
    assert args.artifact_limit == 20


def test_cli_experiment_parses_skip_run_reports():
    parser = build_parser()
    args = parser.parse_args(["experiment", "--skip-run-reports"])
    assert args.cmd == "experiment"
    assert args.skip_run_reports is True


def test_cli_experiment_parses_jobs():
    parser = build_parser()
    args = parser.parse_args(["experiment", "--jobs", "4"])
    assert args.cmd == "experiment"
    assert args.jobs == 4


def test_experiment_parallel_scheduler_starts_heavy_jobs_first():
    fast = {
        "order": 0,
        "preset": "null_groupby_topk",
        "backends": ["pandas", "duckdb", "datafusion"],
    }
    slow = {
        "order": 1,
        "preset": "float_group_key_metamorphic",
        "backends": ["pandas", "polars", "polars_lazy", "duckdb", "sqlite", "datafusion"],
    }

    assert sorted([fast, slow], key=cli._experiment_job_sort_key) == [slow, fast]


def test_cli_experiment_summary_parses_refresh():
    parser = build_parser()
    args = parser.parse_args(["experiment-summary", "--refresh"])
    assert args.cmd == "experiment-summary"
    assert args.refresh is True


def test_cli_parses_longrun_defaults():
    parser = build_parser()
    args = parser.parse_args(["longrun"])
    assert args.cmd == "longrun"
    assert args.duration == "24h"
    assert args.cases is None
    assert args.strategy == "guided"
    assert args.candidate_pool == 8
    assert args.checkpoint_interval == "60s"
    assert args.progress_interval == "60s"
    assert args.save_cases is False
    assert args.no_save_cases is False
    assert args.log_level == "compact"


def test_cli_parses_experiment_summary_command():
    parser = build_parser()
    args = parser.parse_args(["experiment-summary", "--manifest", "runs/experiment-x.json"])
    assert args.cmd == "experiment-summary"
    assert args.manifest == "runs/experiment-x.json"


def test_cli_parses_report_csv_limit():
    parser = build_parser()
    args = parser.parse_args(["report", "--run-file", "runs/run-x.jsonl.gz", "--csv-limit", "100"])
    assert args.cmd == "report"
    assert args.csv_limit == 100


def test_cli_parses_artifact_validation_command():
    parser = build_parser()
    args = parser.parse_args(["validate-artifact", "--bug", "bugs/bug_x"])
    assert args.cmd == "validate-artifact"
    assert args.bug == "bugs/bug_x"


def test_cli_parses_classify_run_command():
    parser = build_parser()
    args = parser.parse_args(["classify-run", "--run-file", "runs/run-x.jsonl", "--limit", "2"])
    assert args.cmd == "classify-run"
    assert args.run_file == "runs/run-x.jsonl"
    assert args.limit == 2


def test_cli_classify_run_reads_compressed_jsonl(tmp_path, capsys):
    run_file = tmp_path / "run-x.jsonl.gz"
    append_jsonl({"case": {"case_id": "case-x", "seed": 1}, "findings": []}, run_file)

    parser = build_parser()
    args = parser.parse_args(["classify-run", "--run-file", str(run_file), "--limit", "2"])

    assert args.func(args) == 0
    out = capsys.readouterr().out
    assert f"run_file={run_file}" in out
    assert "- none" in out


def test_cli_classify_run_reports_candidate_bug_families(tmp_path, capsys):
    run_file = tmp_path / "run-family.jsonl.gz"
    append_jsonl(
        {
            "case": {"case_id": "case-x", "seed": 1},
            "findings": [
                {
                    "kind": "semantic_output_mismatch",
                    "root_cause": "grouped_topk_null_sort_key",
                    "triage_verdict": "candidate_implementation_bug",
                    "suspicious_backends": ["datafusion"],
                    "signature": "sig-x",
                }
            ],
        },
        run_file,
    )

    parser = build_parser()
    args = parser.parse_args(["classify-run", "--run-file", str(run_file), "--limit", "1"])

    assert args.func(args) == 0
    out = capsys.readouterr().out
    assert "candidate bug families:" in out
    assert "- grouped_topk_null_sort_key@datafusion: 1" in out


def test_cli_parses_artifact_triage_command():
    parser = build_parser()
    args = parser.parse_args(
        ["triage-artifact", "--bug", "bugs/bug_x", "--reduce", "--standalone-reproducer"]
    )
    assert args.cmd == "triage-artifact"
    assert args.bug == "bugs/bug_x"
    assert args.reduce is True
    assert args.standalone_reproducer is True


def test_cli_triage_artifact_writes_datafusion_standalone(tmp_path, monkeypatch, capsys):
    bug_dir = tmp_path / "bug_datafusion"
    bug_dir.mkdir()
    case = Case(
        "case-datafusion",
        1,
        [TableData("t0", [ColumnSpec("g", "str"), ColumnSpec("x", "int", nullable=True)], [{"g": "a", "x": None}])],
        Program(
            "prog-datafusion",
            1,
            [
                {"op": "groupby", "keys": ["g"], "aggs": [{"column": "x", "func": "min", "as": "min_x"}]},
                {"op": "sort", "columns": ["min_x"], "ascending": True},
                {"op": "limit", "n": 20},
            ],
        ),
    )
    (bug_dir / "case.json").write_text(json.dumps(case.to_dict()), encoding="utf-8")
    (bug_dir / "findings.json").write_text(
        json.dumps(
            [
                {
                    "kind": "semantic_output_mismatch",
                    "root_cause": "grouped_topk_null_sort_key",
                    "confidence": "high",
                    "suspicious_backends": ["datafusion"],
                }
            ]
        ),
        encoding="utf-8",
    )
    (bug_dir / "config.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        cli,
        "run_loaded_case",
        lambda *args, **kwargs: {
            "status": "bug",
            "findings": [
                {
                    "kind": "semantic_output_mismatch",
                    "root_cause": "grouped_topk_null_sort_key",
                    "confidence": "high",
                    "suspicious_backends": ["datafusion"],
                }
            ],
        },
    )

    parser = build_parser()
    args = parser.parse_args(
        [
            "triage-artifact",
            "--bug",
            str(bug_dir),
            "--backends",
            "pandas,duckdb,datafusion",
            "--standalone-reproducer",
        ]
    )

    assert args.func(args) == 0
    out = capsys.readouterr().out
    standalone = bug_dir / "standalone_datafusion_groupby_null_sortkey_limit.py"
    triage = json.loads((bug_dir / "triage.json").read_text(encoding="utf-8"))
    assert f"standalone_reproducer={standalone}" in out
    assert standalone.exists()
    assert "ORDER BY min_x ASC NULLS LAST LIMIT 20" in standalone.read_text(encoding="utf-8")
    assert triage["verdict"] == "candidate_implementation_bug"
