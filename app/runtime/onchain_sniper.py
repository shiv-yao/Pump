from __future__ import annotations

import asyncio
import json
import os
import re
import time
import websockets
from typing import Any

from app.state import state
from app.utils.loader import call
from app.utils.quote_engine import SOL_MINT, get_quote_multi, quote_is_tradable

WS_URL = os.getenv("SOLANA_WS", "wss://api.mainnet-beta.solana.com")

BASE58_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")

TASK: asyncio.Task | None = None
SEEN: set[str] = set()
LAST_TRADE_TS = 0.0


def log(msg: str):
    print(msg)
    logs = state.setdefault("logs", [])
    logs.append(msg)
    if len(logs) > 500:
        del logs[:-500]


def _b(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).lower() in {"1", "true", "yes", "on"}


def _f(x: Any, d: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return d


def _i(x: Any, d: int = 0) -> int:
    try:
        return int(float(x))
    except Exception:
        return d


def extract_mint(log_line: str) -> str | None:
    cleaned = (
        log_line.replace(",", " ")
        .replace("(", " ")
        .replace(")", " ")
        .replace('"', " ")
        .replace("'", " ")
        .replace("\n", " ")
        .replace("\t", " ")
    )

    for raw in cleaned.split():
        token = raw.strip()

        if token.startswith("mint="):
            token = token.replace("mint=", "", 1)

        if token.startswith("pool:"):
            continue

        if token.startswith("program:") or token.startswith("Program"):
            continue

        if token == SOL_MINT:
            continue

        if "/" in token or "+" in token or "=" in token or ":" in token:
            continue

        if len(token) < 32 or len(token) > 44:
            continue

        if not BASE58_RE.match(token):
            continue

        return token

    return None


async def risk_ok(mint: str, size: float) -> tuple[bool, str]:
    try:
        risk = await call(
            "check_risk",
            {
                "symbol": mint,
                "asset_id": mint,
                "size": size,
            },
        )

        if isinstance(risk, dict) and risk.get("allowed") is False:
            return False, f"risk_blocked:{risk}"

    except Exception as e:
        log(f"[RISK_WARN] {mint} {e}")
        return True, "risk_tool_unavailable_but_continue"

    return True, "ok"


async def wait_until_tradable(mint: str, size_sol: float):
    retries = _i(os.getenv("TRADE_READY_RETRIES", "6"), 6)
    delay = _f(os.getenv("TRADE_READY_DELAY_SEC", "2"), 2)
    entry_delay = _f(os.getenv("SNIPER_ENTRY_DELAY_SEC", "1"), 1)

    await asyncio.sleep(entry_delay)

    amount = int(size_sol * 1_000_000_000)

    for i in range(retries):
        quote = await get_quote_multi(SOL_MINT, mint, amount)
        ok, reason = quote_is_tradable(quote)

        if ok:
            out_amount = quote.get("outAmount")
            impact = quote.get("priceImpactPct")
            log(f"[TRADE_READY] OK {mint} out={out_amount} impact={impact}")
            return True, quote

        log(f"[TRADE_READY] retry={i+1}/{retries} {mint} {reason}")
        await asyncio.sleep(delay)

    return False, None


async def safe_trade_order(payload: dict) -> dict:
    try:
        res = await call("trade_order", payload)
        if not isinstance(res, dict):
            return {"success": False, "error": "invalid_trade_response", "raw": str(res)}
        return res
    except Exception as e:
        return {"success": False, "error": str(e)}


async def handle_new_mint(mint: str):
    global LAST_TRADE_TS

    if mint in SEEN:
        return

    SEEN.add(mint)
    log(f"[NEW TOKEN] {mint}")

    size = _f(os.getenv("MAX_POSITION_PER_TRADE", "0.002"), 0.002)
    cooldown = _i(os.getenv("COOLDOWN_AFTER_TRADE_SEC", "8"), 8)

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
        "slippage_bps": _i(os.getenv("SLIPPAGE_BPS", "150"), 150),
        "priority_fee": _i(os.getenv("PRIORITY_FEE", "10000"), 10000),
        "jito_tip": _i(os.getenv("JITO_TIP_LAMPORTS", "5000"), 5000),
        "confirm": not _b("MANUAL_CONFIRM", "true"),
        "reason": "level_max_onchain_sniper",
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
        res = await safe_trade_order(payload)

    LAST_TRADE_TS = time.time()

    state.setdefault("trade_history", []).append(
        {
            "ts": int(time.time()),
            "mint": mint,
            "action": "buy",
            "payload": payload,
            "quote": quote,
            "result": res,
        }
    )

    # paper 也建立 position，給 auto_sell 測試用
    if res.get("success"):
        state.setdefault("positions", []).append(
            {
                "mint": mint,
                "entry": 1.0,
                "entry_price": 1.0,
                "size": size,
                "peak": 1.0,
                "ts": int(time.time()),
                "paper": not _b("REAL_TRADING", "false"),
            }
        )

    log(f"[BUY_SIGNAL] {mint} -> {res}")


async def detect_new_tokens():
    async with websockets.connect(
        WS_URL,
        ping_interval=20,
        ping_timeout=20,
        close_timeout=5,
    ) as ws:
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
    state["mode"] = "REAL" if _b("REAL_TRADING", "false") else "PAPER"
    log("[SNIPER] LEVEL MAX ONCHAIN STARTED")

    while True:
        try:
            await detect_new_tokens()
        except asyncio.CancelledError:
            break
        except Exception as e:
            log(f"[SNIPER ERROR] {e}")
            await asyncio.sleep(3)

    log("[SNIPER] stopped")


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
