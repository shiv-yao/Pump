import time

# 簡單 cache（避免抖動）
LAST = {}

def normalize(x, lo, hi):
    return max(0, min(1, (x - lo) / (hi - lo + 1e-6)))


async def get_alpha_v2(asset_id: str):

    # ===== 1️⃣ orderbook =====
    book = await call("get_polymarket_book_cache", {
        "asset_id": asset_id
    })

    if "error" in book:
        return {"error": "no book"}

    bid = book.get("best_bid", 0)
    ask = book.get("best_ask", 0)
    mid = (bid + ask) / 2 if bid and ask else 0

    bids = book.get("bids", [])[:5]
    asks = book.get("asks", [])[:5]

    bid_sz = sum(x["size"] for x in bids)
    ask_sz = sum(x["size"] for x in asks)

    imbalance = (bid_sz - ask_sz) / max(bid_sz + ask_sz, 1)

    # ===== 2️⃣ micro price pressure =====
    pressure = (bid * bid_sz + ask * ask_sz) / max(bid_sz + ask_sz, 1)

    micro_alpha = (pressure - mid)

    # ===== 3️⃣ momentum =====
    prev = LAST.get(asset_id, mid)
    momentum = mid - prev
    LAST[asset_id] = mid

    # ===== 4️⃣ fake breakout 過濾 =====
    if abs(momentum) > 0.05:
        momentum = 0

    # ===== 5️⃣ scoring =====
    score = (
        normalize(imbalance, -1, 1) * 0.4 +
        normalize(micro_alpha, -0.05, 0.05) * 0.3 +
        normalize(momentum, -0.02, 0.02) * 0.3
    )

    # ===== 6️⃣ action =====
    if score > 0.65:
        action = "buy"
    elif score < 0.35:
        action = "sell"
    else:
        action = "hold"

    return {
        "score": score,
        "action": action,
        "mid": mid,
        "imbalance": imbalance,
        "momentum": momentum
    }
