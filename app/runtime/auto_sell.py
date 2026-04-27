from __future__ import annotations

import asyncio
import os
import time
from typing import Any

from app.state import state
from app.execution.jupiter import safe_quote, SOL_MINT
from app.execution.trade import execute_sell

TASK: asyncio.Task | None = None


def _b(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).lower() in {"1", "true", "yes", "on"}


def _f(x: Any, d: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return d


def _i(x: Any, d: int = 0) -> int:
    try:
        return int(float(x))
    except Exception:
        return d


def log(msg: str):
    print(msg)
    logs = state.setdefault("logs", [])
    logs.append(msg)
    if len(logs) > 500:
        del logs[:-500]


async def get_position_price_sol(mint: str) -> float | None:
    """
    用 Jupiter quote 估算 token -> SOL 價格。
    注意：這裡假設 amount=1 token base unit，只是簡化版。
    實盤要根據 decimals 改。
    """
    try:
        q = await safe_quote(mint, SOL_MINT, 0.000001)
        if not q or q.get("error"):
            return None
        out_amount = _f(q.get("outAmount"), 0.0)
        return out_amount / 1_000_000_000
    except Exception:
        return None


async def update_positions_once():
    positions = state.get("positions", []) or []
    if not positions:
        return

    take_profit = _f(os.getenv("TAKE_PROFIT", "0.25"), 0.25)
    stop_loss = _f(os.getenv("STOP_LOSS", "-0.10"), -0.10)
    trailing_gap = _f(os.getenv("TRAILING_GAP", "0.08"), 0.08)
    max_hold_sec = _i(os.getenv("MAX_HOLD_SEC", "240"), 240)

    now = int(time.time())

    for p in positions[:]:
        mint = p.get("mint")
        if not mint:
            continue

        entry = _f(p.get("entry_price", p.get("entry", 0.0)), 0.0)
        size = _f(p.get("size", 0.0), 0.0)

        if entry <= 0 or size <= 0:
            continue

        price = await get_position_price_sol(mint)
        if price is None or price <= 0:
            continue

        peak = _f(p.get("peak", entry), entry)
        if price > peak:
            p["peak"] = price
            peak = price

        pnl = (price - entry) / entry
        drawdown_from_peak = (price - peak) / peak if peak > 0 else 0.0
        hold_sec = now - _i(p.get("ts", now), now)

        p["last_price"] = price
        p["unrealized_pnl"] = pnl
        p["hold_sec"] = hold_sec

        reason = None

        if pnl >= take_profit:
            reason = "TAKE_PROFIT"
        elif pnl <= stop_loss:
            reason = "STOP_LOSS"
        elif drawdown_from_peak <= -abs(trailing_gap):
            reason = "TRAILING_STOP"
        elif hold_sec >= max_hold_sec:
            reason = "TIME_EXIT"

        if reason:
            res = await execute_sell(mint, size, reason)
            state["positions"] = [
                x for x in state.get("positions", []) if x.get("mint") != mint
            ]
            log(f"[AUTO_SELL] {mint} reason={reason} pnl={pnl:.4f} res={res}")


async def auto_sell_loop():
    log("[AUTO_SELL] started")

    while True:
        try:
            if state.get("kill"):
                await asyncio.sleep(3)
                continue

            await update_positions_once()
            await asyncio.sleep(_f(os.getenv("AUTO_SELL_INTERVAL_SEC", "5"), 5))

        except asyncio.CancelledError:
            break
        except Exception as e:
            log(f"[AUTO_SELL_ERROR] {e}")
            await asyncio.sleep(5)

    log("[AUTO_SELL] stopped")


def start():
    global TASK

    if TASK and not TASK.done():
        return False

    TASK = asyncio.create_task(auto_sell_loop())
    return True


def stop():
    global TASK

    if TASK and not TASK.done():
        TASK.cancel()

    TASK = None
