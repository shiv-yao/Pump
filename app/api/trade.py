from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.utils.loader import call, debug_tool_map
from app.state import state

router = APIRouter(prefix="/api", tags=["real-trading"])


class TradeRequest(BaseModel):
    symbol: str = Field(..., description="Token symbol or Solana mint address")
    size: float = Field(..., gt=0, description="Order size. Interpreted by execution_gateway; default quote asset is USDC unless configured otherwise.")
    side: str = Field("buy", pattern="^(buy|sell)$")
    slippage_bps: int = Field(default_factory=lambda: int(os.getenv("SLIPPAGE_BPS", "80")), ge=1, le=5000)
    confirm: bool = Field(False, description="Must be true when MANUAL_CONFIRM=true and REAL_TRADING=true")
    reason: str | None = None


@router.get("/trading/status")
async def trading_status():
    return {
        "success": True,
        "real_trading": os.getenv("REAL_TRADING", "false").lower() == "true",
        "manual_confirm": os.getenv("MANUAL_CONFIRM", "true").lower() == "true",
        "use_jito": os.getenv("USE_JITO", "false").lower() == "true",
        "kill": bool(state.get("kill", False)),
        "running": bool(state.get("running", True)),
        "tools": debug_tool_map(),
    }


@router.post("/quote")
async def quote(p: dict[str, Any]):
    # Keep original route but make failures explicit.
    q = await call("jup_get_quote", {
        "symbol": p.get("symbol") or p.get("mint"),
        "amount": p.get("size") or p.get("amount")
    })
    return {"success": not (isinstance(q, dict) and "error" in q), "data": q}


@router.post("/trade")
async def trade(req: TradeRequest):
    if state.get("kill", False):
        raise HTTPException(status_code=423, detail="killswitch is active")

    payload = req.model_dump()
    result = await call("trade_order", payload)
    return {"success": not (isinstance(result, dict) and "error" in result), "data": result}


@router.post("/trade/buy")
async def buy(req: TradeRequest):
    req.side = "buy"
    return await trade(req)


@router.post("/trade/sell")
async def sell(req: TradeRequest):
    req.side = "sell"
    return await trade(req)


@router.post("/sell")
async def sell_legacy(p: dict[str, Any]):
    p["side"] = "sell"
    req = TradeRequest(**p)
    return await sell(req)


@router.post("/killswitch")
async def killswitch():
    state["kill"] = True
    state["running"] = False
    return {"success": True, "status": "stopped"}


@router.post("/killswitch/reset")
async def reset_killswitch():
    state["kill"] = False
    state["running"] = True
    return {"success": True, "status": "running"}


@router.post("/sniper/start")
async def start_sniper():
    from app.sniper.sniper_loop import start
    state["running"] = True
    return await start()


@router.post("/sniper/stop")
async def stop_sniper():
    from app.sniper.sniper_loop import stop
    state["running"] = False
    return await stop()
