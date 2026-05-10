from __future__ import annotations

import time

from datadiff.backends.base import Backend, BackendResult
from datadiff.dsl import Program, TableData


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _lit(value):
    import math
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value):
            return "'NaN'::DOUBLE"
        if math.isinf(value):
            return "'Infinity'::DOUBLE" if value > 0 else "'-Infinity'::DOUBLE"
        return repr(value)
    s = str(value).replace("'", "''")
    return f"'{s}'"


class DuckDBBackend(Backend):
    name = "duckdb"

    def run(self, tables: list[TableData], program: Program, timeout_s: float = 5.0) -> BackendResult:
        start = time.perf_counter()
        try:
            import duckdb
            import pandas as pd
            con = duckdb.connect(database=":memory:")
            df = pd.DataFrame(tables[0].rows, columns=[c.name for c in tables[0].columns])
            con.register("t0", df)
            select_cols = "*"
            source = "t0"
            order_clause = ""
            limit_clause = ""
            where_clauses: list[str] = []
            # For simplicity, materialize after each operation by creating a subquery.
            query = "SELECT * FROM t0"
            tmp_i = 0
            for op in program.operations:
                kind = op["op"]
                if kind == "filter":
                    cmp = op["cmp"]
                    col = _quote(op["column"])
                    query = f"SELECT * FROM ({query}) q WHERE {col} {cmp} {_lit(op['value'])}"
                elif kind == "select":
                    cols = ", ".join(_quote(c) for c in op["columns"])
                    query = f"SELECT {cols} FROM ({query}) q"
                elif kind == "sort":
                    cols = ", ".join(f"{_quote(c)} {'ASC' if op['ascending'] else 'DESC'} NULLS LAST" for c in op["columns"])
                    query = f"SELECT * FROM ({query}) q ORDER BY {cols}"
                elif kind == "limit":
                    query = f"SELECT * FROM ({query}) q LIMIT {int(op['n'])}"
                elif kind == "mutate":
                    expr = op["expr"]
                    if expr["kind"] == "add_const":
                        query = f"SELECT *, {_quote(expr['source'])} + {_lit(expr['value'])} AS {_quote(op['column'])} FROM ({query}) q"
                    else:
                        raise ValueError(expr["kind"])
                elif kind == "groupby":
                    keys = list(op["keys"])
                    agg = op["aggs"][0]
                    func = "COUNT" if agg["func"] == "count" else agg["func"].upper()
                    key_sql = ", ".join(_quote(k) for k in keys)
                    query = f"SELECT {key_sql}, {func}({_quote(agg['column'])}) AS {_quote(agg['as'])} FROM ({query}) q GROUP BY {key_sql}"
                else:
                    raise ValueError(kind)
                tmp_i += 1
            out = con.execute(query).df()
            con.close()
            return BackendResult(self.name, "ok", data=out, duration_ms=(time.perf_counter()-start)*1000)
        except Exception as exc:  # noqa: BLE001
            return BackendResult(self.name, "error", error_type=type(exc).__name__, error=str(exc), duration_ms=(time.perf_counter()-start)*1000)
