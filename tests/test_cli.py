from datadiff.cli import build_parser


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
        ]
    )
    assert args.cmd == "fuzz"
    assert args.cases == 10
    assert args.seed == 5
    assert args.duration == "10s"
    assert args.profile == "edge_float"
    assert args.disable_normalizer is True
    assert args.disable_feedback is True


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


def test_cli_parses_experiment_summary_command():
    parser = build_parser()
    args = parser.parse_args(["experiment-summary", "--manifest", "runs/experiment-x.json"])
    assert args.cmd == "experiment-summary"
    assert args.manifest == "runs/experiment-x.json"


def test_cli_parses_artifact_validation_command():
    parser = build_parser()
    args = parser.parse_args(["validate-artifact", "--bug", "bugs/bug_x"])
    assert args.cmd == "validate-artifact"
    assert args.bug == "bugs/bug_x"
