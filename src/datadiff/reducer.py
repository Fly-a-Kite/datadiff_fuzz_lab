from __future__ import annotations

from collections.abc import Iterable

from datadiff.config import ExperimentConfig
from datadiff.dsl import Case
from datadiff.runner import run_loaded_case


def reduce_case(
    case: Case,
    backends: list[str],
    config: ExperimentConfig | None = None,
    target_kinds: Iterable[str] | None = None,
) -> Case:
    """Small deterministic reducer for the MVP.

    It currently minimizes rows and trailing operations. The reducer keeps a
    candidate only if it still triggers at least one finding. This module exists
    so ablation experiments can compare artifact quality with and without
    reduction; later versions should add column/value/expression reducers.
    """

    config = config or ExperimentConfig(enable_artifact=False)
    target = set(target_kinds or [])
    best = case

    changed = True
    while changed:
        changed = False

        table = best.tables[0]
        for idx in range(len(table.rows)):
            if len(table.rows) <= 1:
                break
            candidate_rows = table.rows[:idx] + table.rows[idx + 1 :]
            candidate_table = type(table)(table.name, table.columns, candidate_rows)
            candidate = Case(best.case_id, best.seed, [candidate_table], best.program)
            if _preserves_target(candidate, backends, config, target):
                best = candidate
                changed = True
                break

        if changed:
            continue

        ops = best.program.operations
        for idx in range(len(ops) - 1, -1, -1):
            if len(ops) <= 1:
                break
            candidate_program = type(best.program)(best.program.program_id, best.program.seed, ops[:idx] + ops[idx + 1 :])
            candidate = Case(best.case_id, best.seed, best.tables, candidate_program)
            if _preserves_target(candidate, backends, config, target):
                best = candidate
                changed = True
                break

    return best


def _preserves_target(
    candidate: Case,
    backends: list[str],
    config: ExperimentConfig,
    target_kinds: set[str],
) -> bool:
    findings = run_loaded_case(candidate, backends, config=config, save_artifact=False)["findings"]
    if not findings:
        return False
    if not target_kinds:
        return True
    return bool(target_kinds & {finding["kind"] for finding in findings})
