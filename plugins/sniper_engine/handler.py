import time
from app.utils.loader import call

SNIPER_CACHE = {}


async def sniper_scan():
    tokens = await call("pump_candidates", {})

    results = []

    for t in tokens:
        mint = t.get("mint")
        if not mint:
            continue

        if mint in SNIPER_CACHE:
            continue

        SNIPER_CACHE[mint] = time.time()

        # ===== wallet alpha =====
        wallet = await call("get_wallet_alpha_v3", {"asset_id": mint})

        score = float(wallet.get("score", 0)) if isinstance(wallet, dict) else 0

        if score < 0.7:
            continue

        # ===== liquidity =====
        liq = await call("check_liquidity", {"asset_id": mint})

        if isinstance(liq, dict):
            if liq.get("ok") is False:
                continue

        # ===== rug check =====
        rug = await call("rug_guard_check", {"asset_id": mint})

        if isinstance(rug, dict) and rug.get("rug", False):
            continue

        results.append({
            "asset_id": mint,
            "score": score
        })

    return results
