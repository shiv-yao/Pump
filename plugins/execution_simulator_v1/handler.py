import random
import math


# ===== config =====
TAKER_FEE = 0.001
MAKER_FEE = 0.0005

BASE_LATENCY = 0.05
LATENCY_JITTER = 0.05

SLIPPAGE_IMPACT = 0.002


# ===== utils =====
def _rand_latency():
    return BASE_LATENCY + random.uniform(0, LATENCY_JITTER)


def _slippage(price, size, liquidity):
    if liquidity <= 0:
        return price

    impact = (size / liquidity) * SLIPPAGE_IMPACT
    return price * (1 + impact)


def _walk_book(side, size, bids, asks):
    """
    吃 orderbook depth
    """
    filled = 0
    cost = 0

    book = asks if side == "buy" else bids

    for lvl in book:
        px = float(lvl["price"])
        qty = float(lvl["size"])

        take = min(size - filled, qty)
        cost += take * px
        filled += take

        if filled >= size:
            break

    if filled == 0:
        return 0, 0

    avg = cost / filled
    return filled, avg


# ===== main simulate =====
async def simulate_order(
    asset_id,
    side,
    size,
    book,
    order_type="limit",
    price=None
):
    """
    模擬一筆訂單
    """

    bids = book.get("bids", [])
    asks = book.get("asks", [])

    if not bids or not asks:
        return {"error": "empty book"}

    best_bid = float(book["best_bid"])
    best_ask = float(book["best_ask"])

    latency = _rand_latency()

    # ===== fill logic =====
    if order_type == "ioc":
        # IOC = 直接吃單
        filled, avg = _walk_book(side, size, bids, asks)

        if filled == 0:
            return {"filled": False}

        fee = avg * filled * TAKER_FEE

        return {
            "filled": True,
            "size": filled,
            "avg_price": avg,
            "fee": fee,
            "latency": latency,
            "mode": "ioc"
        }

    # ===== limit =====
    limit_px = price if price else (best_ask if side == "buy" else best_bid)

    # 是否成交（模擬排隊）
    fill_prob = 0.6

    if random.random() > fill_prob:
        return {"filled": False, "latency": latency}

    filled, avg = _walk_book(side, size, bids, asks)

    if filled == 0:
        return {"filled": False}

    # slippage
    liquidity = sum(float(x["size"]) for x in (asks if side == "buy" else bids))
    avg = _slippage(avg, filled, liquidity)

    fee = avg * filled * (TAKER_FEE if order_type == "ioc" else MAKER_FEE)

    return {
        "filled": True,
        "size": filled,
        "avg_price": avg,
        "fee": fee,
        "latency": latency,
        "mode": "limit"
    }


# ===== replay hook =====
async def simulate_fill(asset_id, side, size, book):
    """
    給 replay_engine 用
    """
    return await simulate_order(
        asset_id=asset_id,
        side=side,
        size=size,
        book=book,
        order_type="ioc"
    )
