import time
import math
from collections import defaultdict

# ===== storage =====
WALLET_STATS = {}
ASSET_TRADES = defaultdict(list)

# ===== config =====
WINDOW = 100
DECAY = 0.97
MIN_TRADES = 5

# ===== helpers =====
def _get_wallet(w):
    if w not in WALLET_STATS:
        WALLET_STATS[w] = {
            "pnl": 0.0,
            "trades": [],
            "score": 0.0,
            "last_update": time.time()
        }
    return WALLET_STATS[w]


def _decay(wallet):
    now = time.time()
    dt = now - wallet["last_update"]

    factor = DECAY ** (dt / 60)
    wallet["pnl"] *= factor
    wallet["last_update"] = now


def _update_score(wallet):
    trades = wallet["trades"][-WINDOW:]

    if len(trades) < MIN_TRADES:
        wallet["score"] = 0.0
        return

    pnl = sum(t["pnl"] for t in trades)
    wins = sum(1 for t in trades if t["pnl"] > 0)

    winrate = wins / len(trades)

    # 核心 scoring（fund style）
    score = 0.0
    score += pnl * 0.4
    score += winrate * 1.5

    wallet["score"] = max(0.0, score)


# ===== public tools =====

def wa_record_trade(wallet, asset_id, side, price, size, timestamp=None):
    w = _get_wallet(wallet)

    _decay(w)

    trade = {
        "time": timestamp or time.time(),
        "asset_id": asset_id,
        "side": side,
        "price": float(price),
        "size": float(size),
        "pnl": 0.0
    }

    w["trades"].append(trade)
    ASSET_TRADES[asset_id].append({
        "wallet": wallet,
        **trade
    })

    # keep window small
    if len(w["trades"]) > WINDOW:
        w["trades"] = w["trades"][-WINDOW:]

    _update_score(w)

    return {"ok": True}


def _aggregate_wallet_signal(asset_id):
    trades = ASSET_TRADES.get(asset_id, [])
    if not trades:
        return None

    score_buy = 0.0
    score_sell = 0.0

    now = time.time()

    for t in trades[-200:]:
        w = WALLET_STATS.get(t["wallet"])
        if not w:
            continue

        _decay(w)

        age = now - t["time"]
        time_weight = math.exp(-age / 120)

        weight = w["score"] * time_weight

        if t["side"] == "buy":
            score_buy += weight
        else:
            score_sell += weight

    total = score_buy + score_sell
    if total == 0:
        return None

    if score_buy > score_sell:
        return {
            "action": "buy",
            "score": score_buy / total
        }
    else:
        return {
            "action": "sell",
            "score": score_sell / total
        }


def get_wallet_alpha_v2(asset_id):
    sig = _aggregate_wallet_signal(asset_id)

    if not sig:
        return {
            "action": "hold",
            "score": 0.0
        }

    # 強信號 threshold
    if sig["score"] < 0.55:
        return {
            "action": "hold",
            "score": sig["score"]
        }

    return sig


def wa_get_top_wallets():
    ranked = sorted(
        WALLET_STATS.items(),
        key=lambda x: x[1]["score"],
        reverse=True
    )

    return [
        {
            "wallet": k,
            "score": round(v["score"], 4),
            "pnl": round(v["pnl"], 4),
            "trades": len(v["trades"])
        }
        for k, v in ranked[:20]
    ]
