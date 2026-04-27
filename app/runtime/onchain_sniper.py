from __future__ import annotations

import asyncio
import json
import os
import time
import re
import websockets

from app.state import state
from app.utils.loader import call

# ================= CONFIG =================
WS_URL = os.getenv("SOLANA_WS", "wss://api.mainnet-beta.solana.com")

SOL_MINT = "So11111111111111111111111111111111111111112"
BASE58_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")

TASK = None
SEEN = set()
LAST_TRADE_TS = 0

# ================= UTILS =================
def log(msg):
    print(msg)
    logs = state.setdefault("logs", [])
    logs.append(msg)
    if len(logs) > 300:
        del logs[:-300]


def _b(name, default="false"):
    return os.getenv(name, default).lower() in {"1", "true", "yes"}


def _f(x, d=0.0):
    try:
        return float(x)
    except:
        return d


def _i(x, d=0):
    try:
        return int(x)
    except:
        return d


# ================= MINT PARSER（🔥關鍵修復） =================
def extract_mint(log_line: str):
    for raw in log_line.replace(",", " ").replace("(", " ").replace(")", " ").split():
        token = raw.strip().strip('"').strip("'")

        if token.startswith("pool:"):
            continue

        if token == SOL_MINT:
            continue

        if not BASE58_RE.match(token):
            continue

        return token

    return None


# ================= CORE =================
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


# ================= SNIPER =================
async def handle_new_mint(mint):
    global LAST_TRADE_TS

    if mint in SEEN:
        return

    # 🔥 交易節流
    now = time.time()
    if now - LAST_TRADE_TS < _i(os.getenv("COOLDOWN_AFTER_TRADE_SEC", "10"), 10):
        return

    SEEN.add(mint)

    log(f"[NEW TOKEN] {mint}")

    size = _f(os.getenv("MAX_POSITION_PER_TRADE", "0.001"), 0.001)

    # ================= RISK =================
    risk = await call("check_risk", {
        "symbol": mint,
        "size": size
    })

    if isinstance(risk, dict) and risk.get("allowed") is False:
        log(f"[BLOCK] risk reject {mint}")
        return

    # ================= JUPITER RETRY（🔥關鍵） =================
    quote = None

    for i in range(3):
        quote = await call("get_quote", {
            "inputMint": SOL_MINT,
            "outputMint": mint,
            "amount": int(size * 1e9)
        })

        if quote and not quote.get("error"):
            break

        await asyncio.sleep(1.2)

    if not quote or quote.get("error"):
        log(f"[SKIP] no liquidity {mint}")
        return

    # ================= LIQ FILTER =================
    out = int(quote.get("outAmount", 0))
    if out < _i(os.getenv("MIN_OUT_AMOUNT", "300"), 300):
        log(f"[LIQ] low out {mint}")
        return

    # ================= MEV GUARD =================
    if _b("ENABLE_MEV_GUARD", "true"):
        impact = float(quote.get("priceImpactPct", 0))
        if impact > _f(os.getenv("MAX_PRICE_IMPACT", "0.15"), 0.15):
            log(f"[MEV BLOCK] high impact {mint}")
            return

    # ================= BUY =================
    log(f"[BUY SIGNAL] {mint} size={size}")

    res = await call("trade_order", {
        "symbol": mint,
        "side": "buy",
        "size": size,
        "confirm": not _b("MANUAL_CONFIRM", "true"),
        "reason": "onchain_sniper"
    })

    LAST_TRADE_TS = time.time()

    state.setdefault("trade_history", []).append({
        "ts": int(time.time()),
        "mint": mint,
        "result": res
    })

    log(f"[BUY] {mint} → {res}")


# ================= LOOP =================
async def run_loop():
    state["running"] = True
    log("[SNIPER] ONCHAIN STARTED")

    while True:
        try:
            await detect_new_tokens()
        except Exception as e:
            log(f"[ERROR] {e}")
            await asyncio.sleep(3)


# ================= CONTROL =================
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
