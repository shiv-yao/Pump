import asyncio
import json
import websockets
import os
import httpx

RPC_WSS = os.getenv("SOLANA_WSS", "wss://api.mainnet-beta.solana.com")
BASE_URL = os.getenv("BASE_URL")

JUP_PROGRAM = "JUP6LkbZBjS1jKKwapdHNy74zcZ3tLUZoi5nRZ7h9tq"

seen = set()

async def mempool_sniper():
    async with websockets.connect(RPC_WSS) as ws:
        sub = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "logsSubscribe",
            "params": [
                {"mentions": [JUP_PROGRAM]},
                {"commitment": "processed"}
            ]
        }

        await ws.send(json.dumps(sub))

        async for msg in ws:
            data = json.loads(msg)

            if "params" not in data:
                continue

            logs = data["params"]["result"]["value"]["logs"]

            for log in logs:
                if "swap" in log.lower():
                    sig = data["params"]["result"]["value"]["signature"]

                    if sig in seen:
                        continue
                    seen.add(sig)

                    print("[MEMPOOL]", sig)

                    asyncio.create_task(handle_signal(sig))
