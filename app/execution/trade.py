from __future__ import annotations

import os
import time
from typing import Any

from app.state import state
from app.execution.jupiter import SOL_MINT, safe_quote, jupiter_order


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


async def execute_swap(mint: str, size_sol: float, quote: dict | None = None) -> dict:
    """
    War mode execution entry.
    PAPER mode: 只記錄 signal/order，不真下單。
    REAL mode: 走 Jupiter order；簽名送出仍交給你既有 trade_order 系統或後續 wallet layer。
    """
    if not quote:
        quote = await safe_quote(SOL_MINT, mint, size_sol)

    if not quote or quote.get("error"):
        res = {
            "success": False,
            "error": "quote_failed",
            "quote": quote,
            "mint": mint,
        }
        log(f"[EXECUTE] quote failed {mint}: {res}")
        return res

    payload = {
        "symbol": mint,
        "side": "buy",
        "size": size_sol,
        "slippage_bps": _i(os.getenv("SLIPPAGE_BPS", "120"), 120),
        "priority_fee": _i(os.getenv("PRIORITY_FEE", "8000"), 8000),
        "jito_tip": _i(os.getenv("JITO_TIP_LAMPORTS", "3000"), 3000),
        "reason": "war_sniper",
    }

    if not _b("REAL_TRADING", "false"):
        res = {
            "success": True,
            "paper": True,
            "message": "REAL_TRADING=false; signal only",
            "payload": payload,
            "quote": quote,
        }

        state.setdefault("trade_history", []).append(
            {
                "ts": int(time.time()),
                "action": "buy_signal",
                "mint": mint,
                "payload": payload,
                "quote": quote,
                "result": res,
            }
        )

        log(f"[PAPER_BUY_SIGNAL] {mint} size={size_sol}")
        return res

    order = await jupiter_order(mint, size_sol, quote)

    state.setdefault("trade_history", []).append(
        {
            "ts": int(time.time()),
            "action": "buy_order",
            "mint": mint,
            "payload": payload,
            "quote": quote,
            "result": order,
        }
    )

    if order.get("success") is False or order.get("error"):
        log(f"[BUY_ORDER_FAIL] {mint} {order}")
    else:
        log(f"[BUY_ORDER_CREATED] {mint}")

    return order


async def execute_sell(mint: str, size: float, reason: str = "auto_sell") -> dict:
    payload = {
        "symbol": mint,
        "side": "sell",
        "size": size,
        "slippage_bps": _i(os.getenv("SLIPPAGE_BPS", "120"), 120),
        "priority_fee": _i(os.getenv("PRIORITY_FEE", "8000"), 8000),
        "jito_tip": _i(os.getenv("JITO_TIP_LAMPORTS", "3000"), 3000),
        "reason": reason,
    }

    if not _b("REAL_TRADING", "false"):
        res = {
            "success": True,
            "paper": True,
            "message": "REAL_TRADING=false; sell signal only",
            "payload": payload,
        }
    else:
        from app.utils.loader import call
        res = await call("trade_order", payload)

    state.setdefault("trade_history", []).append(
        {
            "ts": int(time.time()),
            "action": "sell",
            "mint": mint,
            "payload": payload,
            "result": res,
        }
    )

    log(f"[SELL] {mint} reason={reason} -> {res}")
    return res
