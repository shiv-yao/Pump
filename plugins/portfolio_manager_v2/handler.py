import math

# ===== config =====
MAX_TOTAL_EXPOSURE = 0.3
MAX_PER_ASSET = 0.1
BASE_SIZE = 0.02

CORRELATION_PENALTY = 0.7
RISK_REDUCTION = 0.6


# ===== state（簡單版本）=====
POSITIONS = {}


def _get_pos(asset):
    return POSITIONS.get(asset, 0.0)


def _update_pos(asset, size):
    POSITIONS[asset] = POSITIONS.get(asset, 0.0) + size


def _total_exposure():
    return sum(abs(v) for v in POSITIONS.values())


def _same_side_pressure(side):
    """
    檢查是否已經過多同方向倉位
    """
    same = 0
    total = 0

    for v in POSITIONS.values():
        if v > 0:
            total += 1
            if side == "buy":
                same += 1
        elif v < 0:
            total += 1
            if side == "sell":
                same += 1

    if total == 0:
        return 0

    return same / total


# ===== core logic =====
def run_portfolio_v2(asset_id, capital, orderbook_score=0.0, wallet_score=0.0):
    capital = float(capital)

    # ===== combine alpha =====
    score = (orderbook_score * 0.5) + (wallet_score * 0.8)

    if score < 0.55:
        return {"action": "hold", "size": 0.0, "score": score}

    side = "buy" if score > 0.6 else "sell"

    # ===== base sizing =====
    size = capital * BASE_SIZE * score

    # ===== exposure control =====
    total_exp = _total_exposure()

    if total_exp > capital * MAX_TOTAL_EXPOSURE:
        size *= 0.3  # 強制縮倉

    # ===== per asset cap =====
    current = _get_pos(asset_id)

    if abs(current) > capital * MAX_PER_ASSET:
        size *= 0.5

    # ===== correlation control =====
    pressure = _same_side_pressure(side)

    if pressure > 0.7:
        size *= CORRELATION_PENALTY

    # ===== risk scaling =====
    if score < 0.65:
        size *= RISK_REDUCTION

    # ===== clamp =====
    size = max(0.0, min(size, capital * 0.1))

    if size <= 0:
        return {"action": "hold", "size": 0.0, "score": score}

    # ===== update state =====
    if side == "buy":
        _update_pos(asset_id, size)
    else:
        _update_pos(asset_id, -size)

    return {
        "action": side,
        "size": size,
        "score": score
    }
