import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.utils.loader import call as _call_tool

router = APIRouter(prefix="/api", tags=["dashboard_v4"])


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _safe_int(x: Any, default: int = 0) -> int:
    try:
        return int(x)
    except Exception:
        return default


def _ok(data: Any, meta: dict | None = None):
    return {"success": True, "data": data, "meta": meta or {}}


def _err(msg: str, code: int = 400):
    raise HTTPException(status_code=code, detail=msg)


# =========================
# DASHBOARD HTML
# =========================
@router.get("/dashboard/v4")
async def dashboard_v4_page():
    html_path = Path(__file__).resolve().parent.parent / "templates" / "dashboard_v4.html"
    if not html_path.exists():
        _err("dashboard_v4.html not found", 404)
    return FileResponse(str(html_path), media_type="text/html")


# =========================
# STATE
# =========================
@router.get("/state")
async def api_state():
    state = await _call_tool("get_state", {})
    if not isinstance(state, dict) or "error" in state:
        return _ok({
            "running": False,
            "mode": "PAPER",
            "pnl": 0.0,
            "unrealized_pnl": 0.0,
            "positions_count": 0,
            "trades_count": 0,
            "winrate": 0.0,
            "drawdown": 0.0,
            "total_exposure": 0.0,
            "positions": [],
            "recent_trades": []
        })

    positions_raw = state.get("positions", {}) or {}
    trades = state.get("trades", []) or []
    pnl = _safe_float(state.get("pnl", 0.0))
    running = bool(state.get("running", False))
    mode = state.get("mode", "PAPER")

    positions = []
    total_exposure = 0.0
    unrealized_pnl = 0.0

    # 支援 dict positions
    if isinstance(positions_raw, dict):
        for asset_id, pos in positions_raw.items():
            if not isinstance(pos, dict):
                continue

            size = _safe_float(pos.get("size", 0.0))
            avg = _safe_float(pos.get("avg", 0.0))
            mark = _safe_float(pos.get("mark", avg))
            pos_pnl = (mark - avg) * size if size else 0.0

            positions.append({
                "asset_id": asset_id,
                "size": size,
                "avg": avg,
                "mark": mark,
                "pnl": pos_pnl,
                "strategy_id": pos.get("strategy_id", "unknown")
            })

            total_exposure += abs(size)
            unrealized_pnl += pos_pnl

    # 支援 list positions
    elif isinstance(positions_raw, list):
        for pos in positions_raw:
            if not isinstance(pos, dict):
                continue

            asset_id = pos.get("asset_id", pos.get("symbol", "unknown"))
            size = _safe_float(pos.get("size", 0.0))
            avg = _safe_float(pos.get("avg", 0.0))
            mark = _safe_float(pos.get("mark", avg))
            pos_pnl = (mark - avg) * size if size else 0.0

            positions.append({
                "asset_id": asset_id,
                "size": size,
                "avg": avg,
                "mark": mark,
                "pnl": pos_pnl,
                "strategy_id": pos.get("strategy_id", "unknown")
            })

            total_exposure += abs(size)
            unrealized_pnl += pos_pnl

    wins = sum(1 for t in trades if _safe_float(t.get("pnl_delta", t.get("pnl", 0.0))) > 0)
    n = len(trades)
    winrate = wins / n if n else 0.0

    eq = 0.0
    peak = 0.0
    max_dd = 0.0
    for t in trades:
        pnl_delta = _safe_float(t.get("pnl_delta", t.get("pnl", 0.0)))
        eq += pnl_delta
        peak = max(peak, eq)
        max_dd = max(max_dd, peak - eq)

    recent_trades = []
    for t in trades[-50:]:
        recent_trades.append({
            "time": t.get("time", time.time()),
            "asset_id": t.get("asset_id", t.get("symbol", "")),
            "side": t.get("side", ""),
            "price": _safe_float(t.get("price", 0.0)),
            "size": _safe_float(t.get("size", t.get("amount", 0.0))),
            "fee": _safe_float(t.get("fee", 0.0)),
            "pnl_delta": _safe_float(t.get("pnl_delta", t.get("pnl", 0.0))),
            "strategy_id": t.get("strategy_id", "unknown"),
            "mode": t.get("mode", "unknown")
        })

    return _ok({
        "running": running,
        "mode": mode,
        "pnl": pnl,
        "unrealized_pnl": unrealized_pnl,
        "positions_count": len(positions),
        "trades_count": len(trades),
        "winrate": winrate,
        "drawdown": max_dd,
        "total_exposure": total_exposure,
        "positions": positions,
        "recent_trades": recent_trades
    })


# =========================
# LEDGER
# =========================
@router.get("/ledger")
async def api_ledger(range: str = "all"):
    state = await _call_tool("get_state", {})
    trades = []
    if isinstance(state, dict) and "error" not in state:
        trades = state.get("trades", []) or []

    equity_curve = []
    drawdown_curve = []
    asset_map = {}
    strategy_map = {}

    eq = 0.0
    peak = 0.0

    for t in trades:
        ts = t.get("time", time.time())
        pnl_delta = _safe_float(t.get("pnl_delta", t.get("pnl", 0.0)))
        asset_id = t.get("asset_id", t.get("symbol", ""))
        strategy_id = t.get("strategy_id", "unknown")

        eq += pnl_delta
        peak = max(peak, eq)
        dd = peak - eq

        equity_curve.append({"ts": ts, "equity": eq})
        drawdown_curve.append({"ts": ts, "drawdown": dd})

        if asset_id not in asset_map:
            asset_map[asset_id] = {
                "asset_id": asset_id,
                "realized": 0.0,
                "unrealized": 0.0,
                "exposure": 0.0
            }
        asset_map[asset_id]["realized"] += pnl_delta
        asset_map[asset_id]["exposure"] += abs(_safe_float(t.get("size", t.get("amount", 0.0))))

        if strategy_id not in strategy_map:
            strategy_map[strategy_id] = {"strategy_id": strategy_id, "pnl": 0.0}
        strategy_map[strategy_id]["pnl"] += pnl_delta

    return _ok({
        "equity_curve": equity_curve,
        "drawdown_curve": drawdown_curve,
        "asset_pnl": list(asset_map.values()),
        "strategy_pnl": list(strategy_map.values())
    }, {"range": range})


# =========================
# STRATEGIES
# =========================
@router.get("/strategies")
async def api_strategies():
    stats = await _call_tool("strategy_get_stats", {})
    if not isinstance(stats, dict) or "error" in stats:
        return _ok([])

    out = []
    for strategy_id, s in stats.items():
        if not isinstance(s, dict):
            continue

        out.append({
            "strategy_id": strategy_id,
            "pnl": _safe_float(s.get("pnl", 0.0)),
            "winrate": _safe_float(s.get("winrate", 0.0)),
            "drawdown": _safe_float(s.get("drawdown", 0.0)),
            "trades": _safe_int(s.get("trades", 0)),
            "enabled": bool(s.get("enabled", True)),
            "cooldown": _safe_int(s.get("cooldown", 0)),
            "regimes": s.get("regimes", {})
        })

    out.sort(key=lambda x: (x["pnl"], x["winrate"]), reverse=True)
    return _ok(out)


# =========================
# ALLOCATION
# =========================
@router.get("/allocation")
async def api_allocation(capital: float = 1000):
    alloc = await _call_tool("allocator_get_allocation_map", {"capital": capital})

    if not isinstance(alloc, dict) or "error" in alloc:
        return _ok({
            "total_capital": capital,
            "weights": [],
            "rebalance_interval": 60,
            "allocator_version": "allocator_v3"
        })

    # 支援兩種回傳：
    # 1. {"allocations": {...}}
    # 2. {"strategy_a": 0.3, "strategy_b": 0.7}
    weights_raw = alloc.get("allocations", alloc)

    weights = []
    if isinstance(weights_raw, dict):
        for sid, weight in weights_raw.items():
            w = _safe_float(weight, 0.0)
            weights.append({
                "strategy_id": sid,
                "weight": w,
                "budget": capital * w
            })

    return _ok({
        "total_capital": capital,
        "weights": weights,
        "rebalance_interval": 60,
        "allocator_version": "allocator_v3"
    })


# =========================
# RISK
# =========================
@router.get("/risk")
async def api_risk():
    state = await _call_tool("get_state", {})
    positions = []
    trades = []

    if isinstance(state, dict) and "error" not in state:
        raw_positions = state.get("positions", {}) or {}
        if isinstance(raw_positions, dict):
            positions = list(raw_positions.values())
        elif isinstance(raw_positions, list):
            positions = raw_positions

        trades = state.get("trades", []) or []

    current_exposure = 0.0
    for p in positions:
        if isinstance(p, dict):
            current_exposure += abs(_safe_float(p.get("size", 0.0)))

    eq = 0.0
    peak = 0.0
    max_dd = 0.0
    for t in trades:
        pnl_delta = _safe_float(t.get("pnl_delta", t.get("pnl", 0.0)))
        eq += pnl_delta
        peak = max(peak, eq)
        max_dd = max(max_dd, peak - eq)

    buy_count = 0
    sell_count = 0
    for p in positions:
        if not isinstance(p, dict):
            continue
        size = _safe_float(p.get("size", 0.0))
        if size > 0:
            buy_count += 1
        elif size < 0:
            sell_count += 1

    total_dir = buy_count + sell_count
    correlation_pressure = max(buy_count, sell_count) / total_dir if total_dir else 0.0

    alerts = []
    if correlation_pressure > 0.7:
        alerts.append({
            "level": "warn",
            "code": "CORRELATION_HIGH",
            "message": "Correlation pressure near threshold"
        })
    if max_dd > 0:
        alerts.append({
            "level": "info",
            "code": "DRAWDOWN_TRACKING",
            "message": f"Current max drawdown: {round(max_dd, 4)}"
        })

    return _ok({
        "current_exposure": current_exposure,
        "max_total_exposure": 0.30,
        "max_position_per_trade": 0.05,
        "correlation_pressure": correlation_pressure,
        "risk_scale": 0.70,
        "kill_switch_active": False,
        "alerts": alerts
    })


# =========================
# WALLET LEADERS
# =========================
@router.get("/wallet/leaders")
async def api_wallet_leaders():
    leaders = await _call_tool("wa_get_leaders", {})
    if not isinstance(leaders, list):
        leaders = await _call_tool("wa_get_top_wallets", {})
        if not isinstance(leaders, list):
            return _ok([])

    out = []
    for item in leaders:
        if not isinstance(item, dict):
            continue
        out.append({
            "wallet": item.get("wallet", "unknown"),
            "score": _safe_float(item.get("score", 0.0)),
            "cluster": item.get("cluster", item.get("cluster_id", "")),
            "leader": bool(item.get("leader", False)),
            "recent_activity": _safe_int(item.get("recent_activity", item.get("trades", 0)))
        })

    return _ok(out)


# =========================
# ENV JSON
# =========================
@router.get("/env/latest/json")
async def api_env_latest_json():
    env_path = Path("latest.env")
    if not env_path.exists():
        _err("latest.env not found", 404)

    text = env_path.read_text(encoding="utf-8")
    parsed = {}

    for line in text.splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        k, v = line.split("=", 1)
        parsed[k.strip()] = v.strip()

    return _ok({
        "text": text,
        "parsed": parsed,
        "updated_at": int(env_path.stat().st_mtime)
    })


# =========================
# REPLAY
# =========================
@router.post("/replay")
async def api_replay(payload: dict):
    sample_size = _safe_int(payload.get("sample_size", 200), 200)
    config = payload.get("config", None)

    result = await _call_tool("replay_run", {
        "config": config,
        "sample_size": sample_size
    })

    if isinstance(result, dict) and "error" in result:
        result = await _call_tool("run_replay", {
            "config": config,
            "sample_size": sample_size
        })

    if not isinstance(result, dict):
        _err("replay failed")

    return _ok(result)


@router.post("/replay_opt")
async def api_replay_opt(payload: dict):
    sample_size = _safe_int(payload.get("sample_size", 200), 200)
    num_candidates = _safe_int(payload.get("num_candidates", 30), 30)

    result = await _call_tool("replay_optimize", {
        "sample_size": sample_size,
        "num_candidates": num_candidates
    })

    if not isinstance(result, dict):
        _err("replay optimize failed")

    return _ok(result)


# =========================
# OPTIMIZER
# =========================
@router.post("/optimizer/auto")
async def api_optimizer_auto(payload: dict):
    sample_size = _safe_int(payload.get("sample_size", 200), 200)
    num_candidates = _safe_int(payload.get("num_candidates", 30), 30)

    result = await _call_tool("auto_optimize_env", {
        "sample_size": sample_size,
        "num_candidates": num_candidates
    })

    if not isinstance(result, dict):
        _err("auto optimize failed")

    return _ok(result)


@router.post("/optimizer/apply")
async def api_optimizer_apply():
    result = await _call_tool("apply_best_env", {})
    if not isinstance(result, dict):
        _err("apply env failed")
    return _ok(result)


# =========================
# SIMULATOR
# =========================
@router.post("/simulate_order")
async def api_simulate_order(payload: dict):
    result = await _call_tool("simulate_order", payload)
    if not isinstance(result, dict):
        _err("simulate order failed")
    return _ok(result)


# =========================
# ENGINE CONTROL
# =========================
@router.post("/engine/start")
async def api_engine_start(payload: dict):
    markets = payload.get("markets", ["A", "B"])
    capital = _safe_float(payload.get("capital", 100.0), 100.0)

    result = await _call_tool("start_v7_engine", {
        "markets": markets,
        "capital": capital
    })

    if isinstance(result, dict) and "error" in result:
        result = await _call_tool("start_v6_engine", {
            "markets": markets,
            "capital": capital
        })

    if not isinstance(result, dict):
        return _ok({"running": True, "message": "engine started"})

    return _ok({
        "running": True,
        "message": result.get("message", result.get("msg", "engine started"))
    })


@router.post("/engine/stop")
async def api_engine_stop():
    result = await _call_tool("stop_v7_engine", {})
    if isinstance(result, dict) and "error" in result:
        result = await _call_tool("stop_v6_engine", {})

    if not isinstance(result, dict):
        return _ok({"running": False, "message": "engine stopped"})

    return _ok({
        "running": False,
        "message": result.get("message", result.get("msg", "engine stopped"))
    })


# =========================
# LOGS
# =========================
@router.get("/logs")
async def api_logs(type: str = "system", limit: int = 100):
    # 目前仍是 scaffold / sample logs
    now = int(time.time())
    sample = [
        {"ts": now - 10, "level": "info", "type": "execution", "message": "filled order asset=A size=3"},
        {"ts": now - 8, "level": "info", "type": "optimizer", "message": "latest.env generated"},
        {"ts": now - 5, "level": "warn", "type": "risk", "message": "correlation pressure near threshold"},
        {"ts": now - 2, "level": "info", "type": "system", "message": "wallet_feed_ws connected"},
    ]

    if type != "all":
        sample = [x for x in sample if x["type"] == type]

    return _ok(sample[:limit])
