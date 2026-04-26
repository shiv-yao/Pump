import time

POSITIONS = {}
TRADES = []
EQUITY = []
REALIZED_PNL = 0.0
FEES_TOTAL = 0.0


# ===== CONFIG =====
FEE_RATE = 0.0007  # 0.07%


def _get_position(asset):
    if asset not in POSITIONS:
        POSITIONS[asset] = {
            "size": 0.0,
            "avg": 0.0,
            "last_price": 0.0
        }
    return POSITIONS[asset]


# ========= RECORD TRADE =========
def ledger_record_fill(asset_id, side, price, size):
    global REALIZED_PNL, FEES_TOTAL

    price = float(price)
    size = float(size)

    pos = _get_position(asset_id)

    fee = price * size * FEE_RATE
    FEES_TOTAL += fee

    realized = 0.0

    if side == "buy":
        new_size = pos["size"] + size
        pos["avg"] = (pos["avg"] * pos["size"] + price * size) / max(new_size, 1e-9)
        pos["size"] = new_size

    elif side == "sell":
        realized = (price - pos["avg"]) * size
        pos["size"] -= size
        REALIZED_PNL += realized

    pos["last_price"] = price

    TRADES.append({
        "time": time.time(),
        "asset_id": asset_id,
        "side": side,
        "price": price,
        "size": size,
        "fee": fee,
        "realized": realized
    })

    return {
        "realized": realized,
        "fee": fee
    }


# ========= MARK TO MARKET =========
def ledger_mark_price(asset_id, price):
    pos = _get_position(asset_id)
    pos["last_price"] = float(price)


# ========= CALCULATE =========
def _calc_unrealized():
    unreal = 0.0
    for p in POSITIONS.values():
        unreal += (p["last_price"] - p["avg"]) * p["size"]
    return unreal


def _calc_equity():
    unreal = _calc_unrealized()
    return REALIZED_PNL + unreal - FEES_TOTAL


def _calc_drawdown():
    if not EQUITY:
        return 0.0

    peak = max(EQUITY)
    current = EQUITY[-1]

    if peak == 0:
        return 0.0

    return (peak - current) / peak


# ========= SNAPSHOT =========
def ledger_get_state():
    eq = _calc_equity()
    EQUITY.append(eq)

    return {
        "positions": POSITIONS,
        "realized_pnl": REALIZED_PNL,
        "unrealized_pnl": _calc_unrealized(),
        "fees": FEES_TOTAL,
        "equity": eq,
        "drawdown": _calc_drawdown(),
        "trades": TRADES[-50:]
    }


def ledger_get_equity_curve():
    return EQUITY[-200:]
