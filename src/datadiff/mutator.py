from __future__ import annotations

import copy
import math
import random
from typing import Any

from datadiff.datagen import repair_operations
from datadiff.dsl import Case, Program, TableData


def mutate_case(case: Case, seed: int) -> Case:
    rnd = random.Random(seed * 104729 + case.seed)
    table = copy.deepcopy(case.tables[0])
    operations = copy.deepcopy(case.program.operations)
    choice = rnd.choice(["value", "append_op", "drop_op", "tweak_op"])

    if choice == "value":
        _mutate_value(table, rnd)
    elif choice == "append_op":
        op = _random_operation(table, operations, rnd)
        if op is not None:
            operations.append(op)
    elif choice == "drop_op" and len(operations) > 1:
        del operations[rnd.randrange(len(operations))]
    elif choice == "tweak_op" and operations:
        _tweak_operation(table, operations[rnd.randrange(len(operations))], rnd)

    operations = repair_operations(table, operations)
    if not operations:
        operations = [{"op": "limit", "n": len(table.rows)}]
    program = Program(
        program_id=f"{case.program.program_id}-mut-{seed}",
        seed=seed,
        operations=operations,
    )
    return Case(
        case_id=f"{case.case_id}-mut-{seed}",
        seed=seed,
        tables=[table],
        program=program,
    )


def _mutate_value(table: TableData, rnd: random.Random) -> None:
    if not table.rows:
        return
    col = rnd.choice(table.columns)
    row = rnd.choice(table.rows)
    current = row.get(col.name)
    if current is None:
        row[col.name] = _literal_for_type(col.type, rnd)
        return
    if col.type == "int":
        row[col.name] = int(current) + rnd.choice([-10, -1, 0, 1, 10])
    elif col.type == "float":
        if isinstance(current, float) and (math.isnan(current) or math.isinf(current)):
            row[col.name] = 0.0
        else:
            row[col.name] = float(current) + rnd.choice([-1.0, -0.5, 0.5, 1.0])
    elif col.type == "bool":
        row[col.name] = not bool(current)
    elif col.type == "str":
        row[col.name] = rnd.choice(["", "alpha", "ALPHA", "中文", str(current) + "_x"])


def _random_operation(table: TableData, operations: list[dict[str, Any]], rnd: random.Random) -> dict[str, Any] | None:
    available = _available_columns(table, operations)
    if not available:
        return None
    numeric = [c for c in available if _column_type(table, c) in {"int", "float"} or c.startswith(("m_", "sum_", "min_", "max_", "count_"))]
    choices = ["filter", "select", "sort", "limit"]
    if numeric:
        choices.extend(["mutate", "groupby"])
    kind = rnd.choice(choices)
    if kind == "filter":
        col = rnd.choice(available)
        typ = _column_type(table, col)
        cmp = rnd.choice(["==", "!="] if typ in {"str", "bool"} else [">", ">=", "<", "<=", "==", "!="])
        return {"op": "filter", "column": col, "cmp": cmp, "value": _literal_for_type(typ, rnd)}
    if kind == "select":
        count = rnd.randint(1, len(available))
        return {"op": "select", "columns": sorted(rnd.sample(available, count))}
    if kind == "sort":
        first = rnd.choice(available)
        cols = [first] + sorted(c for c in available if c != first)
        return {"op": "sort", "columns": cols, "ascending": rnd.choice([True, False])}
    if kind == "limit":
        return {"op": "limit", "n": rnd.randint(0, max(1, len(table.rows) + 3))}
    if kind == "mutate" and numeric:
        src = rnd.choice(numeric)
        return {
            "op": "mutate",
            "column": f"m_{len([o for o in operations if o.get('op') == 'mutate'])}",
            "expr": {"kind": "add_const", "source": src, "value": rnd.choice([-10, -1, 0, 1, 10])},
        }
    if kind == "groupby" and numeric:
        keys = [rnd.choice(available)]
        val = rnd.choice(numeric)
        func = rnd.choice(["sum", "min", "max", "count"])
        return {"op": "groupby", "keys": keys, "aggs": [{"column": val, "func": func, "as": f"{func}_{val}"}]}
    return None


def _tweak_operation(table: TableData, op: dict[str, Any], rnd: random.Random) -> None:
    kind = op.get("op")
    if kind == "filter":
        op["cmp"] = rnd.choice([">", ">=", "<", "<=", "==", "!="])
        op["value"] = _literal_for_type(_column_type(table, op["column"]), rnd)
    elif kind == "sort":
        op["ascending"] = not bool(op.get("ascending", True))
    elif kind == "limit":
        op["n"] = max(0, int(op.get("n", 0)) + rnd.choice([-2, -1, 1, 2]))
    elif kind == "mutate":
        op["expr"]["value"] = op["expr"].get("value", 0) + rnd.choice([-2, -1, 1, 2])


def _available_columns(table: TableData, operations: list[dict[str, Any]]) -> list[str]:
    available = [c.name for c in table.columns]
    for op in operations:
        if op.get("op") == "select":
            available = [c for c in op.get("columns", []) if c in available]
        elif op.get("op") == "mutate":
            available.append(op["column"])
        elif op.get("op") == "groupby":
            available = list(op.get("keys", [])) + [agg["as"] for agg in op.get("aggs", [])]
    return available


def _column_type(table: TableData, name: str) -> str:
    for col in table.columns:
        if col.name == name:
            return col.type
    return "float" if name.startswith(("m_", "sum_", "min_", "max_")) else "int"


def _literal_for_type(typ: str, rnd: random.Random) -> Any:
    if typ == "int":
        return rnd.choice([-10, -1, 0, 1, 2, 10])
    if typ == "float":
        return rnd.choice([-1.0, 0.0, 0.5, 1.0, 10.0])
    if typ == "bool":
        return rnd.choice([True, False])
    return rnd.choice(["", "alpha", "beta", "中文", "missing"])
