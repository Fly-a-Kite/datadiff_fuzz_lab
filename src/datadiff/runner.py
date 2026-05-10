from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from datadiff.artifact import save_bug_artifact
from datadiff.backends import make_backend
from datadiff.config import ExperimentConfig
from datadiff.datagen import generate_case
from datadiff.dsl import Case
from datadiff.env import collect_environment
from datadiff.feedback import FeedbackState
from datadiff.metamorphic import build_metamorphic_variants, evaluate_metamorphic_variants
from datadiff.normalizer import normalize_result
from datadiff.oracle import evaluate_case
from datadiff.util import RUNS_DIR, append_jsonl, dump_json, ensure_dirs, utc_now


def behavior_signature(row: dict[str, Any]) -> str:
    payload = {
        "case_ops": row["case"]["program"]["operations"],
        "backend_status": {
            b: r["status"] for b, r in sorted(row["normalized"].items())
        },
        "normalized_shape": {
            b: {
                "columns": r.get("columns", []),
                "rows": len(r.get("rows", [])),
                "sample": r.get("rows", [])[:3],
                "error_type": r.get("error_type", ""),
            }
            for b, r in sorted(row["normalized"].items())
        },
        "finding_kinds": sorted(f["kind"] for f in row.get("findings", [])),
        "finding_roots": sorted(f.get("root_cause", "unknown") for f in row.get("findings", [])),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
    return hashlib.sha256(raw).hexdigest()[:16]


def _execute_case(
    case: Case,
    backends: list[str],
    config: ExperimentConfig,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    raw_results = {}
    normalized = {}
    for backend_name in backends:
        backend = make_backend(backend_name)
        result = backend.run(case.tables, case.program)
        raw_results[backend_name] = {
            k: v
            for k, v in result.to_dict().items()
            if k != "data"
        }
        normalized[backend_name] = normalize_result(
            result,
            case.program,
            enable_normalizer=config.enable_normalizer,
        )
    return raw_results, normalized


def run_loaded_case(
    case: Case,
    backends: list[str],
    config: ExperimentConfig | None = None,
    save_artifact: bool = True,
) -> dict[str, Any]:
    config = config or ExperimentConfig()
    started = time.perf_counter()
    raw_results, normalized = _execute_case(case, backends, config)

    findings = []
    if config.enable_differential_oracle:
        findings = evaluate_case(case, normalized)
    metamorphic_rows: dict[str, Any] = {}
    if config.enable_metamorphic_oracle:
        variant_results = {}
        for variant in build_metamorphic_variants(case):
            variant_raw, variant_norm = _execute_case(variant.case, backends, config)
            variant_results[variant.name] = variant_norm
            metamorphic_rows[variant.name] = {
                "relation": variant.relation,
                "case": variant.case.to_dict(),
                "raw_results": variant_raw,
                "normalized": {k: v.to_dict() for k, v in variant_norm.items()},
            }
        findings.extend(evaluate_metamorphic_variants(case, normalized, variant_results))

    row = {
        "run_at": utc_now(),
        "case": case.to_dict(),
        "raw_results": raw_results,
        "normalized": {k: v.to_dict() for k, v in normalized.items()},
        "metamorphic": metamorphic_rows,
        "findings": [f.to_dict() for f in findings],
        "config": config.to_dict(),
        "environment": collect_environment(),
        "status": "bug" if findings else "ok",
        "duration_ms": (time.perf_counter() - started) * 1000,
    }
    row["behavior_signature"] = behavior_signature(row)
    if findings and save_artifact and config.enable_artifact:
        bug_dir = save_bug_artifact(
            case,
            raw_results=raw_results,
            normalized={k: v.to_dict() for k, v in normalized.items()},
            findings=findings,
            config=config.to_dict(),
        )
        row["bug_dir"] = str(bug_dir)
    return row


def run_fuzz(
    cases: int | None,
    seed: int,
    backends: list[str],
    config: ExperimentConfig | None = None,
    duration_s: float | None = None,
) -> Path:
    ensure_dirs()
    config = config or ExperimentConfig()
    if cases is None and duration_s is None:
        cases = 100
    run_id = f"run-{utc_now().replace(':', '').replace('-', '').replace('Z', '')}-{time.time_ns()}"
    run_file = RUNS_DIR / f"{run_id}.jsonl"
    seen: set[str] = set()
    feedback = FeedbackState() if config.enable_feedback else None
    started = time.perf_counter()
    executed = 0
    findings_count = 0
    new_behavior_count = 0

    while True:
        if cases is not None and executed >= cases:
            break
        if duration_s is not None and executed > 0 and (time.perf_counter() - started) >= duration_s:
            break
        case_seed = seed + executed
        generated = generate_case(
            case_seed,
            type_aware=config.enable_type_aware_generation,
            profile=config.generator_profile,
        )
        case = feedback.choose_case(case_seed, generated) if feedback is not None else generated
        row = run_loaded_case(
            case,
            backends=backends,
            config=config,
            save_artifact=not config.enable_reducer,
        )
        if row["findings"] and config.enable_reducer:
            from datadiff.reducer import reduce_case

            reduced = reduce_case(case, backends=backends, config=ExperimentConfig(
                enable_type_aware_generation=config.enable_type_aware_generation,
                enable_normalizer=config.enable_normalizer,
                enable_differential_oracle=config.enable_differential_oracle,
                enable_metamorphic_oracle=config.enable_metamorphic_oracle,
                enable_feedback=False,
                enable_reducer=False,
                enable_artifact=False,
                oracle_mode=config.oracle_mode,
                generator_profile=config.generator_profile,
            ), target_kinds=[finding["kind"] for finding in row["findings"]])
            reduced_row = run_loaded_case(reduced, backends=backends, config=config, save_artifact=True)
            reduced_row["original_case"] = case.to_dict()
            reduced_row["reduction"] = {
                "original_rows": len(case.tables[0].rows),
                "reduced_rows": len(reduced.tables[0].rows),
                "original_ops": len(case.program.operations),
                "reduced_ops": len(reduced.program.operations),
            }
            row = reduced_row

        sig = row["behavior_signature"]
        row["is_new_behavior"] = sig not in seen
        seen.add(sig)
        if feedback is not None:
            row["stored_in_feedback_corpus"] = feedback.record(case, sig, bool(row["findings"]))
        else:
            row["stored_in_feedback_corpus"] = False
        row["case_index"] = executed
        row["elapsed_s"] = round(time.perf_counter() - started, 6)
        findings_count += len(row["findings"])
        new_behavior_count += int(row["is_new_behavior"])
        append_jsonl(row, run_file)
        executed += 1

        if duration_s is not None and (time.perf_counter() - started) >= duration_s:
            break

    elapsed_s = time.perf_counter() - started
    dump_json(
        {
            "run_id": run_id,
            "run_file": str(run_file),
            "requested_cases": cases,
            "executed_cases": executed,
            "duration_s": duration_s,
            "elapsed_s": elapsed_s,
            "throughput_cases_s": executed / elapsed_s if elapsed_s else 0.0,
            "findings": findings_count,
            "new_behavior_cases": new_behavior_count,
            "seed": seed,
            "backends": backends,
            "config": config.to_dict(),
            "environment": collect_environment(),
        },
        RUNS_DIR / f"{run_id}.meta.json",
    )
    return run_file
