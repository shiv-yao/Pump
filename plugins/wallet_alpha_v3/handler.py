import time
import math
from collections import defaultdict

# ===== storage =====
WALLETS = {}
ASSET_TRADES = defaultdict(list)
CLUSTERS = defaultdict(set)

# ===== config =====
WINDOW = 100
DECAY = 0.97
LEADER_WINDOW = 20  # 最早幾筆視為 leader
MIN_TRADES = 5


# ===== helpers =====
def _get_wallet(w):
    if w not in WALLETS:
        WALLETS[w] = {
            "pnl": 0.0,
            "trades": [],
            "score": 0.0,
            "cluster": None,
            "last_update": time.time()
        }
    return WALLETS[w]


def _decay(w):
    now = time.time()
    dt = now - w["last_update"]
    factor = DECAY ** (dt / 60)
    w["pnl"] *= factor
    w["last_update"] = now


def _update_score(w):
    trades = w["trades"][-WINDOW:]

    if len(trades) < MIN_TRADES:
        w["score"] = 0.0
        return

    pnl = sum(t["pnl"] for t in trades)
    wins = sum(1 for t in trades if t["pnl"] > 0)

    winrate = wins / len(trades)

    score = 0.0
    score += pnl * 0.4
    score += winrate * 1.5

    w["score"] = max(0.0, score)


# ===== clustering =====
def _cluster_wallet(wallet, asset_id):
    """
    簡單 clustering：
    同一 asset + 同時間段進場 → 同 cluster
    """
    trades = ASSET_TRADES[asset_id]

    if not trades:
        return None

    t0 = trades[-1]["time"]

    for t in reversed(trades[-20:]):
        if abs(t["time"] - t0) < 5:  # 5秒內
            cid = f"{asset_id}_{int(t['time']//10)}"
            CLUSTERS[cid].add(wallet)
            return cid

    return None


# ===== leader detection =====
def _is_leader(asset_id, wallet):
    trades = ASSET_TRADES[asset_id]

    if len(trades) < LEADER_WINDOW:
        return False

    early = trades[:LEADER_WINDOW]

    leaders = set(t["wallet"] for t in early)

    return wallet in leaders


# ===== record trade =====
def wa_record_trade(wallet, asset_id, side, price, size, timestamp=None):
    w = _get_wallet(wallet)

    _decay(w)

    ts = timestamp or time.time()

    trade = {
        "time": ts,
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

    # cluster
    cid = _cluster_wallet(wallet, asset_id)
    if cid:
        w["cluster"] = cid

    # trim
    if len(w["trades"]) > WINDOW:
        w["trades"] = w["trades"][-WINDOW:]

    _update_score(w)

    return {"ok": True}


# ===== aggregation =====
def _aggregate(asset_id):
    trades = ASSET_TRADES.get(asset_id, [])
    if not trades:
        return None

    score_buy = 0.0
    score_sell = 0.0

    now = time.time()

    for t in trades[-200:]:
        w = WALLETS.get(t["wallet"])
        if not w:
            continue

        _decay(w)

        age = now - t["time"]
        time_weight = math.exp(-age / 120)

        base = w["score"]

        # leader boost
        if _is_leader(asset_id, t["wallet"]):
            base *= 1.5

        # cluster boost
        if w["cluster"]:
            cluster_size = len(CLUSTERS[w["cluster"]])
            base *= min(2.0, 1 + cluster_size * 0.2)

        weight = base * time_weight

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


# ===== main alpha =====
def get_wallet_alpha_v3(asset_id):
    sig = _aggregate(asset_id)

    if not sig:
        return {"action": "hold", "score": 0.0}

    # threshold
    if sig["score"] < 0.55:
        return {"action": "hold", "score": sig["score"]}

    return sig


# ===== debug =====
def wa_get_leaders():
    ranked = sorted(
        WALLETS.items(),
        key=lambda x: x[1]["score"],
        reverse=True
    )

    return [
        {
            "wallet": k,
            "score": round(v["score"], 4),
            "cluster": v["cluster"]
        }
        for k, v in ranked[:20]
    ]
