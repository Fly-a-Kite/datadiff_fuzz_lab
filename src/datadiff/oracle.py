from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any

from datadiff.dsl import Case
from datadiff.normalizer import NormalizedResult


@dataclass(slots=True)
class Finding:
    finding_id: str
    kind: str
    severity: str
    suspicious_backends: list[str]
    evidence: str
    signature: str
    root_cause: str = "unknown"
    oracle: str = "differential"
    confidence: str = "medium"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _payload(norm: NormalizedResult) -> dict[str, Any]:
    return {
        "status": norm.status,
        "columns": norm.columns,
        "rows": norm.rows,
        "error_type": norm.error_type,
    }


def _signature(case: Case, normalized: dict[str, NormalizedResult], kind: str) -> str:
    payload = {
        "kind": kind,
        "ops": case.program.op_sequence(),
        "results": {k: _payload(v) for k, v in sorted(normalized.items())},
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
    return hashlib.sha256(raw).hexdigest()[:16]


def classify_root_cause(case: Case, normalized: dict[str, NormalizedResult], kind: str) -> str:
    ops = case.program.op_sequence()
    if kind == "exception_mismatch":
        return "exception_taxonomy"
    if any(op == "groupby" for op in ops):
        return "groupby_aggregation"
    if any(op == "filter" for op in ops):
        return "filter_predicate"
    if any(op == "mutate" for op in ops):
        return "arithmetic_expression"
    if any(op in {"sort", "limit"} for op in ops):
        return "ordering_or_limit"
    ok_results = [r for r in normalized.values() if r.status == "ok"]
    if ok_results and len({tuple(r.columns) for r in ok_results}) > 1:
        return "schema_projection"
    if _case_contains_special_float(case):
        return "nan_inf_semantics"
    if _case_contains_null(case):
        return "null_semantics"
    return "unknown"


def _case_contains_null(case: Case) -> bool:
    for table in case.tables:
        for row in table.rows:
            if any(v is None for v in row.values()):
                return True
    return False


def _case_contains_special_float(case: Case) -> bool:
    import math

    for table in case.tables:
        for row in table.rows:
            for value in row.values():
                if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
                    return True
    return False


def evaluate_case(case: Case, normalized: dict[str, NormalizedResult]) -> list[Finding]:
    findings: list[Finding] = []
    statuses = {b: r.status for b, r in normalized.items()}
    ok = {b: r for b, r in normalized.items() if r.status == "ok"}
    non_ok = {b: r for b, r in normalized.items() if r.status != "ok"}

    if ok and non_ok:
        sig = _signature(case, normalized, "accept_reject_mismatch")
        kind = "accept_reject_mismatch"
        findings.append(Finding(
            finding_id=f"finding-{sig}",
            kind=kind,
            severity="high",
            suspicious_backends=list(non_ok),
            evidence=f"Some backends accepted while others rejected: {statuses}",
            signature=sig,
            root_cause=classify_root_cause(case, normalized, kind),
            oracle="differential",
            confidence="high",
        ))
        return findings

    if len(non_ok) == len(normalized) and len(set((r.status, r.error_type) for r in non_ok.values())) > 1:
        sig = _signature(case, normalized, "exception_mismatch")
        kind = "exception_mismatch"
        findings.append(Finding(
            finding_id=f"finding-{sig}",
            kind=kind,
            severity="medium",
            suspicious_backends=list(non_ok),
            evidence=f"All backends rejected but with different errors: { {b: r.error_type for b, r in non_ok.items()} }",
            signature=sig,
            root_cause=classify_root_cause(case, normalized, kind),
            oracle="differential",
            confidence="medium",
        ))
        return findings

    if len(ok) >= 2:
        payloads = {b: _payload(r) for b, r in ok.items()}
        unique = {}
        for b, p in payloads.items():
            key = json.dumps(p, ensure_ascii=False, sort_keys=True)
            unique.setdefault(key, []).append(b)
        if len(unique) > 1:
            group_sizes = [len(group) for group in unique.values()]
            max_size = max(group_sizes)
            if group_sizes.count(max_size) > 1:
                suspicious = sorted(ok)
            else:
                largest_group = next(group for group in unique.values() if len(group) == max_size)
                suspicious = sorted(b for group in unique.values() if group is not largest_group for b in group)
            sig = _signature(case, normalized, "semantic_output_mismatch")
            kind = "semantic_output_mismatch"
            shapes = {b: (len(r.rows), len(r.columns)) for b, r in ok.items()}
            findings.append(Finding(
                finding_id=f"finding-{sig}",
                kind=kind,
                severity="critical",
                suspicious_backends=suspicious,
                evidence=f"Backends returned different canonical tables; shapes={shapes}",
                signature=sig,
                root_cause=classify_root_cause(case, normalized, kind),
                oracle="differential",
                confidence="high" if len(suspicious) < len(ok) else "medium",
            ))
    return findings
