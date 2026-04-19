from collections import defaultdict
import time

WALLET_PNL = defaultdict(float)
WALLET_LAST = {}
CACHE = {}


def decay(x, dt):
    return x * (0.95 ** dt)


async def get_wallet_alpha(asset_id: str):

    now = time.time()

    # ===== 1️⃣ 抓最近成交 =====
    fills = await call("pm_get_fills", {"limit": 50})

    if "error" in fills:
        return {"error": "no fills"}

    trades = fills.get("fills", [])

    # ===== 2️⃣ 更新 wallet PnL =====
    for t in trades:
        wallet = t.get("taker") or t.get("maker") or "unknown"
        price = float(t.get("price", 0))
        size = float(t.get("size", 0))

        prev = WALLET_LAST.get(wallet, now)
        dt = now - prev

        WALLET_PNL[wallet] = decay(WALLET_PNL[wallet], dt)

        # 簡化：低買高賣 → +，反之 -
        WALLET_PNL[wallet] += size * (0.5 - price)

        WALLET_LAST[wallet] = now

    # ===== 3️⃣ 排名 =====
    top = sorted(WALLET_PNL.items(), key=lambda x: x[1], reverse=True)[:5]

    if not top:
        return {"action": "hold", "score": 0}

    # ===== 4️⃣ 聚合方向 =====
    signal = 0
    weight = 0

    for w, pnl in top:
        if pnl > 0:
            signal += 1
        else:
            signal -= 1
        weight += abs(pnl)

    score = signal / max(len(top), 1)

    # ===== 5️⃣ 轉交易訊號 =====
    if score > 0.3:
        action = "buy"
    elif score < -0.3:
        action = "sell"
    else:
        action = "hold"

    return {
        "action": action,
        "score": abs(score),
        "top_wallets": top[:3]
    }
