from app.utils.loader import call


# ===== ENGINE WRAPPER =====
async def start_engine(markets=None, capital=100, **kwargs):
    return await call("start_v7_engine", {
        "markets": markets or ["BTCUSDT"],
        "capital": capital
    })


async def stop_engine(**kwargs):
    return await call("stop_v7_engine", {})


async def get_state(**kwargs):
    return await call("get_state", {})


# ===== FUND DECISION =====
async def fund_decide_trade(symbol, capital=100, **kwargs):
    # ===== ALPHA =====
    alpha = await call("get_alpha_v2", {"asset_id": symbol})
    wallet = await call("get_wallet_alpha_v3", {"asset_id": symbol})

    if not isinstance(alpha, dict):
        return {"action": "hold"}

    base_score = float(alpha.get("score", 0))
    base_side = alpha.get("action", "hold")

    wallet_score = float(wallet.get("score", 0)) if isinstance(wallet, dict) else 0
    wallet_side = wallet.get("action", "hold") if isinstance(wallet, dict) else "hold"

    # ===== FUSION =====
    if wallet_score > base_score:
        side = wallet_side
        score = wallet_score
        strategy_id = "wallet_alpha"
    else:
        side = base_side
        score = base_score
        strategy_id = "market_alpha"

    # ===== FILTER =====
    if score < 0.5:
        return {"action": "hold"}

    # ===== ALLOCATOR =====
    alloc = await call("allocator_get_budget", {
        "strategy_id": strategy_id,
        "capital": capital
    })

    if not isinstance(alloc, dict):
        return {"action": "hold"}

    budget = float(alloc.get("budget", 0))
    if budget <= 0:
        return {"action": "hold"}

    size = budget * 0.2

    # ===== CLAMP =====
    size = max(0.001, min(size, capital * 0.05))

    # ===== RISK =====
    risk = await call("check_risk", {
        "asset_id": symbol,
        "size": size
    })

    if isinstance(risk, dict) and not risk.get("allowed", True):
        return {"action": "hold"}

    return {
        "action": side,
        "size": size,
        "strategy_id": strategy_id,
        "score": score
    }
