import time
import asyncio
from typing import Dict, Any

from app.utils.loader import call as tool_call

STATE = {
    "running": False,
    "mode": "paper",
    "last_decision": None,
    "last_trade": None,
    "pnl": 0.0,
}


# =============================
# CORE SIGNAL PIPELINE
# =============================

async def gather_market_context(symbol: str) -> Dict[str, Any]:
    price = await tool_call("price", {"symbol": symbol})
    alpha = await tool_call("get_alpha_signal", {"symbol": symbol})
    risk = await tool_call("get_risk_state", {"symbol": symbol})

    return {
        "symbol": symbol,
        "price": price,
        "alpha": alpha,
        "risk": risk,
    }


# =============================
# DECISION ENGINE
# =============================

def decide_trade(ctx: Dict[str, Any]):
    try:
        score = ctx.get("alpha", {}).get("score", 0)
        risk = ctx.get("risk", {}).get("risk_level", 1)

        if risk > 0.8:
            return {"action": "skip", "reason": "high risk"}

        if score > 0.7:
            return {"action": "buy", "size": 1.0}

        if score < -0.7:
            return {"action": "sell", "size": 1.0}

        return {"action": "hold"}

    except Exception as e:
        return {"action": "error", "error": str(e)}


# =============================
# EXECUTION
# =============================

async def execute_decision(symbol: str, decision: Dict[str, Any]):
    if decision["action"] == "buy":
        return await tool_call("buy_token", {
            "symbol": symbol,
            "size": decision.get("size", 1)
        })

    if decision["action"] == "sell":
        return await tool_call("sell_token", {
            "symbol": symbol,
            "size": decision.get("size", 1)
        })

    return {"status": "no_trade"}


# =============================
# MAIN LOOP
# =============================

async def run_fund_cycle(symbol="BTCUSDT"):
    ctx = await gather_market_context(symbol)

    decision = decide_trade(ctx)
    STATE["last_decision"] = decision

    result = await execute_decision(symbol, decision)
    STATE["last_trade"] = result

    return {
        "context": ctx,
        "decision": decision,
        "result": result
    }


# =============================
# ENGINE LOOP
# =============================

async def run_engine():
    STATE["running"] = True

    while STATE["running"]:
        try:
            await run_fund_cycle("BTCUSDT")
            await asyncio.sleep(2)

        except Exception as e:
            print("ENGINE ERROR:", e)
            await asyncio.sleep(3)


async def start_engine():
    if STATE["running"]:
        return {"status": "already running"}

    asyncio.create_task(run_engine())
    return {"status": "started"}


async def stop_engine():
    STATE["running"] = False
    return {"status": "stopped"}


async def get_state():
    return STATE
