from __future__ import annotations

import asyncio
import json
import os
import time
import websockets

from app.state import state
from app.utils.loader import call

WS_URL = os.getenv("SOLANA_WS", "wss://api.mainnet-beta.solana.com")

TASK = None
SEEN = set()


def log(msg):
    print(msg)
    logs = state.setdefault("logs", [])
    logs.append(msg)
    if len(logs) > 200:
        del logs[:-200]


def _b(name, default="false"):
    return os.getenv(name, default).lower() in ["1", "true", "yes"]


def _f(x, d=0.0):
    try:
        return float(x)
    except:
        return d


async def detect_new_tokens():
    async with websockets.connect(WS_URL) as ws:

        sub = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "logsSubscribe",
            "params": [
                {"mentions": ["TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"]},
                {"commitment": "processed"}
            ]
        }

        await ws.send(json.dumps(sub))
        log("[SNIPER] WS subscribed")

        while True:
            msg = await ws.recv()
            data = json.loads(msg)

            if "params" not in data:
                continue

            logs_data = data["params"]["result"]["value"]["logs"]

            for l in logs_data:
                if "InitializeMint" in l or "mint" in l.lower():
                    mint = extract_mint(l)
                    if mint:
                        await handle_new_mint(mint)


def extract_mint(log_line: str):
    # ⚠️ 簡化版本（實戰你可以再強化）
    parts = log_line.split()
    for p in parts:
        if len(p) > 30:
            return p
    return None


async def handle_new_mint(mint):
    if mint in SEEN:
        return

    SEEN.add(mint)

    log(f"[NEW TOKEN] {mint}")

    size = _f(os.getenv("MAX_POSITION_PER_TRADE", "0.001"), 0.001)

    # 🔥 風控
    risk = await call("check_risk", {
        "symbol": mint,
        "size": size
    })

    if isinstance(risk, dict) and risk.get("allowed") is False:
        log(f"[BLOCK] risk reject {mint}")
        return

    # 🔥 流動性檢查（Jupiter）
    quote = await call("get_quote", {
        "inputMint": "So11111111111111111111111111111111111111112",
        "outputMint": mint,
        "amount": int(size * 1e9)
    })

    if not quote or quote.get("error"):
        log(f"[SKIP] no liquidity {mint}")
        return

    # 🔥 下單
    res = await call("trade_order", {
        "symbol": mint,
        "side": "buy",
        "size": size,
        "confirm": not _b("MANUAL_CONFIRM", "true"),
        "reason": "onchain_sniper"
    })

    state.setdefault("trade_history", []).append({
        "ts": int(time.time()),
        "mint": mint,
        "result": res
    })

    log(f"[BUY] {mint} → {res}")


async def run_loop():
    state["running"] = True
    log("[SNIPER] ONCHAIN STARTED")

    try:
        await detect_new_tokens()
    except Exception as e:
        log(f"[ERROR] {e}")
        await asyncio.sleep(3)


def start():
    global TASK
    if TASK and not TASK.done():
        return False
    TASK = asyncio.create_task(run_loop())
    return True


def stop():
    global TASK
    if TASK:
        TASK.cancel()
    TASK = None
