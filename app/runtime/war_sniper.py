from __future__ import annotations
import asyncio, json, os, time, re, websockets

from app.state import state
from app.execution.jupiter import safe_quote, execute_swap

WS = os.getenv("SOLANA_WS")
SOL = "So11111111111111111111111111111111111111112"

BASE58 = re.compile(r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b")

SEEN = set()
TASK = None
LAST = 0


def log(x):
    print(x)
    state.setdefault("logs", []).append(x)


def parse_mint(line: str):
    for m in BASE58.findall(line):
        if m != SOL:
            return m
    return None


async def wait_liquidity(mint):
    for _ in range(6):
        q = await safe_quote(SOL, mint, 0.002)
        if q and q.get("outAmount", 0) > 0:
            return True
        await asyncio.sleep(2)
    return False


async def trade(mint):
    global LAST

    size = float(os.getenv("MAX_POSITION_PER_TRADE", "0.002"))

    # cooldown
    if time.time() - LAST < 8:
        return

    ok = await wait_liquidity(mint)
    if not ok:
        log(f"[SKIP] no liq {mint}")
        return

    quote = await safe_quote(SOL, mint, size)
    if not quote:
        log(f"[SKIP] quote fail {mint}")
        return

    res = await execute_swap(mint, size, quote)

    LAST = time.time()

    state.setdefault("trade_history", []).append({
        "mint": mint,
        "res": res
    })

    log(f"[BUY] {mint}")


async def loop():
    log("[WAR] started")

    async with websockets.connect(WS) as ws:
        await ws.send(json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "logsSubscribe",
            "params": [
                {"mentions": ["TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"]},
                {"commitment": "processed"}
            ]
        }))

        while True:
            msg = await ws.recv()
            data = json.loads(msg)

            if "params" not in data:
                continue

            for l in data["params"]["result"]["value"]["logs"]:
                mint = parse_mint(l)

                if not mint or mint in SEEN:
                    continue

                SEEN.add(mint)
                log(f"[NEW] {mint}")

                await trade(mint)


def start():
    global TASK
    if TASK:
        return False
    TASK = asyncio.create_task(loop())
    return True


def stop():
    global TASK
    if TASK:
        TASK.cancel()
