#!/usr/bin/env python3
"""Preflight checks for the DataFusion grouped top-k NULL sort-key issue."""

from __future__ import annotations

import datafusion
import pyarrow as pa
from datafusion import SessionContext


def _register(rows: list[tuple[str, int | None]]) -> SessionContext:
    ctx = SessionContext()
    batch = pa.RecordBatch.from_arrays(
        [
            pa.array([row[0] for row in rows], type=pa.string()),
            pa.array([row[1] for row in rows], type=pa.int64()),
        ],
        schema=pa.schema(
            [
                pa.field("g", pa.string(), nullable=True),
                pa.field("x", pa.int64(), nullable=True),
            ]
        ),
    )
    ctx.register_record_batches("t0", [[batch]])
    return ctx


def _rows(rows: list[tuple[str, int | None]], sql: str) -> list[tuple]:
    ctx = _register(rows)
    out = []
    for batch in ctx.sql(sql).collect():
        data = batch.to_pylist()
        for row in data:
            out.append(tuple(row.get(name) for name in batch.schema.names))
    return out


def main() -> int:
    base = (
        "SELECT g, MIN(x) AS min_x, MAX(x) AS max_x, "
        "SUM(x) AS sum_x, AVG(x) AS avg_x, COUNT(x) AS count_x "
        "FROM t0 GROUP BY g"
    )
    cases = [
        (
            "raw_null_sort_topk_control",
            [("a", None)],
            "SELECT x FROM t0 ORDER BY x ASC NULLS LAST LIMIT 20",
            1,
        ),
        (
            "null_group_key_nonnull_min_control",
            [(None, 5)],
            f"SELECT min_x FROM ({base}) q ORDER BY min_x ASC NULLS LAST LIMIT 20",
            1,
        ),
        (
            "single_null_control",
            [("a", None)],
            f"SELECT min_x FROM ({base}) q LIMIT 20",
            1,
        ),
        (
            "single_null_order_only",
            [("a", None)],
            f"SELECT min_x FROM ({base}) q ORDER BY min_x ASC NULLS LAST",
            1,
        ),
        (
            "single_null_topk_asc_last",
            [("a", None)],
            f"SELECT min_x FROM ({base}) q ORDER BY min_x ASC NULLS LAST LIMIT 20",
            1,
        ),
        (
            "single_null_topk_asc_default",
            [("a", None)],
            f"SELECT min_x FROM ({base}) q ORDER BY min_x ASC LIMIT 20",
            1,
        ),
        (
            "single_null_topk_asc_last_limit_one",
            [("a", None)],
            f"SELECT min_x FROM ({base}) q ORDER BY min_x ASC NULLS LAST LIMIT 1",
            1,
        ),
        (
            "single_null_topk_asc_first",
            [("a", None)],
            f"SELECT min_x FROM ({base}) q ORDER BY min_x ASC NULLS FIRST LIMIT 20",
            1,
        ),
        (
            "single_null_topk_desc_last",
            [("a", None)],
            f"SELECT min_x FROM ({base}) q ORDER BY min_x DESC NULLS LAST LIMIT 20",
            1,
        ),
        (
            "single_null_topk_desc_first",
            [("a", None)],
            f"SELECT min_x FROM ({base}) q ORDER BY min_x DESC NULLS FIRST LIMIT 20",
            1,
        ),
        (
            "mixed_null_and_value_topk",
            [("a", None), ("b", 5)],
            f"SELECT min_x FROM ({base}) q ORDER BY min_x ASC NULLS LAST LIMIT 20",
            2,
        ),
        (
            "single_null_max_desc_topk",
            [("a", None)],
            f"SELECT max_x FROM ({base}) q ORDER BY max_x DESC NULLS LAST LIMIT 20",
            1,
        ),
        (
            "mixed_null_and_value_max_desc_topk",
            [("a", None), ("b", 5)],
            f"SELECT max_x FROM ({base}) q ORDER BY max_x DESC NULLS LAST LIMIT 20",
            2,
        ),
        (
            "single_null_sum_asc_topk_control",
            [("a", None)],
            f"SELECT sum_x FROM ({base}) q ORDER BY sum_x ASC NULLS LAST LIMIT 20",
            1,
        ),
        (
            "single_null_avg_asc_topk_control",
            [("a", None)],
            f"SELECT avg_x FROM ({base}) q ORDER BY avg_x ASC NULLS LAST LIMIT 20",
            1,
        ),
        (
            "mixed_limit_one_expected_value_only",
            [("a", None), ("b", 5)],
            f"SELECT min_x FROM ({base}) q ORDER BY min_x ASC NULLS LAST LIMIT 1",
            1,
        ),
    ]

    print(f"datafusion={getattr(datafusion, '__version__', 'unknown')}")
    print(f"pyarrow={pa.__version__}")
    failed = []
    for name, input_rows, sql, expected_rows in cases:
        rows = _rows(input_rows, sql)
        status = "ok" if len(rows) == expected_rows else "FAIL"
        print(f"{status} {name}: expected_rows={expected_rows} actual_rows={len(rows)} rows={rows}")
        if status != "ok":
            failed.append(name)
    if failed:
        print("failing_cases=" + ",".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
