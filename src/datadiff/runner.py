from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from datadiff.artifact import save_bug_artifact
from datadiff.backends import make_backend
from datadiff.config import ExperimentConfig
from datadiff.datagen import generate_case
from datadiff.dsl import Case
from datadiff.env import collect_environment
from datadiff.normalizer import normalize_result
from datadiff.oracle import evaluate_case
from datadiff.util import RUNS_DIR, append_jsonl, dump_json, ensure_dirs, utc_now


def behavior_signature(row: dict[str, Any]) -> str:
    payload = {
        "case_ops": row["case"]["program"]["operations"],
        "backend_status": {
            b: r["status"] for b, r in sorted(row["normalized"].items())
        },
        "finding_kinds": sorted(f["kind"] for f in row.get("findings", [])),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
    return hashlib.sha256(raw).hexdigest()[:16]


def run_loaded_case(
    case: Case,
    backends: list[str],
    config: ExperimentConfig | None = None,
    save_artifact: bool = True,
) -> dict[str, Any]:
    config = config or ExperimentConfig()
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
        norm = normalize_result(
            result,
            case.program,
            enable_normalizer=config.enable_normalizer,
        )
        normalized[backend_name] = norm

    findings = []
    if config.enable_differential_oracle:
        findings = evaluate_case(case, normalized)

    row = {
        "run_at": utc_now(),
        "case": case.to_dict(),
        "raw_results": raw_results,
        "normalized": {k: v.to_dict() for k, v in normalized.items()},
        "findings": [f.to_dict() for f in findings],
        "config": config.to_dict(),
        "environment": collect_environment(),
        "status": "bug" if findings else "ok",
    }
    row["behavior_signature"] = behavior_signature(row)
    if findings and save_artifact and config.enable_artifact:
        bug_dir = save_bug_artifact(
            case,
            raw_results=raw_results,
            normalized={k: v.to_dict() for k, v in normalized.items()},
            findings=findings,
        )
        row["bug_dir"] = str(bug_dir)
    return row


def run_fuzz(
    cases: int,
    seed: int,
    backends: list[str],
    config: ExperimentConfig | None = None,
) -> Path:
    ensure_dirs()
    config = config or ExperimentConfig()
    run_id = f"run-{utc_now().replace(':', '').replace('-', '').replace('Z', '')}"
    run_file = RUNS_DIR / f"{run_id}.jsonl"
    seen: set[str] = set()
    for i in range(cases):
        case = generate_case(seed + i)
        row = run_loaded_case(case, backends=backends, config=config)
        sig = row["behavior_signature"]
        row["is_new_behavior"] = sig not in seen
        seen.add(sig)
        append_jsonl(row, run_file)
    dump_json(
        {
            "run_id": run_id,
            "run_file": str(run_file),
            "cases": cases,
            "seed": seed,
            "backends": backends,
            "config": config.to_dict(),
            "environment": collect_environment(),
        },
        RUNS_DIR / f"{run_id}.meta.json",
    )
    return run_file
