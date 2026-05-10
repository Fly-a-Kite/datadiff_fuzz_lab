from __future__ import annotations

import math
import random
import string
from typing import Any, Literal

from .dsl import Case, ColumnSpec, Program, TableData

GeneratorProfile = Literal["common", "edge_float"]


def _rand_str(rnd: random.Random) -> str | None:
    choices = ["", "alpha", "beta", "gamma", "δelta", "中文", "space value", "A", "a"]
    if rnd.random() < 0.7:
        return rnd.choice(choices)
    return "".join(rnd.choice(string.ascii_letters) for _ in range(rnd.randint(1, 8)))


def _value_for_type(
    rnd: random.Random,
    typ: str,
    nullable: bool = True,
    profile: GeneratorProfile = "common",
) -> Any:
    if nullable and rnd.random() < 0.18:
        return None
    if typ == "int":
        return rnd.choice([0, 1, -1, 2, -2, 10, -10, rnd.randint(-100, 100)])
    if typ == "float":
        if profile == "edge_float":
            special = rnd.random()
            if special < 0.05:
                return float("nan")
            if special < 0.08:
                return float("inf")
            if special < 0.11:
                return float("-inf")
        # The common profile targets a stable subset. NaN/Infinity are valuable,
        # but they belong in edge_float experiments because engines intentionally
        # disagree on their comparison semantics.
        return rnd.choice([0.0, 1.0, -1.0, 0.5, -0.5, round(rnd.uniform(-50, 50), 3)])
    if typ == "bool":
        return rnd.choice([True, False])
    if typ == "str":
        return _rand_str(rnd)
    raise ValueError(typ)


def generate_table(
    seed: int,
    name: str = "t0",
    min_rows: int = 0,
    max_rows: int = 20,
    profile: GeneratorProfile = "common",
) -> TableData:
    rnd = random.Random(seed)
    base_cols = [
        ColumnSpec("id", "int", nullable=False),
        ColumnSpec("g", "str", nullable=True),
        ColumnSpec("x", "int", nullable=True),
        ColumnSpec("y", "float", nullable=True),
        ColumnSpec("flag", "bool", nullable=True),
        ColumnSpec("s", "str", nullable=True),
    ]
    ncols = rnd.randint(3, len(base_cols))
    columns = base_cols[:ncols]
    nrows = rnd.randint(min_rows, max_rows)
    rows: list[dict[str, Any]] = []
    for i in range(nrows):
        row: dict[str, Any] = {}
        for col in columns:
            if col.name == "id":
                # Repeated IDs are useful for joins and group-like behavior.
                row[col.name] = rnd.choice([i, i % 5, 0, 1])
            else:
                row[col.name] = _value_for_type(rnd, col.type, col.nullable, profile=profile)
        rows.append(row)
    return TableData(name=name, columns=columns, rows=rows)


def _literal_for_column(rnd: random.Random, table: TableData, col: str) -> Any:
    typ = table.column_type(col)
    values = [r.get(col) for r in table.rows if r.get(col) is not None]
    if values and rnd.random() < 0.65:
        v = rnd.choice(values)
        # Avoid NaN as a comparison literal because NaN equality is intentionally special.
        if isinstance(v, float) and math.isnan(v):
            return 0.0
        return v
    if typ == "int":
        return rnd.choice([-10, -1, 0, 1, 2, 10])
    if typ == "float":
        return rnd.choice([-1.0, 0.0, 0.5, 1.0, 10.0])
    if typ == "bool":
        return rnd.choice([True, False])
    return rnd.choice(["", "alpha", "beta", "中文", "missing"])


def _literal_for_type(rnd: random.Random, typ: str) -> Any:
    if typ == "int":
        return rnd.choice([-10, -1, 0, 1, 2, 10])
    if typ == "float":
        return rnd.choice([-1.0, 0.0, 0.5, 1.0, 10.0])
    if typ == "bool":
        return rnd.choice([True, False])
    return rnd.choice(["", "alpha", "beta", "中文", "missing"])


def generate_program(seed: int, table: TableData, max_ops: int = 5, type_aware: bool = True) -> Program:
    rnd = random.Random(seed * 7919 + 17)
    ops: list[dict[str, Any]] = []
    available_cols = [c.name for c in table.columns]
    col_types = {c.name: c.type for c in table.columns}
    numeric_cols = table.numeric_columns()
    comparable_cols = table.comparable_columns()

    op_pool = ["filter", "select", "sort", "limit", "mutate", "groupby"]
    nops = rnd.randint(1, max_ops)
    grouped = False

    for _ in range(nops):
        if not type_aware:
            ops.append(_generate_type_oblivious_operation(rnd, table, available_cols))
            continue

        possible = list(op_pool)
        if grouped:
            possible = ["sort", "limit", "select"]
        op = rnd.choice(possible)

        if op == "filter" and comparable_cols and not grouped:
            col = rnd.choice(comparable_cols)
            typ = col_types[col]
            cmp_ops = ["==", "!="] if typ in {"str", "bool"} else [">", ">=", "<", "<=", "==", "!="]
            base_cols = {c.name for c in table.columns}
            value = _literal_for_column(rnd, table, col) if col in base_cols else _literal_for_type(rnd, typ)
            ops.append({"op": "filter", "column": col, "cmp": rnd.choice(cmp_ops), "value": value})

        elif op == "select" and available_cols:
            k = rnd.randint(1, len(available_cols))
            cols = sorted(rnd.sample(available_cols, k))
            ops.append({"op": "select", "columns": cols})
            available_cols = cols
            numeric_cols = [c for c in numeric_cols if c in available_cols]
            comparable_cols = [c for c in comparable_cols if c in available_cols]

        elif op == "sort" and available_cols:
            first = rnd.choice(available_cols)
            cols = [first] + sorted(c for c in available_cols if c != first)
            ops.append({"op": "sort", "columns": cols, "ascending": rnd.choice([True, False])})

        elif op == "limit":
            ops.append({"op": "limit", "n": rnd.randint(0, max(1, len(table.rows) + 2))})

        elif op == "mutate" and numeric_cols and not grouped:
            src = rnd.choice(numeric_cols)
            new_col = f"m_{len([o for o in ops if o.get('op') == 'mutate'])}"
            const = rnd.choice([-2, -1, 0, 1, 2, 10])
            ops.append({"op": "mutate", "column": new_col, "expr": {"kind": "add_const", "source": src, "value": const}})
            available_cols.append(new_col)
            col_types[new_col] = col_types[src]
            numeric_cols.append(new_col)
            comparable_cols.append(new_col)

        elif op == "groupby" and numeric_cols and available_cols and not grouped:
            keys = [rnd.choice(available_cols)]
            # Avoid grouping by float columns for common-subset stability.
            key_candidates = [c.name for c in table.columns if c.name in available_cols and c.type in {"int", "str", "bool"}]
            if key_candidates:
                keys = [rnd.choice(key_candidates)]
            val = rnd.choice(numeric_cols)
            func = rnd.choice(["sum", "min", "max", "count"])
            alias = f"{func}_{val}"
            ops.append({"op": "groupby", "keys": keys, "aggs": [{"column": val, "func": func, "as": alias}]})
            available_cols = keys + [alias]
            numeric_cols = [alias]
            comparable_cols = available_cols
            grouped = True

    if type_aware:
        ops = repair_operations(table, ops)
    if not ops:
        ops.append({"op": "limit", "n": len(table.rows)})
    return Program(program_id=f"prog-{seed:08d}", seed=seed, operations=ops)


def _generate_type_oblivious_operation(
    rnd: random.Random,
    table: TableData,
    available_cols: list[str],
) -> dict[str, Any]:
    col = rnd.choice(available_cols)
    kind = rnd.choice(["filter", "select", "sort", "limit", "mutate", "groupby"])
    if kind == "filter":
        return {
            "op": "filter",
            "column": col,
            "cmp": rnd.choice([">", ">=", "<", "<=", "==", "!="]),
            "value": rnd.choice([None, -1, 0, 1, 0.5, True, False, "alpha", "missing"]),
        }
    if kind == "select":
        return {"op": "select", "columns": sorted(rnd.sample(available_cols, rnd.randint(1, len(available_cols))))}
    if kind == "sort":
        cols = [col] + sorted(c for c in available_cols if c != col)
        return {"op": "sort", "columns": cols, "ascending": rnd.choice([True, False])}
    if kind == "limit":
        return {"op": "limit", "n": rnd.randint(0, max(1, len(table.rows) + 2))}
    if kind == "mutate":
        return {
            "op": "mutate",
            "column": f"u_{rnd.randint(0, 9)}",
            "expr": {"kind": "add_const", "source": col, "value": rnd.choice([-1, 0, 1])},
        }
    numeric_cols = table.numeric_columns()
    agg_col = rnd.choice(numeric_cols or available_cols)
    func = rnd.choice(["sum", "min", "max", "count"])
    return {"op": "groupby", "keys": [col], "aggs": [{"column": agg_col, "func": func, "as": f"{func}_{agg_col}"}]}


def repair_operations(table: TableData, ops: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep generated programs inside the common semantic subset.

    This is a guardrail for paper-quality experiments: invalid generated
    programs mostly measure generator bugs and backend error-message variance.
    """

    repaired: list[dict[str, Any]] = []
    available = {c.name for c in table.columns}
    col_types = {c.name: c.type for c in table.columns}
    numeric = {c.name for c in table.columns if c.type in {"int", "float"}}
    grouped = False
    for op in ops:
        kind = op["op"]
        if kind == "filter":
            if grouped or op["column"] not in available:
                continue
            repaired.append(op)
        elif kind == "select":
            cols = [c for c in op["columns"] if c in available]
            if not cols:
                continue
            repaired.append({"op": "select", "columns": cols})
            available = set(cols)
            numeric &= available
        elif kind == "sort":
            cols = [c for c in op["columns"] if c in available]
            if cols:
                full_cols = cols + sorted(c for c in available if c not in cols)
                repaired.append({**op, "columns": full_cols})
        elif kind == "limit":
            if repaired and repaired[-1].get("op") == "sort":
                repaired.append(op)
            break
        elif kind == "mutate":
            expr = op["expr"]
            src = expr.get("source")
            if grouped or src not in available or src not in numeric:
                continue
            repaired.append(op)
            available.add(op["column"])
            numeric.add(op["column"])
            col_types[op["column"]] = col_types[src]
        elif kind == "groupby":
            if grouped:
                continue
            keys = [k for k in op["keys"] if k in available]
            aggs = [a for a in op["aggs"] if a["column"] in available and a["column"] in numeric]
            if not keys or not aggs:
                continue
            repaired.append({**op, "keys": keys, "aggs": aggs})
            available = set(keys) | {a["as"] for a in aggs}
            numeric = {a["as"] for a in aggs}
            grouped = True
    return repaired


def generate_case(seed: int, type_aware: bool = True, profile: GeneratorProfile = "common") -> Case:
    table = generate_table(seed, name="t0", profile=profile)
    program = generate_program(seed, table, type_aware=type_aware)
    return Case(case_id=f"case-{seed:08d}", seed=seed, tables=[table], program=program)
