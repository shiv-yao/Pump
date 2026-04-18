import asyncio, json, os, time
import httpx
import websockets

RUNNING = False
STATE = {
    "last_trade": None,
    "spread": 0,
    "trades": 0
}

POLY_WS = "wss://ws.polymarket.com"
BINANCE_API = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"

SPREAD_THRESHOLD = float(os.getenv("ARB_THRESHOLD", "0.003"))
ORDER_SIZE = float(os.getenv("ARB_ORDER_SIZE", "10"))

# ===== 外部價格 =====
async def get_external_price():
    async with httpx.AsyncClient(timeout=5) as c:
        r = await c.get(BINANCE_API)
        return float(r.json()["price"])

# ===== Polymarket WS =====
async def poly_ws_loop():
    global RUNNING

    async with websockets.connect(POLY_WS) as ws:

        await ws.send(json.dumps({
            "type": "subscribe",
            "channel": "market"
        }))

        while RUNNING:
            msg = await ws.recv()
            data = json.loads(msg)

            if "price" not in data:
                continue

            poly_price = float(data["price"])
            ext_price = await get_external_price()

            spread = (ext_price - poly_price) / poly_price
            STATE["spread"] = spread

            if abs(spread) > SPREAD_THRESHOLD:
                await execute_trade(spread)

# ===== 下單（模擬 / 接你 trading_api）=====
async def execute_trade(spread):
    side = "BUY" if spread > 0 else "SELL"

    # 👉 這裡接你的 trading_api plugin
    print(f"TRADE {side} | spread={spread:.4f}")

    STATE["last_trade"] = {
        "side": side,
        "spread": spread,
        "time": time.time()
    }
    STATE["trades"] += 1

# ===== 主 loop =====
async def bot_loop():
    await poly_ws_loop()

# ===== 控制 =====
async def start_arb_bot():
    global RUNNING
    if RUNNING:
        return "Already running"

    RUNNING = True
    asyncio.create_task(bot_loop())
    return "Arbitrage bot started"

async def stop_arb_bot():
    global RUNNING
    RUNNING = False
    return "Bot stopped"

async def arb_status():
    return json.dumps(STATE, indent=2)
