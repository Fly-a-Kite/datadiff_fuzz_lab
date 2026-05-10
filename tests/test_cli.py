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
            "--disable-normalizer",
            "--disable-feedback",
        ]
    )
    assert args.cmd == "fuzz"
    assert args.cases == 10
    assert args.seed == 5
    assert args.disable_normalizer is True
    assert args.disable_feedback is True
