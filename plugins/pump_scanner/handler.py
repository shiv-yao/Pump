from __future__ import annotations

import time
from typing import Any

import httpx

from app.utils.loader import call


PUMP_API = "https://frontend-api.pump.fun/coins/latest"


def _f(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _i(x: Any, default: int = 0) -> int:
    try:
        return int(x)
    except Exception:
        return default


def _normalize_token(row: dict) -> dict:
    mint = row.get("mint") or row.get("address") or ""
    symbol = row.get("symbol") or ""
    name = row.get("name") or symbol or mint[:6]
    created_raw = row.get("created_timestamp") or row.get("created") or row.get("createdAt") or 0

    created_ts = _f(created_raw, 0.
