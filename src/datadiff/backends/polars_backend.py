from __future__ import annotations

import time

from datadiff.backends.base import Backend, BackendResult
from datadiff.dsl import Program, TableData


class PolarsBackend(Backend):
    name = "polars"

    def _to_df(self, table: TableData):
        import polars as pl
        data = {c.name: [row.get(c.name) for row in table.rows] for c in table.columns}
        return pl.DataFrame(data)

    def run(self, tables: list[TableData], program: Program, timeout_s: float = 5.0) -> BackendResult:
        start = time.perf_counter()
        try:
            import polars as pl
            df = self._to_df(tables[0])
            for op in program.operations:
                kind = op["op"]
                if kind == "filter":
                    col = pl.col(op["column"])
                    val = op["value"]
                    cmp = op["cmp"]
                    if cmp == ">": expr = col > val
                    elif cmp == ">=": expr = col >= val
                    elif cmp == "<": expr = col < val
                    elif cmp == "<=": expr = col <= val
                    elif cmp == "==": expr = col == val
                    elif cmp == "!=": expr = col != val
                    else: raise ValueError(cmp)
                    df = df.filter(expr.fill_null(False))
                elif kind == "select":
                    df = df.select(list(op["columns"]))
                elif kind == "sort":
                    df = df.sort(list(op["columns"]), descending=not bool(op["ascending"]), nulls_last=True)
                elif kind == "limit":
                    df = df.head(int(op["n"]))
                elif kind == "mutate":
                    expr = op["expr"]
                    if expr["kind"] == "add_const":
                        df = df.with_columns((pl.col(expr["source"]) + expr["value"]).alias(op["column"]))
                    else:
                        raise ValueError(expr["kind"])
                elif kind == "groupby":
                    keys = list(op["keys"])
                    agg = op["aggs"][0]
                    col, func, alias = agg["column"], agg["func"], agg["as"]
                    if func == "count":
                        df = df.group_by(keys, maintain_order=True).agg(pl.col(col).count().alias(alias))
                    elif func == "sum":
                        df = df.group_by(keys, maintain_order=True).agg(
                            pl.when(pl.col(col).count() == 0)
                            .then(None)
                            .otherwise(pl.col(col).sum())
                            .alias(alias)
                        )
                    else:
                        df = df.group_by(keys, maintain_order=True).agg(getattr(pl.col(col), func)().alias(alias))
                else:
                    raise ValueError(kind)
            return BackendResult(self.name, "ok", data=df, duration_ms=(time.perf_counter()-start)*1000)
        except Exception as exc:  # noqa: BLE001
            return BackendResult(self.name, "error", error_type=type(exc).__name__, error=str(exc), duration_ms=(time.perf_counter()-start)*1000)
