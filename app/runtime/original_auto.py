from __future__ import annotations

import asyncio
import os
import time
from typing import Any

from app.state import state
from app.utils.loader import call

TASK: asyncio.Task | None = None
PLUGIN_SNIPER_STARTED = False
SEEN_MINTS: set[str] = set()


def _b(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).lower() in {"1", "true", "yes", "on"}


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


def log_event(msg: str):
    print(msg)
    logs = state.setdefault("logs", [])
    logs.append(msg)
    if len(logs) > 300:
        del logs[:-300]


def _mode() -> str:
    return "REAL" if _b("REAL_TRADING", "false") else "PAPER"


def _trade_size() -> float:
    return _f(
        os.getenv("SNIPER_TRADE_SIZE_SOL")
        or os.getenv("MAX_POSITION_SOL")
        or os.getenv("MAX_POSITION_PER_TRADE")
        or "0.001",
        0.001,
    )


async def _start_existing_plugin_sniper_once():
    global PLUGIN_SNIPER_STARTED
    if PLUGIN_SNIPER_STARTED or not _b("START_PLUGIN_SNIPER", "true"):
        return
    res = await call("start_sniper", {"capital": _f(os.getenv("SNIPER_CAPITAL", "100"), 100)})
    PLUGIN_SNIPER_STARTED = True
    log_event(f"[AUTO] existing sniper plugin start: {res}")


async def _fetch_candidates() -> list[dict]:
    limit = _i(os.getenv("SNIPER_LIMIT", "10"), 10)
    max_age = _i(os.getenv("SNIPER_MAX_AGE_SEC", "180"), 180)

    res = await call("pump_candidates", {"limit": limit, "max_age_sec": max_age})
    if isinstance(res, dict) and not res.get("error"):
        candidates = res.get("candidates") or res.get("tokens") or res.get("results") or []
        if candidates:
            return [x for x in candidates if isinstance(x, dict)]

    # Fallback: use raw latest pump.fun rows if strict filters produce no result.
    latest = await call("pump_latest", {"limit": max(limit, 20)})
    if isinstance(latest, dict) and not latest.get("error"):
        rows = latest.get("tokens") or []
        out = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            age = _i(row.get("age_sec", 999999), 999999)
            if age > max_age:
                continue
            out.append({
                "mint": row.get("mint"),
                "symbol": row.get("symbol") or row.get("mint"),
                "name": row.get("name"),
                "age_sec": age,
                "alpha_score": 0.72 if age <= max_age else 0.0,
                "source": "pump_latest_fallback",
            })
        return out[:limit]

    log_event(f"[PUMP] no candidates: {res}")
    return []


async def _risk_and_alpha_ok(c: dict, size: float) -> tuple[bool, str, float]:
    mint = c.get("mint") or c.get("asset_id") or c.get("symbol")
    score = _f(c.get("alpha_score", c.get("score", 0.0)), 0.0)
    min_score = _f(os.getenv("SNIPER_MIN_SCORE", os.getenv("MIN_SCORE", "0.70")), 0.70)

    if not mint:
        return False, "missing_mint", score
    if score < min_score:
        return False, f"score_low:{score:.3f}<{min_score:.3f}", score

    rug = await call("rug_check", {"asset_id": mint, "symbol": mint})
    if isinstance(rug, dict) and not rug.get("error"):
        if rug.get("allowed") is False:
            return False, "rug_blocked", score
        if _f(rug.get("score", 0.0), 0.0) > _f(os.getenv("MAX_RUG_SCORE", "0.80"), 0.80):
            return False, "rug_score_high", score

    risk = await call("check_risk", {"asset_id": mint, "symbol": mint, "size": size})
    if isinstance(risk, dict) and not risk.get("error"):
        if risk.get("allowed") is False:
            return False, f"risk_blocked:{risk}", score

    return True, "ok", score


async def pump_sniper_cycle():
    if state.get("kill"):
        log_event("[PUMP] kill switch active; skip")
        return

    candidates = await _fetch_candidates()
    size = _trade_size()

    for c in candidates:
        mint = c.get("mint") or c.get("asset_id") or c.get("symbol")
        if not mint or mint in SEEN_MINTS:
            continue
        SEEN_MINTS.add(mint)

        ok, reason, score = await _risk_and_alpha_ok(c, size)
        if not ok:
            log_event(f"[PUMP] skip {str(mint)[:8]} reason={reason}")
            continue

        log_event(f"[PUMP] BUY_SIGNAL {mint} score={score:.3f} size={size} mode={_mode()}")

        payload = {
            "symbol": mint,
            "side": "buy",
            "size": size,
            "slippage_bps": _i(os.getenv("SLIPPAGE_BPS", "80"), 80),
            "confirm": not _b("MANUAL_CONFIRM", "true"),
            "reason": f"pump_sniper score={score:.3f}",
        }
        res = await call("trade_order", payload)
        trades = state.setdefault("trade_history", [])
        trades.append({"ts": int(time.time()), "payload": payload, "result": res})
        if len(trades) > 200:
            del trades[:-200]
        log_event(f"[PUMP] trade_order result: {res}")


async def auto_runtime_loop():
    state["running"] = True
    state["mode"] = _mode()
    log_event(f"[AUTO] original-core runtime started mode={state['mode']}")

    while state.get("running", True):
        try:
            state["mode"] = _mode()
            await _start_existing_plugin_sniper_once()

            if _b("ENABLE_PUMP_SNIPER", "true"):
                await pump_sniper_cycle()

            # Keep original fund/strategy plugins alive if present.
            if _b("RUN_FUND_CYCLE", "false"):
                res = await call("run_fund_cycle", {})
                log_event(f"[AUTO] fund_cycle: {res}")

            await asyncio.sleep(_f(os.getenv("TRADING_INTERVAL_SEC", os.getenv("SNIPER_SCAN_INTERVAL", "2")), 2.0))
        except asyncio.CancelledError:
            break
        except Exception as e:
            log_event(f"[AUTO_ERROR] {e}")
            await asyncio.sleep(5)

    state["running"] = False
    log_event("[AUTO] original-core runtime stopped")


def start_runtime() -> bool:
    global TASK
    if TASK and not TASK.done():
        state["running"] = True
        return False
    TASK = asyncio.create_task(auto_runtime_loop())
    return True


def stop_runtime():
    global TASK
    state["running"] = False
    if TASK and not TASK.done():
        TASK.cancel()
    TASK = None
