from __future__ import annotations

import time
from typing import Any

from app.state import state


def _safe_trim(key: str, max_len: int = 500) -> list:
    rows = state.setdefault(key, [])
    if not isinstance(rows, list):
        rows = list(rows)
        state[key] = rows
    if len(rows) > max_len:
        del rows[:-max_len]
    return rows


def log_event(tag: str, data: Any = None, level: str = "INFO") -> dict:
    """OpenAlice-style structured event log for every bot decision."""
    event = {
        "ts": int(time.time()),
        "level": level,
        "tag": tag,
        "data": data if data is not None else {},
    }

    events = _safe_trim("events", 800)
    events.append(event)
    _safe_trim("events", 800)

    logs = state.setdefault("logs", [])
    logs.append(f"[{tag}] {data}" if data is not None else f"[{tag}]")
    if len(logs) > 500:
        del logs[:-500]

    return event


def recent_events(limit: int = 80) -> list[dict]:
    return list(state.get("events", []) or [])[-limit:]
