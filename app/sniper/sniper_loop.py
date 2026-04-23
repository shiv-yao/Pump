import asyncio
from app.utils.loader import call

from app.fund.fund_brain import decide_trade
from app.execution.trade_executor import execute_trade
from app.strategy.position_manager import manage_positions
from app.risk.kill_switch import check_kill

RUNNING = False

SCAN_INTERVAL = 0.2
MIN_SNIPER_SCORE = 0.7


async def sniper_loop():
    global RUNNING
    RUNNING = True

    print("🚀 SNIPER LOOP STARTED")

    while RUNNING:

        try:
            # =========================
            # 1️⃣ 風控（Kill Switch）
            # =========================
            if await check_kill():
                print("⚠️ KILL SWITCH ACTIVE")
                await asyncio.sleep(1)
                continue

            # =========================
            # 2️⃣ 持倉管理（TP / SL）
            # =========================
            await manage_positions()

            # =========================
            # 3️⃣ Sniper Scan
            # =========================
            result = await call("sniper_scan", {})

            tokens = []
            if isinstance(result, dict):
                tokens = result.get("candidates", [])
            elif isinstance(result, list):
                tokens = result

            # =========================
            # 4️⃣ 遍歷候選
            # =========================
            for t in tokens:

                symbol = t.get("asset_id") or t.get("mint")
                score = float(t.get("score", 0))

                if not symbol:
                    continue

                if score < MIN_SNIPER_SCORE:
                    continue

                # =========================
                # 5️⃣ Fund Brain 決策
                # =========================
                decision = await decide_trade(symbol)

                if decision.get("action") != "buy":
                    continue

                # =========================
                # 6️⃣ Execute
                # =========================
                res = await execute_trade(decision, symbol)

                print(f"🚀 TRADE {symbol}", res)

            await asyncio.sleep(SCAN_INTERVAL)

        except Exception as e:
            print("❌ SNIPER ERROR:", e)
            await asyncio.sleep(1)


# =========================
# 控制 API
# =========================
async def start_sniper():
    asyncio.create_task(sniper_loop())
    return {"status": "started"}


async def stop_sniper():
    global RUNNING
    RUNNING = False
    return {"status": "stopped"}
