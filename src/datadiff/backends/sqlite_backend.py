from __future__ import annotations

import sqlite3
import time
from typing import Any

from datadiff.backends.base import Backend, BackendResult
from datadiff.dsl import Program, TableData


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _lit(value: Any) -> str:
    import math

    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value):
            return "NULL"
        if math.isinf(value):
            return "1e999" if value > 0 else "-1e999"
        return repr(value)
    return "'" + str(value).replace("'", "''") + "'"


def _sql_type(kind: str) -> str:
    if kind == "int":
        return "INTEGER"
    if kind == "float":
        return "REAL"
    if kind == "bool":
        return "INTEGER"
    return "TEXT"


class SQLiteBackend(Backend):
    name = "sqlite"

    def run(self, tables: list[TableData], program: Program, timeout_s: float = 5.0) -> BackendResult:
        start = time.perf_counter()
        try:
            import pandas as pd

            table = tables[0]
            column_types = {c.name: c.type for c in table.columns}
            con = sqlite3.connect(":memory:")
            col_defs = ", ".join(f"{_quote(c.name)} {_sql_type(c.type)}" for c in table.columns)
            con.execute(f"CREATE TABLE t0 ({col_defs})")
            if table.rows:
                cols = [c.name for c in table.columns]
                placeholders = ", ".join("?" for _ in cols)
                con.executemany(
                    f"INSERT INTO t0 ({', '.join(_quote(c) for c in cols)}) VALUES ({placeholders})",
                    [[row.get(c) for c in cols] for row in table.rows],
                )
            query = "SELECT * FROM t0"
            for op in program.operations:
                kind = op["op"]
                if kind == "filter":
                    query = (
                        f"SELECT * FROM ({query}) q "
                        f"WHERE {_quote(op['column'])} {op['cmp']} {_lit(op['value'])}"
                    )
                elif kind == "select":
                    cols = ", ".join(_quote(c) for c in op["columns"])
                    query = f"SELECT {cols} FROM ({query}) q"
                elif kind == "sort":
                    # SQLite sorts NULLs first for ASC. Use an explicit null
                    # discriminator to match the common subset used by the
                    # other backends: NULLS LAST.
                    order_parts = []
                    for c in op["columns"]:
                        q = _quote(c)
                        order_parts.append(f"({q} IS NULL) ASC")
                        order_parts.append(f"{q} {'ASC' if op['ascending'] else 'DESC'}")
                    query = f"SELECT * FROM ({query}) q ORDER BY {', '.join(order_parts)}"
                elif kind == "limit":
                    query = f"SELECT * FROM ({query}) q LIMIT {int(op['n'])}"
                elif kind == "mutate":
                    expr = op["expr"]
                    if expr["kind"] != "add_const":
                        raise ValueError(expr["kind"])
                    query = (
                        f"SELECT *, {_quote(expr['source'])} + {_lit(expr['value'])} "
                        f"AS {_quote(op['column'])} FROM ({query}) q"
                    )
                elif kind == "groupby":
                    keys = list(op["keys"])
                    agg = op["aggs"][0]
                    func = "COUNT" if agg["func"] == "count" else agg["func"].upper()
                    key_sql = ", ".join(_quote(k) for k in keys)
                    query = (
                        f"SELECT {key_sql}, {func}({_quote(agg['column'])}) AS {_quote(agg['as'])} "
                        f"FROM ({query}) q GROUP BY {key_sql}"
                    )
                else:
                    raise ValueError(kind)
            cur = con.execute(query)
            columns = [desc[0] for desc in cur.description]
            out = pd.DataFrame(cur.fetchall(), columns=columns)
            for col in out.columns:
                if column_types.get(str(col)) == "bool":
                    out[col] = out[col].map(lambda v: None if pd.isna(v) else bool(v))
            con.close()
            return BackendResult(self.name, "ok", data=out, duration_ms=(time.perf_counter() - start) * 1000)
        except Exception as exc:  # noqa: BLE001
            return BackendResult(
                self.name,
                "error",
                error_type=type(exc).__name__,
                error=str(exc),
                duration_ms=(time.perf_counter() - start) * 1000,
            )
