from __future__ import annotations

import asyncio
import json
import os
import re
import time

import httpx
import websockets

from app.state import state
from app.utils.loader import call

WS_URL = os.getenv("SOLANA_WS", "wss://api.mainnet-beta.solana.com")
SOL_MINT = "So11111111111111111111111111111111111111112"
BASE58_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")

TASK = None
SEEN = set()
LAST_TRADE_TS = 0


def log(msg):
    print(msg)
    logs = state.setdefault("logs", [])
    logs.append(msg)
    if len(logs) > 300:
        del logs[:-300]


def _b(name, default="false"):
    return os.getenv(name, default).lower() in {"1", "true", "yes", "on"}


def _f(x, d=0.0):
    try:
        return float(x)
    except Exception:
        return d


def _i(x, d=0):
    try:
        return int(float(x))
    except Exception:
        return d


def extract_mint(log_line: str):
    for raw in log_line.replace(",", " ").replace("(", " ").replace(")", " ").split():
        token = raw.strip().strip('"').strip("'")

        if token.startswith("pool:"):
            continue
        if token == SOL_MINT:
            continue
        if len(token) > 44:
            continue
        if not BASE58_RE.match(token):
            continue

        return token

    return None


async def get_jupiter_quote(mint: str, amount: int):
    url = os.getenv("JUP_QUOTE_URL", "https://quote-api.jup.ag/v6/quote")

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            url,
            params={
                "inputMint": SOL_MINT,
                "outputMint": mint,
                "amount": amount,
                "slippageBps": _i(os.getenv("SLIPPAGE_BPS", "120"), 120),
            },
        )
        r.raise_for_status()
        return r.json()


async def wait_until_tradable(mint: str, size_sol: float):
    retries = _i(os.getenv("TRADE_READY_RETRIES", "8"), 8)
    delay = _f(os.getenv("TRADE_READY_DELAY_SEC", "2"), 2)
    min_out = _i(os.getenv("MIN_OUT_AMOUNT", "10"), 10)
    max_impact = _f(os.getenv("MAX_PRICE_IMPACT", "0.35"), 0.35)

    amount = int(size_sol * 1_000_000_000)

    for i in range(retries):
        try:
            quote = await get_jupiter_quote(mint, amount)

            if not isinstance(quote, dict):
                log(f"[TRADE_READY] retry={i+1}/{retries} invalid_quote {mint}")
                await asyncio.sleep(delay)
                continue

            if quote.get("error"):
                log(f"[TRADE_READY] retry={i+1}/{retries} quote_error {mint}: {quote.get('error')}")
                await asyncio.sleep(delay)
                continue

            out_amount = _i(quote.get("outAmount", 0), 0)
            impact = _f(quote.get("priceImpactPct", 1), 1)

            if out_amount < min_out:
                log(f"[TRADE_READY] retry={i+1}/{retries} low_out {mint} out={out_amount} min={min_out}")
                await asyncio.sleep(delay)
                continue

            if impact > max_impact:
                log(f"[TRADE_READY] retry={i+1}/{retries} high_impact {mint} impact={impact}")
                await asyncio.sleep(delay)
                continue

            log(f"[TRADE_READY] OK {mint} out={out_amount} impact={impact}")
            return True, quote

        except Exception as e:
            log(f"[TRADE_READY] retry={i+1}/{retries} quote_error {mint}: {e}")
            await asyncio.sleep(delay)

    return False, None


async def risk_ok(mint: str, size: float):
    try:
        risk = await call("check_risk", {
            "symbol": mint,
            "asset_id": mint,
            "size": size,
        })

        if isinstance(risk, dict) and risk.get("allowed") is False:
            return False, f"risk_blocked:{risk}"

    except Exception as e:
        return False, f"risk_error:{e}"

    return True, "ok"


async def handle_new_mint(mint: str):
    global LAST_TRADE_TS

    if mint in SEEN:
        return

    SEEN.add(mint)
    log(f"[NEW TOKEN] {mint}")

    size = _f(os.getenv("MAX_POSITION_PER_TRADE", "0.001"), 0.001)

    cooldown = _i(os.getenv("COOLDOWN_AFTER_TRADE_SEC", "10"), 10)
    now = time.time()

    if now - LAST_TRADE_TS < cooldown:
        log(f"[SKIP] cooldown {mint}")
        return

    ok, reason = await risk_ok(mint, size)
    if not ok:
        log(f"[SKIP] {mint} {reason}")
        return

    tradable, quote = await wait_until_tradable(mint, size)
    if not tradable:
        log(f"[SKIP] no tradable liquidity {mint}")
        return

    payload = {
        "symbol": mint,
        "side": "buy",
        "size": size,
        "slippage_bps": _i(os.getenv("SLIPPAGE_BPS", "120"), 120),
        "priority_fee": _i(os.getenv("PRIORITY_FEE", "5000"), 5000),
        "jito_tip": _i(os.getenv("JITO_TIP_LAMPORTS", "2000"), 2000),
        "confirm": not _b("MANUAL_CONFIRM", "true"),
        "reason": "onchain_sniper_trade_ready",
    }

    if not _b("REAL_TRADING", "false"):
        res = {
            "success": True,
            "paper": True,
            "message": "REAL_TRADING=false; signal only",
            "payload": payload,
            "quote": quote,
        }
    else:
        res = await call("trade_order", payload)

    LAST_TRADE_TS = time.time()

    state.setdefault("trade_history", []).append({
        "ts": int(time.time()),
        "mint": mint,
        "action": "buy",
        "payload": payload,
        "quote": quote,
        "result": res,
    })

    log(f"[BUY_SIGNAL] {mint} -> {res}")


async def detect_new_tokens():
    async with websockets.connect(WS_URL) as ws:
        sub = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "logsSubscribe",
            "params": [
                {"mentions": ["TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"]},
                {"commitment": "processed"},
            ],
        }

        await ws.send(json.dumps(sub))
        log("[SNIPER] WS subscribed")

        while True:
            msg = await ws.recv()
            data = json.loads(msg)

            if "params" not in data:
                continue

            logs_data = data["params"]["result"]["value"].get("logs", [])

            for line in logs_data:
                if "InitializeMint" in line or "mint" in line.lower():
                    mint = extract_mint(line)
                    if mint:
                        await handle_new_mint(mint)


async def run_loop():
    state["running"] = True
    log("[SNIPER] ONCHAIN STARTED")

    while True:
        try:
            await detect_new_tokens()
        except asyncio.CancelledError:
            break
        except Exception as e:
            log(f"[SNIPER ERROR] {e}")
            await asyncio.sleep(3)


def start():
    global TASK

    if TASK and not TASK.done():
        return False

    TASK = asyncio.create_task(run_loop())
    return True


def stop():
    global TASK

    if TASK and not TASK.done():
        TASK.cancel()

    TASK = None
