from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

ColumnType = Literal["int", "float", "bool", "str"]
Value = Any


@dataclass(slots=True)
class ColumnSpec:
    name: str
    type: ColumnType
    nullable: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ColumnSpec":
        return cls(**data)


@dataclass(slots=True)
class TableData:
    name: str
    columns: list[ColumnSpec]
    rows: list[dict[str, Value]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "columns": [c.to_dict() for c in self.columns],
            "rows": self.rows,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TableData":
        return cls(
            name=data["name"],
            columns=[ColumnSpec.from_dict(c) for c in data["columns"]],
            rows=data["rows"],
        )

    def column_type(self, name: str) -> ColumnType:
        for c in self.columns:
            if c.name == name:
                return c.type
        raise KeyError(name)

    def numeric_columns(self) -> list[str]:
        return [c.name for c in self.columns if c.type in {"int", "float"}]

    def comparable_columns(self) -> list[str]:
        return [c.name for c in self.columns if c.type in {"int", "float", "str", "bool"}]


@dataclass(slots=True)
class Program:
    program_id: str
    seed: int
    operations: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Program":
        return cls(**data)

    @property
    def order_sensitive(self) -> bool:
        return bool(self.operations and self.operations[-1].get("op") == "sort")

    def op_sequence(self) -> list[str]:
        return [str(op.get("op", "unknown")) for op in self.operations]


@dataclass(slots=True)
class Case:
    case_id: str
    seed: int
    tables: list[TableData]
    program: Program

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "seed": self.seed,
            "tables": [t.to_dict() for t in self.tables],
            "program": self.program.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Case":
        return cls(
            case_id=data["case_id"],
            seed=data["seed"],
            tables=[TableData.from_dict(t) for t in data["tables"]],
            program=Program.from_dict(data["program"]),
        )
