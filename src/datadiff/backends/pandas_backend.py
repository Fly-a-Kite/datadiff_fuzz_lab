from __future__ import annotations

import time
from typing import Any

from datadiff.backends.base import Backend, BackendResult
from datadiff.dsl import Program, TableData


class PandasBackend(Backend):
    name = "pandas"

    def _to_df(self, table: TableData):
        import pandas as pd
        return pd.DataFrame(table.rows, columns=[c.name for c in table.columns])

    def run(self, tables: list[TableData], program: Program, timeout_s: float = 5.0) -> BackendResult:
        start = time.perf_counter()
        try:
            import pandas as pd  # noqa: F401
            df = self._to_df(tables[0])
            for op in program.operations:
                kind = op["op"]
                if kind == "filter":
                    col = op["column"]
                    val = op["value"]
                    cmp = op["cmp"]
                    series = df[col]
                    if cmp == ">": mask = series > val
                    elif cmp == ">=": mask = series >= val
                    elif cmp == "<": mask = series < val
                    elif cmp == "<=": mask = series <= val
                    elif cmp == "==": mask = series == val
                    elif cmp == "!=": mask = series != val
                    else: raise ValueError(cmp)
                    df = df[mask.fillna(False)]
                elif kind == "select":
                    df = df[list(op["columns"])]
                elif kind == "sort":
                    df = df.sort_values(list(op["columns"]), ascending=bool(op["ascending"]), na_position="last", kind="mergesort")
                elif kind == "limit":
                    df = df.head(int(op["n"]))
                elif kind == "mutate":
                    expr = op["expr"]
                    if expr["kind"] == "add_const":
                        df = df.copy()
                        df[op["column"]] = df[expr["source"]] + expr["value"]
                    else:
                        raise ValueError(expr["kind"])
                elif kind == "groupby":
                    keys = list(op["keys"])
                    agg = op["aggs"][0]
                    col, func, alias = agg["column"], agg["func"], agg["as"]
                    if func == "count":
                        out = df.groupby(keys, dropna=False, sort=False)[col].count().reset_index(name=alias)
                    else:
                        out = getattr(df.groupby(keys, dropna=False, sort=False)[col], func)().reset_index(name=alias)
                    df = out
                else:
                    raise ValueError(kind)
            return BackendResult(self.name, "ok", data=df, duration_ms=(time.perf_counter()-start)*1000)
        except Exception as exc:  # noqa: BLE001
            return BackendResult(self.name, "error", error_type=type(exc).__name__, error=str(exc), duration_ms=(time.perf_counter()-start)*1000)
