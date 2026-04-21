from __future__ import annotations

from decimal import Decimal, getcontext
from pathlib import Path

from models import HedgeInception

getcontext().prec = 28

_HEDGES_DIR: Path = Path(__file__).parent / "hedges"


def save_hedge(hedge: HedgeInception) -> Path:
    _HEDGES_DIR.mkdir(exist_ok=True)
    path = _HEDGES_DIR / f"{hedge.hedge_id}.json"
    # mode="json" serializes Decimal as string, date as ISO-8601
    path.write_text(
        hedge.model_dump_json(indent=2),
        encoding="utf-8",
    )
    return path


def load_hedge(hedge_id: str) -> HedgeInception:
    path = _HEDGES_DIR / f"{hedge_id}.json"
    return HedgeInception.model_validate_json(path.read_text(encoding="utf-8"))


def list_hedges() -> list[str]:
    if not _HEDGES_DIR.exists():
        return []
    return [p.stem for p in sorted(_HEDGES_DIR.glob("*.json"))]
