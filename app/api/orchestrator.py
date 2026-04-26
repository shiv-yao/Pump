import os
import time
from fastapi import APIRouter
from app.command_router import execute_platform_command

router = APIRouter()

ORCH_ENABLED = os.getenv("ORCH_ENABLED", "true").lower() == "true"
REAL_TRADING = os.getenv("REAL_TRADING", "false").lower() == "true"
MANUAL_CONFIRM = os.getenv("MANUAL_CONFIRM", "true").lower() == "true"

BUY_TOOLS = ["trade_order", "buy_token", "execute_trade"]
SCAN_TOOLS = ["sniper_scan", "scan_market", "scan_onchain_activity"]
RISK_TOOLS = ["rug_check", "check_risk", "filter_signal"]
DECISION_TOOLS = ["fund_decide_trade", "decide_trade", "strategy_should_trade"]


async def run_first_available(tools, payload=None):
    errors = []

    for tool in tools:
        try:
            cmd = tool
            if payload:
                cmd = f"{tool} {payload}"

            result = await execute_platform_command(cmd)

            if isinstance(result, dict) and result.get("success") is False:
                errors.append({tool: result})
                continue

            return {
                "tool": tool,
                "success": True,
                "result": result,
            }

        except Exception as e:
            errors.append({tool: str(e)})

    return {
        "success": False,
        "errors": errors,
    }


@router.post("/api/master/run")
async def master_run():
    if not ORCH_ENABLED:
        return {
            "success": False,
            "error": "orchestrator disabled",
        }

    flow = []
    started = int(time.time())

    scan = await run_first_available(SCAN_TOOLS)
    flow.append({"step": "scan", **scan})

    if not scan.get("success"):
        return {
            "success": False,
            "reason": "scan failed",
            "flow": flow,
        }

    risk = await run_first_available(RISK_TOOLS)
    flow.append({"step": "risk", **risk})

    if not risk.get("success"):
        return {
            "success": False,
            "reason": "risk failed",
            "flow": flow,
        }

    decision = await run_first_available(DECISION_TOOLS)
    flow.append({"step": "decision", **decision})

    decision_text = str(decision.get("result", "")).lower()

    should_buy = any(x in decision_text for x in ["buy", "enter", "long", "execute"])

    if not should_buy:
        return {
            "success": True,
            "action": "skip",
            "reason": "decision did not approve buy",
            "flow": flow,
            "elapsed_sec": int(time.time()) - started,
        }

    if not REAL_TRADING:
        return {
            "success": True,
            "action": "paper_buy_signal",
            "real_trading": False,
            "flow": flow,
            "elapsed_sec": int(time.time()) - started,
        }

    if MANUAL_CONFIRM:
        return {
            "success": True,
            "action": "waiting_manual_confirm",
            "manual_confirm": True,
            "flow": flow,
            "elapsed_sec": int(time.time()) - started,
        }

    buy = await run_first_available(BUY_TOOLS)
    flow.append({"step": "buy", **buy})

    return {
        "success": buy.get("success", False),
        "action": "buy_executed" if buy.get("success") else "buy_failed",
        "flow": flow,
        "elapsed_sec": int(time.time()) - started,
    }


@router.post("/api/master/start")
async def master_start():
    return await master_run()


@router.get("/api/master/status")
async def master_status():
    return {
        "success": True,
        "orchestrator": ORCH_ENABLED,
        "real_trading": REAL_TRADING,
        "manual_confirm": MANUAL_CONFIRM,
        "scan_tools": SCAN_TOOLS,
        "risk_tools": RISK_TOOLS,
        "decision_tools": DECISION_TOOLS,
        "buy_tools": BUY_TOOLS,
    }
