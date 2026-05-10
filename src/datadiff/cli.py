from __future__ import annotations

import argparse
from pathlib import Path

from datadiff.config import ExperimentConfig
from datadiff.dsl import Case
from datadiff.reporter import latest_run_file, write_experiment_summary, write_report
from datadiff.reducer import reduce_case
from datadiff.runner import run_fuzz, run_loaded_case
from datadiff.util import BUGS_DIR, REPORTS_DIR, RUNS_DIR, dump_json, ensure_dirs, load_json, parse_duration, read_jsonl, utc_now


def _parse_backends(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def _config_from_args(args: argparse.Namespace) -> ExperimentConfig:
    return ExperimentConfig(
        enable_type_aware_generation=not args.disable_type_aware_generation,
        enable_normalizer=not args.disable_normalizer,
        enable_differential_oracle=not args.disable_differential_oracle,
        enable_metamorphic_oracle=args.enable_metamorphic_oracle,
        enable_feedback=not args.disable_feedback,
        enable_reducer=args.enable_reducer,
        enable_artifact=not args.disable_artifact,
        oracle_mode="both" if args.enable_metamorphic_oracle else "differential",
        generator_profile=args.profile,
    )


def add_ablation_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--disable-type-aware-generation", action="store_true")
    parser.add_argument("--disable-normalizer", action="store_true")
    parser.add_argument("--disable-differential-oracle", action="store_true")
    parser.add_argument("--enable-metamorphic-oracle", action="store_true")
    parser.add_argument("--disable-feedback", action="store_true")
    parser.add_argument("--enable-reducer", action="store_true")
    parser.add_argument("--disable-artifact", action="store_true")


def cmd_init(args: argparse.Namespace) -> int:
    ensure_dirs()
    print("Initialized DataDiffFuzz")
    print(f"runs:    {RUNS_DIR}")
    print(f"bugs:    {BUGS_DIR}")
    print(f"reports: {REPORTS_DIR}")
    return 0


def cmd_fuzz(args: argparse.Namespace) -> int:
    out = run_fuzz(
        cases=args.cases,
        seed=args.seed,
        backends=_parse_backends(args.backends),
        config=_config_from_args(args),
        duration_s=parse_duration(args.duration),
    )
    print(f"run log written: {out}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    run_file = Path(args.run_file) if args.run_file else latest_run_file()
    md_path, csv_path = write_report(run_file)
    print(f"markdown report: {md_path}")
    print(f"csv findings:    {csv_path}")
    return 0


def cmd_experiment_summary(args: argparse.Namespace) -> int:
    manifest_file = Path(args.manifest) if args.manifest else None
    md_path, csv_path = write_experiment_summary(manifest_file)
    print(f"markdown summary: {md_path}")
    print(f"csv summary:      {csv_path}")
    return 0


def cmd_show_bugs(args: argparse.Namespace) -> int:
    run_file = Path(args.run_file) if args.run_file else latest_run_file()
    rows = read_jsonl(run_file)
    shown = 0
    for row in rows:
        if not row.get("findings"):
            continue
        print("=" * 88)
        print(f"{row['case']['case_id']} seed={row['case']['seed']} status={row['status']}")
        print(f"ops={[op['op'] for op in row['case']['program']['operations']]}")
        print(f"bug_dir={row.get('bug_dir', '')}")
        for backend, norm in row.get("normalized", {}).items():
            print(
                f"  {backend}: {norm.get('status')} "
                f"rows={len(norm.get('rows', []))} cols={norm.get('columns', [])}"
            )
        for finding in row.get("findings", []):
            print(
                f"- [{finding['severity']}] {finding['kind']} "
                f"root={finding.get('root_cause', 'unknown')} "
                f"oracle={finding.get('oracle', 'unknown')} "
                f"suspicious={finding.get('suspicious_backends', [])}: {finding['evidence']}"
            )
        shown += 1
        if shown >= args.limit:
            break
    if shown == 0:
        print("No bugs in selected run.")
    return 0


def cmd_reproduce(args: argparse.Namespace) -> int:
    bug_dir = Path(args.bug)
    repro = bug_dir / "reproduce.py"
    if not repro.exists():
        raise FileNotFoundError(repro)
    if args.print_command:
        print(f"Run this command to reproduce:\npython {repro}")
        return 0
    case = Case.from_dict(load_json(bug_dir / "case.json"))
    config_path = bug_dir / "config.json"
    config_data = load_json(config_path) if config_path.exists() else {}
    config = ExperimentConfig(**config_data) if config_data else ExperimentConfig()
    backends = _parse_backends(args.backends) if args.backends else list(load_json(bug_dir / "results.json"))
    result = run_loaded_case(case, backends=backends, config=config, save_artifact=False)
    print(f"status={result['status']}")
    for finding in result["findings"]:
        print(
            f"- {finding['kind']} root={finding.get('root_cause', 'unknown')} "
            f"oracle={finding.get('oracle', 'unknown')} signature={finding.get('signature', '')}"
        )
    return 0


def cmd_validate_artifact(args: argparse.Namespace) -> int:
    bug_dir = Path(args.bug)
    case = Case.from_dict(load_json(bug_dir / "case.json"))
    original_findings = load_json(bug_dir / "findings.json")
    config_path = bug_dir / "config.json"
    config_data = load_json(config_path) if config_path.exists() else {}
    config = ExperimentConfig(**config_data) if config_data else ExperimentConfig()
    backends = _parse_backends(args.backends) if args.backends else list(load_json(bug_dir / "results.json"))
    result = run_loaded_case(case, backends=backends, config=config, save_artifact=False)

    original_kinds = {f.get("kind", "") for f in original_findings}
    reproduced_kinds = {f.get("kind", "") for f in result.get("findings", [])}
    original_roots = {f.get("root_cause", "unknown") for f in original_findings}
    reproduced_roots = {f.get("root_cause", "unknown") for f in result.get("findings", [])}
    kind_ok = bool(original_kinds & reproduced_kinds)
    root_ok = bool(original_roots & reproduced_roots) if original_roots else True
    ok = result["status"] == "bug" and kind_ok and root_ok
    print(f"artifact={bug_dir}")
    print(f"status={'valid' if ok else 'not-reproduced'}")
    print(f"original_kinds={sorted(original_kinds)}")
    print(f"reproduced_kinds={sorted(reproduced_kinds)}")
    print(f"original_roots={sorted(original_roots)}")
    print(f"reproduced_roots={sorted(reproduced_roots)}")
    return 0 if ok else 1


def cmd_reduce(args: argparse.Namespace) -> int:
    bug_dir = Path(args.bug)
    case = Case.from_dict(load_json(bug_dir / "case.json"))
    backends = _parse_backends(args.backends)
    reduced = reduce_case(case, backends=backends)
    result = run_loaded_case(reduced, backends=backends)
    print(f"original rows={len(case.tables[0].rows)} ops={len(case.program.operations)}")
    print(f"reduced rows={len(reduced.tables[0].rows)} ops={len(reduced.program.operations)}")
    print(f"status={result['status']} bug_dir={result.get('bug_dir', '')}")
    return 0


def _parse_seeds(value: str) -> list[int]:
    seeds: list[int] = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        seeds.append(int(part))
    if not seeds:
        raise ValueError("at least one seed is required")
    return seeds


def _preset_config(name: str) -> ExperimentConfig:
    if name == "baseline":
        return ExperimentConfig()
    if name == "no_type_aware":
        return ExperimentConfig(enable_type_aware_generation=False)
    if name == "no_normalizer":
        return ExperimentConfig(enable_normalizer=False)
    if name == "no_feedback":
        return ExperimentConfig(enable_feedback=False)
    if name == "metamorphic":
        return ExperimentConfig(enable_metamorphic_oracle=True, oracle_mode="both")
    if name == "reducer":
        return ExperimentConfig(enable_reducer=True)
    if name == "oracle_only_metamorphic":
        return ExperimentConfig(
            enable_differential_oracle=False,
            enable_metamorphic_oracle=True,
            oracle_mode="metamorphic",
        )
    if name == "edge_float":
        return ExperimentConfig(generator_profile="edge_float")
    raise ValueError(f"unknown experiment preset: {name}")


def cmd_experiment(args: argparse.Namespace) -> int:
    ensure_dirs()
    presets = [p.strip() for p in args.presets.split(",") if p.strip()]
    seeds = _parse_seeds(args.seeds)
    backends = _parse_backends(args.backends)
    duration_s = parse_duration(args.duration)
    manifest = {
        "created_at": utc_now(),
        "presets": presets,
        "seeds": seeds,
        "cases": args.cases,
        "duration_s": duration_s,
        "backends": backends,
        "runs": [],
    }
    for preset in presets:
        for seed in seeds:
            run_file = run_fuzz(
                cases=args.cases,
                seed=seed,
                backends=backends,
                config=_preset_config(preset),
                duration_s=duration_s,
            )
            md_path, csv_path = write_report(run_file)
            manifest["runs"].append(
                {
                    "preset": preset,
                    "seed": seed,
                    "run_file": str(run_file),
                    "report": str(md_path),
                    "csv": str(csv_path),
                }
            )
            print(f"{preset} seed={seed} run={run_file}")
    ts = utc_now().replace(":", "").replace("-", "").replace("Z", "")
    manifest_path = RUNS_DIR / f"experiment-{ts}.json"
    dump_json(manifest, manifest_path)
    print(f"experiment manifest: {manifest_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="datadiff",
        description="Semantic differential fuzzing for DataFrame and embedded analytical engines.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="create project runtime directories")
    p_init.set_defaults(func=cmd_init)

    p_fuzz = sub.add_parser("fuzz", help="run differential fuzzing")
    p_fuzz.add_argument("--cases", type=int, default=None, help="maximum cases; defaults to 100 when --duration is absent")
    p_fuzz.add_argument("--duration", default=None, help="wall-clock budget such as 10s, 5m, 24h")
    p_fuzz.add_argument("--seed", type=int, default=1)
    p_fuzz.add_argument("--backends", default="pandas,polars,duckdb,sqlite")
    p_fuzz.add_argument("--profile", choices=["common", "edge_float"], default="common")
    add_ablation_flags(p_fuzz)
    p_fuzz.set_defaults(func=cmd_fuzz)

    p_report = sub.add_parser("report", help="generate markdown/csv report")
    p_report.add_argument("--run-file", default=None)
    p_report.set_defaults(func=cmd_report)

    p_exp_summary = sub.add_parser("experiment-summary", help="summarize an experiment manifest")
    p_exp_summary.add_argument("--manifest", default=None)
    p_exp_summary.set_defaults(func=cmd_experiment_summary)

    p_show = sub.add_parser("show-bugs", help="print bug findings")
    p_show.add_argument("--run-file", default=None)
    p_show.add_argument("--limit", type=int, default=10)
    p_show.set_defaults(func=cmd_show_bugs)

    p_repro = sub.add_parser("reproduce", help="show reproduce command for a bug artifact")
    p_repro.add_argument("--bug", required=True)
    p_repro.add_argument("--backends", default=None)
    p_repro.add_argument("--print-command", action="store_true")
    p_repro.set_defaults(func=cmd_reproduce)

    p_validate = sub.add_parser("validate-artifact", help="rerun a bug artifact and check finding preservation")
    p_validate.add_argument("--bug", required=True)
    p_validate.add_argument("--backends", default=None)
    p_validate.set_defaults(func=cmd_validate_artifact)

    p_reduce = sub.add_parser("reduce", help="minimize a bug artifact while preserving findings")
    p_reduce.add_argument("--bug", required=True)
    p_reduce.add_argument("--backends", default="pandas,polars,duckdb,sqlite")
    p_reduce.set_defaults(func=cmd_reduce)

    p_exp = sub.add_parser("experiment", help="run repeatable ablation experiment matrix")
    p_exp.add_argument("--cases", type=int, default=100)
    p_exp.add_argument("--duration", default=None, help="optional per-run wall-clock budget such as 10s, 5m, 24h")
    p_exp.add_argument("--seeds", default="1,1001,2001")
    p_exp.add_argument("--backends", default="pandas,polars,duckdb,sqlite")
    p_exp.add_argument(
        "--presets",
        default="baseline,no_type_aware,no_normalizer,no_feedback,metamorphic,reducer",
        help="comma-separated presets",
    )
    p_exp.set_defaults(func=cmd_experiment)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
