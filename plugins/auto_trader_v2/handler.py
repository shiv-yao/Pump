import asyncio
import json

from app.plugin_manager import execute_tool

RUNNING = False


async def run_fund(asset_id: str, symbol: str = "BTCUSDT"):
    """
    Example:
    run_fund(asset_id="1234567890", symbol="BTCUSDT")
    """
    global RUNNING
    RUNNING = True

    capital = 10.0
    logs = []

    # 先啟動 Polymarket market-channel stream
    try:
        start_msg = await execute_tool("start_polymarket_book", {"asset_ids": [asset_id]})
        logs.append(start_msg)
    except Exception as e:
        logs.append(f"stream start error: {e}")

    while RUNNING:
        try:
            signal_raw = await execute_tool("get_polymarket_signal", {
                "asset_id": asset_id,
                "symbol": symbol
            })

            if isinstance(signal_raw, str):
                signal = json.loads(signal_raw)
            else:
                signal = signal_raw

            if "error" in signal:
                logs.append(signal["error"])
                await asyncio.sleep(1)
                continue

            action = signal["action"]
            confidence = float(signal.get("confidence", 0))
            size = round(capital * min(max(confidence, 0.05), 0.25), 4)

            if action == "buy_yes":
                result = await execute_tool("pm_buy", {
                    "market": asset_id,
                    "amount": size
                })
                logs.append(f"BUY_YES size={size} -> {result}")

            elif action == "buy_no":
                result = await execute_tool("pm_sell", {
                    "market": asset_id,
                    "amount": size
                })
                logs.append(f"BUY_NO size={size} -> {result}")

            else:
                logs.append(f"HOLD edge={signal['edge']:.4f} imb={signal['imbalance']:.4f}")

        except Exception as e:
            logs.append(str(e))

        await asyncio.sleep(1)

    return logs


async def stop_fund():
    global RUNNING
    RUNNING = False
    try:
        await execute_tool("stop_polymarket_book", {})
    except Exception:
        pass
    return "Fund stopped"
