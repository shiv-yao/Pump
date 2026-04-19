import asyncio
import json

from app.plugin_manager import execute_tool

RUNNING = False


async def run_fund(symbol: str = "BTCUSDT"):
    global RUNNING
    RUNNING = True

    capital = 10
    logs = []

    while RUNNING:
        try:
            # 1️⃣ alpha
            signal_raw = await execute_tool("get_alpha_signal", {"symbol": symbol})
            signal = json.loads(signal_raw)
            score = signal["score"]

            # 2️⃣ risk
            risk = await execute_tool("can_trade", {})
            if risk != "True":
                logs.append("🛑 Risk blocked")
                await asyncio.sleep(2)
                continue

            # 3️⃣ decision
            if score > 0.6:
                side = "buy"
                target = "solana"
            elif score < -0.6:
                side = "sell"
                target = "polymarket"
            else:
                await asyncio.sleep(1)
                continue

            size = capital * 0.1

            # 4️⃣ execution
            result = await execute_tool("route_order", {
                "target": target,
                "side": side,
                "symbol": symbol,
                "amount": size
            })

            logs.append(result)

        except Exception as e:
            logs.append(str(e))

        await asyncio.sleep(1)

    return logs
