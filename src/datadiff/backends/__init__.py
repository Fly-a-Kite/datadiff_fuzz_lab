from __future__ import annotations

from datadiff.backends.base import Backend
from datadiff.backends.duckdb_backend import DuckDBBackend
from datadiff.backends.pandas_backend import PandasBackend
from datadiff.backends.polars_backend import PolarsBackend
from datadiff.backends.sqlite_backend import SQLiteBackend


def make_backend(name: str) -> Backend:
    if name == "pandas":
        return PandasBackend()
    if name == "polars":
        return PolarsBackend()
    if name == "duckdb":
        return DuckDBBackend()
    if name == "sqlite":
        return SQLiteBackend()
    raise ValueError(f"unknown backend: {name}")
