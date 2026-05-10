from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from datadiff.dsl import Program, TableData


@dataclass(slots=True)
class BackendResult:
    backend: str
    status: str  # ok / error / timeout / missing
    data: Any = None
    error_type: str = ""
    error: str = ""
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Backend:
    name = "base"

    def run(self, tables: list[TableData], program: Program, timeout_s: float = 5.0) -> BackendResult:
        raise NotImplementedError
