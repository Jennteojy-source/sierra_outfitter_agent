"""Mock conversation ratings store (in-memory + local JSON)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RATINGS_PATH = DATA_DIR / "ratings.json"

_ratings: list[dict[str, Any]] = []
_loaded = False


def _load() -> None:
    global _ratings, _loaded
    if _loaded:
        return
    if RATINGS_PATH.is_file():
        try:
            data = json.loads(RATINGS_PATH.read_text())
            if isinstance(data, list):
                _ratings = data
        except json.JSONDecodeError:
            _ratings = []
    _loaded = True


def save_rating(record: dict[str, Any]) -> dict[str, Any]:
    _load()
    row = {
        **record,
        "created_at": record.get("created_at")
        or datetime.now(timezone.utc).isoformat(),
    }
    _ratings.append(row)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RATINGS_PATH.write_text(json.dumps(_ratings, indent=2))
    return row


def all_ratings() -> list[dict[str, Any]]:
    _load()
    return list(_ratings)
