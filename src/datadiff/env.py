from __future__ import annotations

import platform
import sqlite3
import sys
from functools import lru_cache
from importlib import metadata


def package_version(name: str) -> str:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return "not-installed"


@lru_cache(maxsize=1)
def _collect_environment_cached() -> tuple[tuple[str, str], ...]:
    data = {
        "python": sys.version.replace("\n", " "),
        "platform": platform.platform(),
        "pandas": package_version("pandas"),
        "polars": package_version("polars"),
        "duckdb": package_version("duckdb"),
        "sqlite": sqlite3.sqlite_version,
        "datadiff_fuzz_lab": package_version("datadiff-fuzz-lab"),
    }
    return tuple(data.items())


def collect_environment() -> dict[str, str]:
    return dict(_collect_environment_cached())
