import asyncio
from app.utils.loader import call


async def sniper_loop():
    while True:
        try:
            result = await call("sniper_scan", {})
            candidates = result.get("candidates", [])

            for c in candidates:
                if c.get("score", 0) > 0.8:
                    await call("trade_order", {
                        "symbol": c["asset_id"],
                        "side": "buy",
                        "size": 0.02,
                        "priority": "jito"
                    })

        except Exception as e:
            print("sniper loop error:", e)

        await asyncio.sleep(0.3)
