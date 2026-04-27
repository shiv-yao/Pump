from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any

import websockets

from app.state import state
from app.utils.loader import call

# =========================
# GLOBAL
# =========================
TASK: asyncio.Task | None = None
SNIPER_TASK: asyncio.Task | None = None

SEEN_MINTS: set[str] = set()

WS = os.getenv("SOLANA_WS", "wss://api.mainnet-beta.solana.com")

# =========================
# UTILS
# =========================
def _b(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).lower() in {"1", "true", "yes", "on"}

def _f(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except:
        return default

def _i(x: Any, default: int = 0) -> int:
    try:
        return int(x)
    except:
        return default

def log_event(msg: str):
    print(msg)
    logs = state.setdefault("logs", [])
    logs.append(msg)
    if len(logs) > 300:
        del logs[:-300]

# =========================
# 🧠 KRONOS FILTER
# =========================
async def kronos_ok(mint: str) -> bool:
    if not _b("ENABLE_KRONOS", "true"):
        return True

    try:
        res = await call("get_market_regime", {"symbol": mint})
        if "bear" in str(res).lower():
            log_event(f"[KRONOS] skip {mint}")
            return False
    except:
        pass

    return True

# =========================
# 🛡 GUARD PIPELINE
# =========================
async def guard_ok(mint: str, size: float) -> bool:
    try:
        rug = await call("rug_check", {"asset_id": mint})
        if isinstance(rug, dict) and rug.get("allowed") is False:
            log_event(f"[GUARD] rug blocked {mint}")
            return False

        risk = await call("check_risk", {"asset_id": mint, "size": size})
        if isinstance(risk, dict) and risk.get("allowed") is False:
            log_event(f"[GUARD] risk blocked {mint}")
            return False

    except Exception as e:
        log_event(f"[GUARD ERROR] {e}")
        return False

    return True

# =========================
# 💧 JUPITER QUOTE CHECK
# =========================
async def liquidity_ok(mint: str) -> bool:
    if not _b("ENABLE_JUPITER_QUOTE_CHECK", "true"):
        return True

    try:
        res = await call("get_quote", {
            "inputMint": "So11111111111111111111111111111111111111112",
            "outputMint": mint,
            "amount": 1000000
        })

        out = float(res.get("outAmount", 0))
        impact = float(res.get("priceImpactPct", 1))

        if out < _f(os.getenv("MIN_OUT_AMOUNT", "300"), 300):
            log_event(f"[LIQ] low out {mint}")
            return False

        if impact > _f(os.getenv("MAX_PRICE_IMPACT", "0.15"), 0.15):
            log_event(f"[LIQ] high impact {mint}")
            return False

        return True

    except Exception as e:
        log_event(f"[LIQ ERROR] {e}")
        return False

# =========================
# 💰 EXECUTE BUY
# =========================
async def execute_buy(mint: str):
    size = _f(os.getenv("MAX_POSITION_PER_TRADE", "0.01"), 0.01)

    payload = {
        "symbol": mint,
        "side": "buy",
        "size": size,
        "slippage_bps": _i(os.getenv("SLIPPAGE_BPS", "80"), 80),
        "priority_fee": _i(os.getenv("PRIORITY_FEE", "5000"), 5000),
        "jito_tip": _i(os.getenv("JITO_TIP_LAMPORTS", "2000"), 2000),
        "confirm": not _b("MANUAL_CONFIRM", "true"),
        "reason": "SNIPER",
    }

    res = await call("trade_order", payload)

    state.setdefault("trade_history", []).append({
        "ts": int(time.time()),
        "mint": mint,
        "res": res
    })

    log_event(f"[BUY] {mint} -> {res}")

# =========================
# 🔥 CHAIN SNIPER
# =========================
async def chain_sniper():
    log_event("[SNIPER] started")

    while True:
        try:
            async with websockets.connect(WS) as ws:

                await ws.send(json.dumps({
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "logsSubscribe",
                    "params": ["all", {"commitment": "processed"}]
                }))

                while True:
                    msg = await ws.recv()
                    data = json.loads(msg)

                    if "params" not in data:
                        continue

                    logs = data["params"]["result"]["value"]["logs"]

                    for l in logs:
                        if "mint" not in l.lower():
                            continue

                        mint = extract_mint(l)

                        if not mint:
                            continue

                        if mint in SEEN_MINTS:
                            continue

                        SEEN_MINTS.add(mint)

                        log_event(f"[NEW] {mint}")

                        # === PIPELINE ===
                        if not await kronos_ok(mint):
                            continue

                        if not await liquidity_ok(mint):
                            continue

                        if not await guard_ok(mint, 0.01):
                            continue

                        await execute_buy(mint)

        except Exception as e:
            log_event(f"[SNIPER ERROR] {e}")
            await asyncio.sleep(2)

def extract_mint(log: str):
    parts = log.split()
    for p in parts:
        if len(p) > 30:
            return p
    return None

# =========================
# 🔁 DEX SCANNER（修正版）
# =========================
async def dex_scan():
    try:
        symbols = os.getenv("DEX_SCAN_SYMBOLS", "SOL,USDC,BONK").split(",")

        res = await call("scan_market", {
            "symbols": [s.strip() for s in symbols if s.strip()]
        })

        log_event(f"[DEX] {res}")

    except Exception as e:
        log_event(f"[DEX ERROR] {e}")

# =========================
# 🔁 MAIN LOOP
# =========================
async def auto_runtime_loop():
    state["running"] = True
    log_event("[AUTO] runtime started")

    while state.get("running", True):
        try:
            if state.get("kill"):
                log_event("[KILL] active")
                await asyncio.sleep(2)
                continue

            if _b("ENABLE_DEX_SNIPER", "true"):
                await dex_scan()

            await asyncio.sleep(_f(os.getenv("TRADING_INTERVAL_SEC", "5"), 5))

        except asyncio.CancelledError:
            break
        except Exception as e:
            log_event(f"[AUTO ERROR] {e}")
            await asyncio.sleep(5)

    state["running"] = False
    log_event("[AUTO] stopped")

# =========================
# START / STOP
# =========================
def start_runtime():
    global TASK, SNIPER_TASK

    if not TASK:
        TASK = asyncio.create_task(auto_runtime_loop())

    if _b("ENABLE_CHAIN_SNIPER", "true") and not SNIPER_TASK:
        SNIPER_TASK = asyncio.create_task(chain_sniper())

    state["running"] = True
    return True

def stop_runtime():
    global TASK, SNIPER_TASK

    state["running"] = False

    if TASK:
        TASK.cancel()
        TASK = None

    if SNIPER_TASK:
        SNIPER_TASK.cancel()
        SNIPER_TASK = None
