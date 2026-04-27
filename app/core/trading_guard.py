from __future__ import annotations

import os
import time
from typing import Any

from app.state import state
from app.core.event_log import log_event


def _f(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _i(x: Any, default: int = 0) -> int:
    try:
        return int(float(x))
    except Exception:
        return default


def _b(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).lower() in {"1", "true", "yes", "on"}


def guard_trade(payload: dict, candidate: dict | None = None) -> tuple[bool, str, dict]:
    """OpenAlice-style guard pipeline before any trade_order call."""
    checks: list[dict] = []
    candidate = candidate or {}

    if state.get("kill"):
        return False, "killswitch", {"checks": [{"name": "killswitch", "ok": False}]}

    size = _f(payload.get("size") or payload.get("amount"), 0.0)
    max_size = _f(os.getenv("MAX_POSITION_PER_TRADE", os.getenv("MAX_POSITION_SOL", "0.01")), 0.01)
    ok_size = 0 < size <= max_size
    checks.append({"name": "max_position_per_trade", "ok": ok_size, "size": size, "limit": max_size})
    if not ok_size:
        return False, f"size_too_big:{size}>{max_size}", {"checks": checks}

    positions = state.get("positions", []) or []
    max_positions = _i(os.getenv("MAX_OPEN_POSITIONS", "5"), 5)
    ok_positions = len(positions) < max_positions
    checks.append({"name": "max_open_positions", "ok": ok_positions, "count": len(positions), "limit": max_positions})
    if not ok_positions:
        return False, "max_open_positions", {"checks": checks}

    exposure = _f(state.get("total_exposure", 0.0), 0.0)
    max_exposure = _f(os.getenv("MAX_TOTAL_EXPOSURE", "0.05"), 0.05)
    ok_exposure = exposure + size <= max_exposure
    checks.append({"name": "max_total_exposure", "ok": ok_exposure, "current": exposure, "add": size, "limit": max_exposure})
    if not ok_exposure:
        return False, "max_total_exposure", {"checks": checks}

    daily_pnl = _f(state.get("daily_pnl", 0.0), 0.0)
    daily_loss_limit = _f(os.getenv("MAX_DAILY_LOSS", "0.03"), 0.03)
    ok_daily = daily_pnl > -abs(daily_loss_limit)
    checks.append({"name": "max_daily_loss", "ok": ok_daily, "daily_pnl": daily_pnl, "limit": -abs(daily_loss_limit)})
    if not ok_daily:
        return False, "max_daily_loss", {"checks": checks}

    consec_loss = _i(state.get("consecutive_loss", 0), 0)
    max_consec = _i(os.getenv("MAX_CONSEC_LOSS", "3"), 3)
    ok_consec = consec_loss < max_consec
    checks.append({"name": "max_consecutive_loss", "ok": ok_consec, "count": consec_loss, "limit": max_consec})
    if not ok_consec:
        return False, "max_consecutive_loss", {"checks": checks}

    mint = payload.get("symbol") or payload.get("mint") or candidate.get("mint")
    cooldown_sec = _i(os.getenv("TOKEN_COOLDOWN_SEC", "120"), 120)
    now = int(time.time())
    cooldowns = state.setdefault("token_cooldowns", {})
    last = _i(cooldowns.get(str(mint), 0), 0) if mint else 0
    ok_cooldown = not mint or now - last >= cooldown_sec
    checks.append({"name": "token_cooldown", "ok": ok_cooldown, "mint": mint, "elapsed": now - last if last else None, "limit_sec": cooldown_sec})
    if not ok_cooldown:
        return False, "token_cooldown", {"checks": checks}

    whitelist = [x.strip() for x in os.getenv("TOKEN_WHITELIST", "").split(",") if x.strip()]
    blacklist = [x.strip() for x in os.getenv("TOKEN_BLACKLIST", "").split(",") if x.strip()]
    if blacklist and mint in blacklist:
        checks.append({"name": "blacklist", "ok": False, "mint": mint})
        return False, "blacklisted_token", {"checks": checks}
    if whitelist and mint not in whitelist:
        checks.append({"name": "whitelist", "ok": False, "mint": mint})
        return False, "not_whitelisted", {"checks": checks}

    log_event("GUARD_PASS", {"mint": mint, "checks": checks})
    return True, "ok", {"checks": checks}


def mark_trade_attempt(mint: str | None):
    if mint:
        state.setdefault("token_cooldowns", {})[str(mint)] = int(time.time())
