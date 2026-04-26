from app.utils.loader import call

DEV_WALLETS = {}

async def track_wallet(asset_id):
    tx = await call("get_recent_transactions", {"asset_id": asset_id})

    if not tx:
        return

    wallet = tx.get("signer")

    if wallet not in DEV_WALLETS:
        DEV_WALLETS[wallet] = {
            "early_entries": 0,
            "wins": 0
        }

    DEV_WALLETS[wallet]["early_entries"] += 1

    return wallet


async def get_dev_signal(asset_id):
    wallet = await track_wallet(asset_id)

    if not wallet:
        return {"score": 0}

    stats = DEV_WALLETS.get(wallet, {})

    score = min(1.0, stats.get("early_entries", 0) * 0.1)

    return {
        "wallet": wallet,
        "score": score,
        "action": "buy" if score > 0.7 else "hold"
    }
