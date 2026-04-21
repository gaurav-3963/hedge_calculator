from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Any

from models import LogRow

getcontext().prec = 28

_LOGS_DIR: Path = Path(__file__).parent / "logs"


def _to_serializable(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _to_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_serializable(item) for item in obj]
    return obj


def append_log(hedge_id: str, row: LogRow) -> None:
    _LOGS_DIR.mkdir(exist_ok=True)
    path = _LOGS_DIR / f"hedge_{hedge_id}.jsonl"
    data = _to_serializable(row.model_dump())
    data["schema_version"] = "1.0"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(data, ensure_ascii=False))
        fh.write("\n")
        fh.flush()


def read_logs(hedge_id: str) -> list[LogRow]:
    path = _LOGS_DIR / f"hedge_{hedge_id}.jsonl"
    if not path.exists():
        return []
    rows: list[LogRow] = []
    with path.open(encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            data = json.loads(raw)
            data.pop("schema_version", None)
            rows.append(LogRow.model_validate(data))
    return rows
