import asyncio
import time
import os

from app.utils.loader import call

RUNNING = False
TASK = None

SNIPER_CACHE = {}

# ===== CONFIG =====
SCAN_INTERVAL = float(os.getenv("SNIPER_SCAN_INTERVAL", "0.3"))
MIN_SCORE = float(os.getenv("SNIPER_MIN_SCORE", "0.7"))
STRONG_SCORE = float(os.getenv("SNIPER_STRONG_SCORE", "0.8"))

BASE_SIZE = float(os.getenv("SNIPER_BASE_SIZE", "0.02"))
MAX_SIZE = float(os.getenv("SNIPER_MAX_SIZE", "0.05"))

USE_JITO = os.getenv("USE_JITO", "true").lower() == "true"


# =========================
# SCAN
# =========================
async def sniper_scan():
    tokens = await call("pump_candidates", {})

    results = []

    for t in tokens:
        mint = t.get("mint")
        if not mint:
            continue

        # 避免重複打
        if mint in SNIPER_CACHE:
            continue

        SNIPER_CACHE[mint] = time.time()

        # ===== wallet alpha =====
        wallet = await call("get_wallet_alpha_v3", {"asset_id": mint})

        score = float(wallet.get("score", 0)) if isinstance(wallet, dict) else 0

        if score < MIN_SCORE:
            continue

        # ===== liquidity =====
        liq = await call("check_liquidity", {"asset_id": mint})

        if isinstance(liq, dict) and liq.get("ok") is False:
            continue

        # ===== rug =====
        rug = await call("rug_guard_check", {"asset_id": mint})

        if isinstance(rug, dict) and rug.get("rug", False):
            continue

        results.append({
            "asset_id": mint,
            "score": score
        })

    return results


# =========================
# EXECUTION
# =========================
async def sniper_execute(asset_id, score, capital=100):
    # ===== size =====
    size = BASE_SIZE

    if score > STRONG_SCORE:
        size = MAX_SIZE

    # ===== risk =====
    risk = await call("check_risk", {
        "asset_id": asset_id,
        "size": size
    })

    if isinstance(risk, dict) and not risk.get("allowed", True):
        return {"skip": True, "reason": "risk"}

    # ===== JITO boost =====
    payload = {
        "asset_id": asset_id,
        "side": "buy",
        "size": size
    }

    if USE_JITO and score > STRONG_SCORE:
        payload.update({
            "priority_fee": 120000,
            "jito_tip": 5000
        })

    # ===== REAL EXECUTION =====
    result = await call("trade_order", payload)

    return result


# =========================
# LOOP
# =========================
async def sniper_loop(capital=100):
    global RUNNING

    while RUNNING:
        try:
            tokens = await sniper_scan()

            for t in tokens:
                await sniper_execute(
                    t["asset_id"],
                    t["score"],
                    capital
                )

        except Exception as e:
            print(f"[SNIPER ERROR] {e}")

        await asyncio.sleep(SCAN_INTERVAL)


# =========================
# API
# =========================
async def start_sniper(capital=100, **kwargs):
    global RUNNING, TASK

    if RUNNING:
        return {"ok": True, "msg": "sniper already running"}

    RUNNING = True
    TASK = asyncio.create_task(sniper_loop(capital))

    return {
        "ok": True,
        "msg": "sniper started"
    }


async def stop_sniper(**kwargs):
    global RUNNING, TASK

    RUNNING = False

    if TASK:
        TASK.cancel()
        TASK = None

    return {"ok": True, "msg": "sniper stopped"}
