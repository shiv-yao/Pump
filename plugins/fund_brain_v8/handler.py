import time
from collections import deque

# ===== state =====
TRADE_HISTORY = deque(maxlen=100)
LAST_PRICES = {}
PARAMS = {
    "threshold": 0.55,
    "risk": 1.0
}


# ========= regime =========
async def fb_get_regime(asset_id):

    book = await call("get_polymarket_book_cache", {"asset_id": asset_id})
    if "error" in book:
        return {"regime": "unknown"}

    mid = (book["best_bid"] + book["best_ask"]) / 2

    prev = LAST_PRICES.get(asset_id, mid)
    LAST_PRICES[asset_id] = mid

    delta = mid - prev

    if abs(delta) > 0.02:
        return {"regime": "trend"}

    if abs(delta) < 0.005:
        return {"regime": "chop"}

    return {"regime": "mean"}


# ========= auto tuning =========
async def fb_adjust_params():

    if len(TRADE_HISTORY) < 10:
        return PARAMS

    wins = [t for t in TRADE_HISTORY if t["pnl"] > 0]
    losses = [t for t in TRADE_HISTORY if t["pnl"] <= 0]

    winrate = len(wins) / len(TRADE_HISTORY)

    # 調整 threshold
    if winrate < 0.4:
        PARAMS["threshold"] += 0.02

    elif winrate > 0.6:
        PARAMS["threshold"] -= 0.02

    PARAMS["threshold"] = max(0.5, min(0.7, PARAMS["threshold"]))

    # 調整風險
    pnl_sum = sum(t["pnl"] for t in TRADE_HISTORY)

    if pnl_sum < 0:
        PARAMS["risk"] *= 0.9
    else:
        PARAMS["risk"] *= 1.05

    PARAMS["risk"] = max(0.5, min(2.0, PARAMS["risk"]))

    return PARAMS


# ========= sizing =========
async def fb_position_size(score, regime):

    base = 0.01

    # alpha 強度
    alpha_mult = score * 2

    # regime
    if regime == "trend":
        regime_mult = 1.5
    elif regime == "mean":
        regime_mult = 1.0
    else:
        regime_mult = 0.6

    size = base * alpha_mult * regime_mult * PARAMS["risk"]

    return max(0.005, min(size, 0.05))


# ========= record trade =========
def fb_record_trade(pnl):
    TRADE_HISTORY.append({
        "time": time.time(),
        "pnl": pnl
    })
