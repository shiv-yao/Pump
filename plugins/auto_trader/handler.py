import asyncio

from app.plugin_manager import execute_tool

RUNNING = False

async def run_auto_trading(symbol: str = "BTCUSDT"):
    global RUNNING
    RUNNING = True

    capital = 10  # 初始資金

    logs = []

    while RUNNING:
        try:
            # 1. alpha
            signal = await execute_tool("get_alpha_signal", {"symbol": symbol})

            import json
            data = json.loads(signal)

            score = data["score"]

            # 2. 決策
            action = await execute_tool("decide_trade", {"score": score})

            # 3. 倉位
            size = await execute_tool("position_size", {
                "score": score,
                "capital": capital
            })

            if "buy" in action:
                result = await execute_tool("execute_trade", {
                    "side": "buy",
                    "symbol": symbol,
                    "amount": float(size)
                })
                logs.append(result)

            elif "sell" in action:
                result = await execute_tool("execute_trade", {
                    "side": "sell",
                    "symbol": symbol,
                    "amount": float(size)
                })
                logs.append(result)

        except Exception as e:
            logs.append(str(e))

        await asyncio.sleep(2)  # 節奏控制

    return logs
