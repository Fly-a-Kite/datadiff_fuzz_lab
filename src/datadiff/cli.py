from __future__ import annotations

import argparse
from pathlib import Path

from datadiff.config import ExperimentConfig
from datadiff.dsl import Case
from datadiff.reporter import latest_run_file, write_report
from datadiff.reducer import reduce_case
from datadiff.runner import run_fuzz, run_loaded_case
from datadiff.util import BUGS_DIR, REPORTS_DIR, RUNS_DIR, ensure_dirs, load_json, read_jsonl


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
    )
    print(f"run log written: {out}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    run_file = Path(args.run_file) if args.run_file else latest_run_file()
    md_path, csv_path = write_report(run_file)
    print(f"markdown report: {md_path}")
    print(f"csv findings:    {csv_path}")
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
    print(f"Run this command to reproduce:\npython {repro}")
    return 0


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="datadiff",
        description="Semantic differential fuzzing for DataFrame and embedded analytical engines.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="create project runtime directories")
    p_init.set_defaults(func=cmd_init)

    p_fuzz = sub.add_parser("fuzz", help="run differential fuzzing")
    p_fuzz.add_argument("--cases", type=int, default=100)
    p_fuzz.add_argument("--seed", type=int, default=1)
    p_fuzz.add_argument("--backends", default="pandas,polars,duckdb")
    add_ablation_flags(p_fuzz)
    p_fuzz.set_defaults(func=cmd_fuzz)

    p_report = sub.add_parser("report", help="generate markdown/csv report")
    p_report.add_argument("--run-file", default=None)
    p_report.set_defaults(func=cmd_report)

    p_show = sub.add_parser("show-bugs", help="print bug findings")
    p_show.add_argument("--run-file", default=None)
    p_show.add_argument("--limit", type=int, default=10)
    p_show.set_defaults(func=cmd_show_bugs)

    p_repro = sub.add_parser("reproduce", help="show reproduce command for a bug artifact")
    p_repro.add_argument("--bug", required=True)
    p_repro.set_defaults(func=cmd_reproduce)

    p_reduce = sub.add_parser("reduce", help="minimize a bug artifact while preserving findings")
    p_reduce.add_argument("--bug", required=True)
    p_reduce.add_argument("--backends", default="pandas,polars,duckdb")
    p_reduce.set_defaults(func=cmd_reduce)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
