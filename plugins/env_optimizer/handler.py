from typing import Any, Dict, List


DEFAULTS = {
    "MAX_LATENCY": 0.10,
    "MIN_EDGE": 0.02,
    "FILL_PROB_THRESHOLD": 0.30,
    "EDGE_STRONG_THRESHOLD": 0.05,
    "FB_THRESHOLD_MIN": 0.50,
    "FB_THRESHOLD_MAX": 0.70,
    "FB_RISK_MIN": 0.50,
    "FB_RISK_MAX": 2.00,
    "FB_BASE_SIZE": 0.01,
    "MAX_POSITION_PER_TRADE": 0.05,
    "MAX_TOTAL_EXPOSURE": 0.20,
    "MAX_DAILY_LOSS": 0.15,
    "WALLET_ALPHA_WINDOW": 50,
    "WALLET_DECAY": 0.95,
    "ENGINE_LOOP_INTERVAL": 0.20,
}


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _stats(trades: List[Dict[str, Any]]) -> Dict[str, float]:
    if not trades:
        return {
            "count": 0,
            "winrate": 0.0,
            "avg_pnl": 0.0,
            "total_pnl": 0.0,
            "max_drawdown": 0.0,
        }

    pnls = [float(t.get("pnl_delta", t.get("pnl", 0.0)) or 0.0) for t in trades]
    wins = [p for p in pnls if p > 0]
    total = sum(pnls)
    avg = total / len(pnls)

    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for p in pnls:
        equity += p
        if equity > peak:
            peak = equity
        dd = peak - equity
        if dd > max_dd:
            max_dd = dd

    return {
        "count": len(pnls),
        "winrate": len(wins) / len(pnls),
        "avg_pnl": avg,
        "total_pnl": total,
        "max_drawdown": max_dd,
    }


def suggest_env_params(trades: List[Dict[str, Any]], current: Dict[str, Any] | None = None):
    params = dict(DEFAULTS)
    if current:
        for k, v in current.items():
            if k in params:
                params[k] = v

    s = _stats(trades)

    if s["count"] < 10:
        return {
            "stats": s,
            "params": params,
            "message": "交易樣本太少，先維持目前設定。"
        }

    winrate = s["winrate"]
    avg_pnl = s["avg_pnl"]
    total_pnl = s["total_pnl"]
    drawdown = s["max_drawdown"]

    # 1) entry threshold
    if winrate < 0.40 or avg_pnl < 0:
        params["FB_THRESHOLD_MIN"] = round(_clamp(float(params["FB_THRESHOLD_MIN"]) + 0.03, 0.50, 0.75), 4)
        params["MIN_EDGE"] = round(_clamp(float(params["MIN_EDGE"]) + 0.005, 0.01, 0.08), 4)
    elif winrate > 0.60 and avg_pnl > 0:
        params["FB_THRESHOLD_MIN"] = round(_clamp(float(params["FB_THRESHOLD_MIN"]) - 0.02, 0.45, 0.75), 4)
        params["MIN_EDGE"] = round(_clamp(float(params["MIN_EDGE"]) - 0.003, 0.005, 0.08), 4)

    # 2) risk sizing
    if drawdown > abs(total_pnl) * 0.8 and drawdown > 0:
        params["FB_BASE_SIZE"] = round(_clamp(float(params["FB_BASE_SIZE"]) * 0.8, 0.003, 0.03), 4)
        params["MAX_POSITION_PER_TRADE"] = round(_clamp(float(params["MAX_POSITION_PER_TRADE"]) * 0.85, 0.01, 0.10), 4)
        params["MAX_TOTAL_EXPOSURE"] = round(_clamp(float(params["MAX_TOTAL_EXPOSURE"]) * 0.9, 0.05, 0.50), 4)
    elif winrate > 0.62 and total_pnl > 0:
        params["FB_BASE_SIZE"] = round(_clamp(float(params["FB_BASE_SIZE"]) * 1.08, 0.003, 0.03), 4)
        params["MAX_POSITION_PER_TRADE"] = round(_clamp(float(params["MAX_POSITION_PER_TRADE"]) * 1.05, 0.01, 0.10), 4)

    # 3) execution behavior
    if winrate < 0.45:
        params["FILL_PROB_THRESHOLD"] = round(_clamp(float(params["FILL_PROB_THRESHOLD"]) + 0.05, 0.20, 0.80), 4)
        params["EDGE_STRONG_THRESHOLD"] = round(_clamp(float(params["EDGE_STRONG_THRESHOLD"]) + 0.01, 0.03, 0.12), 4)
    elif winrate > 0.60:
        params["FILL_PROB_THRESHOLD"] = round(_clamp(float(params["FILL_PROB_THRESHOLD"]) - 0.03, 0.20, 0.80), 4)

    # 4) wallet alpha memory
    if winrate > 0.55:
        params["WALLET_ALPHA_WINDOW"] = int(_clamp(int(params["WALLET_ALPHA_WINDOW"]) + 10, 20, 200))
        params["WALLET_DECAY"] = round(_clamp(float(params["WALLET_DECAY"]) + 0.01, 0.85, 0.995), 4)
    else:
        params["WALLET_ALPHA_WINDOW"] = int(_clamp(int(params["WALLET_ALPHA_WINDOW"]) - 5, 20, 200))
        params["WALLET_DECAY"] = round(_clamp(float(params["WALLET_DECAY"]) - 0.01, 0.85, 0.995), 4)

    # 5) engine speed
    if winrate < 0.45:
        params["ENGINE_LOOP_INTERVAL"] = round(_clamp(float(params["ENGINE_LOOP_INTERVAL"]) + 0.05, 0.05, 1.0), 4)
    elif winrate > 0.60 and total_pnl > 0:
        params["ENGINE_LOOP_INTERVAL"] = round(_clamp(float(params["ENGINE_LOOP_INTERVAL"]) - 0.02, 0.05, 1.0), 4)

    # 6) daily loss guard
    if drawdown > 0 and total_pnl < 0:
        params["MAX_DAILY_LOSS"] = round(_clamp(float(params["MAX_DAILY_LOSS"]) * 0.9, 0.03, 0.30), 4)

    return {
        "stats": s,
        "params": params,
        "message": "已根據近期交易表現產生新的 env 建議值。"
    }


def export_env_block(params: Dict[str, Any]):
    lines = []
    ordered = [
        "MAX_LATENCY",
        "MIN_EDGE",
        "FILL_PROB_THRESHOLD",
        "EDGE_STRONG_THRESHOLD",
        "FB_THRESHOLD_MIN",
        "FB_THRESHOLD_MAX",
        "FB_RISK_MIN",
        "FB_RISK_MAX",
        "FB_BASE_SIZE",
        "MAX_POSITION_PER_TRADE",
        "MAX_TOTAL_EXPOSURE",
        "MAX_DAILY_LOSS",
        "WALLET_ALPHA_WINDOW",
        "WALLET_DECAY",
        "ENGINE_LOOP_INTERVAL",
    ]

    for key in ordered:
        if key in params:
            lines.append(f"{key}={params[key]}")

    return "\n".join(lines)
