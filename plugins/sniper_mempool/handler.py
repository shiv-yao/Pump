import asyncio
import json
import websockets

from app.utils.loader import call

RUNNING = False
TASK = None

WSS = "wss://api.mainnet-beta.solana.com"

PROGRAMS = [
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5TtzQ3d3S",  # Jupiter
    "pump111111111111111111111111111111111111111"   # pump (示意)
]


async def mempool_stream():
    async with websockets.connect(WSS) as ws:
        sub = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "logsSubscribe",
            "params": [{"mentions": PROGRAMS}, {"commitment": "processed"}]
        }
        await ws.send(json.dumps(sub))

        while RUNNING:
            msg = await ws.recv()
            data = json.loads(msg)

            logs = data.get("params", {}).get("result", {}).get("value", {}).get("logs", [])

            for log in logs:
                if "initialize" in log or "mint" in log:
                    await call("sniper_execute_fast", {
                        "source": "mempool",
                        "log": log
                    })


async def start_mempool_sniper():
    global RUNNING, TASK

    if RUNNING:
        return {"ok": True}

    RUNNING = True
    TASK = asyncio.create_task(mempool_stream())

    return {"ok": True, "msg": "mempool sniper started"}


async def stop_mempool_sniper():
    global RUNNING, TASK

    RUNNING = False

    if TASK:
        TASK.cancel()
        TASK = None

    return {"ok": True}
