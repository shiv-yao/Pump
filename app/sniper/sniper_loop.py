import asyncio
from app.utils.loader import call
from app.fund.fund_brain import decide_trade
from app.execution.trade_executor import execute_trade
from app.risk.kill_switch import check_kill

RUNNING = False

SCAN_INTERVAL = 0.2


async def sniper_loop():
    global RUNNING
    RUNNING = True

    while RUNNING:

        # ===== kill switch =====
        if await check_kill():
            print("⚠️ KILL SWITCH ACTIVE")
            await asyncio.sleep(1)
            continue

        # ===== scan tokens =====
        result = await call("sniper_scan", {})
        tokens = result.get("candidates", []) if isinstance(result, dict) else []

        for token in tokens:
            symbol = token.get("asset_id")
            score = float(token.get("score", 0))

            if score < 0.7:
                continue

            # ===== fund brain =====
            decision = await decide_trade(symbol)

            if decision.get("action") != "buy":
                continue

            # ===== execute =====
            res = await execute_trade(decision, symbol)

            print(f"🚀 TRADE {symbol}", res)

        await asyncio.sleep(SCAN_INTERVAL)


async def start_sniper():
    asyncio.create_task(sniper_loop())
    return {"status": "started"}


async def stop_sniper():
    global RUNNING
    RUNNING = False
    return {"status": "stopped"}
