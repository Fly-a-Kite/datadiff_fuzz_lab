from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPORTS_DIR = PROJECT_ROOT / "reports"
BUGS_DIR = PROJECT_ROOT / "bugs"
RUNS_DIR = PROJECT_ROOT / "runs"
CORPUS_DIR = PROJECT_ROOT / "corpus"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def ensure_dirs() -> None:
    for p in [REPORTS_DIR, BUGS_DIR, RUNS_DIR, CORPUS_DIR, CORPUS_DIR / "seeds", CORPUS_DIR / "interesting"]:
        p.mkdir(parents=True, exist_ok=True)


def json_default(obj: Any) -> Any:
    if isinstance(obj, Path):
        return str(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def dump_json(data: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True, default=json_default), encoding="utf-8")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def append_jsonl(row: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, sort_keys=True, default=json_default) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def slugify(text: str, max_len: int = 80) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "-", text).strip("-")
    return text[:max_len] or "item"


def stable_float(value: Any) -> Any:
    if isinstance(value, float):
        if math.isnan(value):
            return {"__nan__": True}
        if math.isinf(value):
            return {"__inf__": 1 if value > 0 else -1}
    return value


def parse_duration(value: str | None) -> float | None:
    if value is None:
        return None
    text = value.strip().lower()
    if not text:
        raise ValueError("duration cannot be empty")
    match = re.fullmatch(r"(\d+(?:\.\d+)?)(s|m|h|d)?", text)
    if not match:
        raise ValueError(f"invalid duration: {value!r}; expected forms like 10s, 5m, 24h")
    amount = float(match.group(1))
    unit = match.group(2) or "s"
    scale = {"s": 1.0, "m": 60.0, "h": 3600.0, "d": 86400.0}[unit]
    duration_s = amount * scale
    if duration_s <= 0:
        raise ValueError("duration must be positive")
    return duration_s
