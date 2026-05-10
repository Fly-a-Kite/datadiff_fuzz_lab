from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from datadiff.dsl import Case, Program, TableData
from datadiff.normalizer import NormalizedResult
from datadiff.oracle import Finding


@dataclass(slots=True)
class MetamorphicVariant:
    name: str
    relation: str
    case: Case


def build_metamorphic_variants(case: Case, limit: int = 3) -> list[MetamorphicVariant]:
    variants: list[MetamorphicVariant] = []
    variants.extend(_row_permutation_variants(case))
    variants.extend(_filter_commutativity_variants(case))
    variants.extend(_select_idempotence_variants(case))
    return variants[:limit]


def evaluate_metamorphic_variants(
    case: Case,
    base: dict[str, NormalizedResult],
    variants: dict[str, dict[str, NormalizedResult]],
) -> list[Finding]:
    findings: list[Finding] = []
    for variant_name, normalized in variants.items():
        for backend, base_result in base.items():
            variant_result = normalized.get(backend)
            if variant_result is None:
                continue
            if _payload(base_result) == _payload(variant_result):
                continue
            relation = variant_name.split(":", 1)[0]
            sig = _signature(case, backend, variant_name, base_result, variant_result)
            findings.append(
                Finding(
                    finding_id=f"finding-{sig}",
                    kind=f"metamorphic_{relation}_violation",
                    severity="high",
                    suspicious_backends=[backend],
                    evidence=(
                        f"Backend {backend} violates metamorphic relation {variant_name}; "
                        f"base_status={base_result.status} variant_status={variant_result.status}"
                    ),
                    signature=sig,
                    root_cause=f"metamorphic_{relation}",
                    oracle="metamorphic",
                    confidence="medium",
                )
            )
    return findings


def _row_permutation_variants(case: Case) -> list[MetamorphicVariant]:
    ops = case.program.op_sequence()
    if "limit" in ops:
        return []
    table = case.tables[0]
    if len(table.rows) < 2:
        return []
    permuted_table = TableData(table.name, table.columns, list(reversed(table.rows)))
    variant = Case(
        case_id=f"{case.case_id}-mr-row-permutation",
        seed=case.seed,
        tables=[permuted_table],
        program=case.program,
    )
    return [MetamorphicVariant("row_permutation:reverse", "row_permutation", variant)]


def _filter_commutativity_variants(case: Case) -> list[MetamorphicVariant]:
    ops = case.program.operations
    variants: list[MetamorphicVariant] = []
    for idx in range(len(ops) - 1):
        if ops[idx].get("op") != "filter" or ops[idx + 1].get("op") != "filter":
            continue
        swapped = list(ops)
        swapped[idx], swapped[idx + 1] = swapped[idx + 1], swapped[idx]
        program = Program(
            program_id=f"{case.program.program_id}-mr-filter-commute-{idx}",
            seed=case.program.seed,
            operations=swapped,
        )
        variants.append(
            MetamorphicVariant(
                f"filter_commutativity:swap-{idx}-{idx + 1}",
                "filter_commutativity",
                Case(f"{case.case_id}-mr-filter-commute-{idx}", case.seed, case.tables, program),
            )
        )
        break
    return variants


def _select_idempotence_variants(case: Case) -> list[MetamorphicVariant]:
    ops = case.program.operations
    for idx, op in enumerate(ops):
        if op.get("op") != "select":
            continue
        duplicated = ops[: idx + 1] + [dict(op)] + ops[idx + 1 :]
        program = Program(
            program_id=f"{case.program.program_id}-mr-select-idempotence-{idx}",
            seed=case.program.seed,
            operations=duplicated,
        )
        return [
            MetamorphicVariant(
                f"select_idempotence:duplicate-{idx}",
                "select_idempotence",
                Case(f"{case.case_id}-mr-select-idempotence-{idx}", case.seed, case.tables, program),
            )
        ]
    return []


def _payload(norm: NormalizedResult) -> dict[str, Any]:
    return {
        "status": norm.status,
        "columns": norm.columns,
        "rows": norm.rows,
        "error_type": norm.error_type,
    }


def _signature(
    case: Case,
    backend: str,
    variant_name: str,
    base_result: NormalizedResult,
    variant_result: NormalizedResult,
) -> str:
    payload = {
        "case_id": case.case_id,
        "backend": backend,
        "variant": variant_name,
        "base": _payload(base_result),
        "variant_result": _payload(variant_result),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
    return hashlib.sha256(raw).hexdigest()[:16]
