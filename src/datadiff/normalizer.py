from __future__ import annotations

import math
import unicodedata
from dataclasses import dataclass
from typing import Any

from datadiff.backends.base import BackendResult
from datadiff.dsl import Program


@dataclass(slots=True)
class NormalizedResult:
    backend: str
    status: str
    columns: list[str]
    rows: list[list[Any]]
    error_type: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "status": self.status,
            "columns": self.columns,
            "rows": self.rows,
            "error_type": self.error_type,
            "error": self.error,
        }


def _norm_value(v: Any) -> Any:
    try:
        import pandas as pd
        if pd.isna(v):
            # Distinguish NaN from None only when Python float says NaN.
            if isinstance(v, float) and math.isnan(v):
                return {"kind": "nan"}
            return None
    except Exception:
        pass
    if isinstance(v, float):
        if math.isnan(v):
            return {"kind": "nan"}
        if math.isinf(v):
            return {"kind": "inf", "sign": 1 if v > 0 else -1}
        if v.is_integer() and abs(v) < 2**53:
            return int(v)
        return round(v, 10)
    if isinstance(v, str):
        return unicodedata.normalize("NFC", v)
    if hasattr(v, "item"):
        try:
            return _norm_value(v.item())
        except Exception:
            pass
    return v


def _to_pandas(data: Any):
    import pandas as pd
    if data is None:
        return pd.DataFrame()
    # Polars can convert through Arrow, but that path may require optional
    # dependencies. For normalization, rows/columns are enough.
    if hasattr(data, "rows") and hasattr(data, "columns"):
        return pd.DataFrame(data.rows(named=True), columns=list(data.columns))
    if hasattr(data, "to_pandas"):
        return data.to_pandas()
    if hasattr(data, "to_pandas_dataframe"):
        return data.to_pandas_dataframe()
    return data


def normalize_result(result: BackendResult, program: Program, enable_normalizer: bool = True) -> NormalizedResult:
    if result.status != "ok":
        return NormalizedResult(
            backend=result.backend,
            status=result.status,
            columns=[],
            rows=[],
            error_type=result.error_type,
            error=result.error[:500],
        )
    try:
        df = _to_pandas(result.data)
        original_columns = [str(c) for c in list(df.columns)]
        columns = sorted(original_columns)
        rows: list[list[Any]] = []
        for _, row in df.iterrows():
            rows.append([_norm_value(row[c]) for c in columns])
        if enable_normalizer:
            # SQL/DataFrame backends differ on stable ordering for ties and on
            # whether intermediate order is observable. The default oracle is
            # bag-semantics; order-sensitive metamorphic checks should be tested
            # separately with explicit tie-breakers.
            rows = sorted(rows, key=lambda r: repr(r))
        return NormalizedResult(result.backend, "ok", columns=columns, rows=rows)
    except Exception as exc:  # noqa: BLE001
        return NormalizedResult(result.backend, "normalization_error", [], [], type(exc).__name__, str(exc)[:500])
