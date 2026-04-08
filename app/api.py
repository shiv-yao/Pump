# app/api.py
import os
import asyncio
import importlib
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from app.state import engine
from app.execution.jupiter_exec import execute_swap
from app.config import SOL_MINT as SOL, SOL_DECIMALS


ENGINE_TASK: Optional[asyncio.Task] = None
ENGINE_MAIN_LOOP = None
ENGINE_GET_METRICS = None
ENGINE_MODULE = None


# =========================================================
# FALLBACK METRICS
# =========================================================

def _safe_get_metrics_fallback() -> Dict[str, Any]:
    positions = getattr(engine, "positions", []) or []
    trades = getattr(engine, "trade_history", []) or []
    logs = getattr(engine, "logs", []) or []
    stats = getattr(engine, "stats", {}) or {}

    capital = float(getattr(engine, "capital", 0.0))
    start_capital = float(getattr(engine, "start_capital", capital))
    peak_capital = float(getattr(engine, "peak_capital", capital))

    total_return = capital - start_capital
    return_pct = (total_return / start_capital) if start_capital > 0 else 0.0
    drawdown = ((peak_capital - capital) / peak_capital) if peak_capital > 0 else 0.0

    wins = int(stats.get("wins", 0))
    losses = int(stats.get("losses", 0))
    trade_count = len(trades)

    return {
        "summary": {
            "capital": capital,
            "start_capital": start_capital,
            "peak_capital": peak_capital,
            "equity_gain": total_return,
            "return_pct": return_pct,
            "drawdown": drawdown,
            "running": bool(getattr(engine, "running", False)),
            "mode": "REAL" if str(os.getenv("REAL_TRADING", "false")).lower() == "true" else "PAPER",
        },
        "performance": {
            "trades": trade_count,
            "wins": wins,
            "losses": losses,
            "win_rate": (wins / trade_count) if trade_count > 0 else 0.0,
            "profit_factor": 0.0,
            "total_return": total_return,
        },
        "trading": {
            "signals": int(stats.get("signals", 0)),
            "executed": int(stats.get("executed", 0)),
            "rejected": int(stats.get("rejected", 0)),
            "errors": int(stats.get("errors", 0)),
            "open_positions": len(positions),
            "open_exposure": float(stats.get("open_exposure", 0.0)),
            "forced_trades": int(stats.get("forced_trades", 0)),
            "no_trade_cycles": int(getattr(engine, "no_trade_cycles", 0)),
        },
        "positions": positions,
        "recent_trades": trades[-20:],
        "logs": logs[-120:],
    }


# =========================================================
# ENGINE IMPORT RESOLVER
# =========================================================

def _resolve_engine_module():
    global ENGINE_MAIN_LOOP, ENGINE_GET_METRICS, ENGINE_MODULE

    candidates = [
        "app.main",          # 你目前這版最重要
        "app.engine.main",
        "app.engine",
        "app.core.engine",
        "app.engine.v66",
        "app.engine.v65",
        "app.engine.v64",
        "app.engine.v63",
        "app.engine.v62",
        "app.engine.v61",
        "app.engine.v60",
    ]

    for mod_name in candidates:
        try:
            mod = importlib.import_module(mod_name)

            main_loop = getattr(mod, "main_loop", None)
            get_metrics = getattr(mod, "get_metrics", None)

            if callable(main_loop):
                ENGINE_MAIN_LOOP = main_loop
                ENGINE_GET_METRICS = get_metrics if callable(get_metrics) else _safe_get_metrics_fallback
                ENGINE_MODULE = mod
                print(f"✅ ENGINE LOADED: {mod_name}")
                return mod

        except Exception as e:
            print(f"ENGINE_IMPORT_SKIP {mod_name}: {e}")

    ENGINE_MAIN_LOOP = None
    ENGINE_GET_METRICS = _safe_get_metrics_fallback
    ENGINE_MODULE = None
    print("⚠️ NO REAL ENGINE MODULE FOUND; USING FALLBACK METRICS")
    return None


# =========================================================
# ENGINE STATE INIT
# =========================================================

def ensure_engine():
    engine.positions = getattr(engine, "positions", [])
    engine.trade_history = getattr(engine, "trade_history", [])
    engine.logs = getattr(engine, "logs", [])

    engine.capital = float(getattr(engine, "capital", 5.0))
    engine.start_capital = float(getattr(engine, "start_capital", engine.capital))
    engine.peak_capital = float(getattr(engine, "peak_capital", engine.capital))

    engine.running = bool(getattr(engine, "running", False))
    engine.no_trade_cycles = int(getattr(engine, "no_trade_cycles", 0))

    engine.last_signal = getattr(engine, "last_signal", "")
    engine.last_trade = getattr(engine, "last_trade", "")

    engine.stats = getattr(engine, "stats", {})
    defaults = {
        "signals": 0,
        "executed": 0,
        "rejected": 0,
        "errors": 0,
        "open_positions": 0,
        "open_exposure": 0.0,
        "trades": 0,
        "wins": 0,
        "losses": 0,
        "forced_trades": 0,
    }
    for k, v in defaults.items():
        engine.stats.setdefault(k, v)


def push_log(msg: str):
    print(msg)
    engine.logs.append(str(msg))
    engine.logs = engine.logs[-1200:]


# =========================================================
# ENGINE RUNNER
# =========================================================

async def _engine_runner():
    ensure_engine()
    push_log("🚀 V66 API ENGINE RUNNER START")

    if ENGINE_MAIN_LOOP is None:
        push_log("❌ ENGINE_MAIN_LOOP missing")
        return

    try:
        await ENGINE_MAIN_LOOP()
    except asyncio.CancelledError:
        push_log("🛑 ENGINE TASK CANCELLED")
        raise
    except Exception as e:
        engine.stats["errors"] = int(engine.stats.get("errors", 0)) + 1
        push_log(f"❌ ENGINE CRASH: {e}")
        raise


async def start_engine_task():
    global ENGINE_TASK

    ensure_engine()
    _resolve_engine_module()

    if ENGINE_MAIN_LOOP is None:
        raise RuntimeError("engine_main_loop_not_found")

    if ENGINE_TASK and not ENGINE_TASK.done():
        return False

    engine.running = True
    ENGINE_TASK = asyncio.create_task(_engine_runner())
    push_log("🔥 ENGINE TASK STARTED")
    return True


async def stop_engine_task():
    global ENGINE_TASK

    engine.running = False

    if ENGINE_TASK and not ENGINE_TASK.done():
        ENGINE_TASK.cancel()
        try:
            await ENGINE_TASK
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    push_log("🛑 ENGINE TASK STOPPED")
    return True


# =========================================================
# FASTAPI LIFESPAN
# =========================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_engine()
    _resolve_engine_module()

    auto_start = str(os.getenv("AUTO_START_ENGINE", "true")).lower() == "true"
    if auto_start:
        try:
            await start_engine_task()
        except Exception as e:
            push_log(f"⚠️ AUTO_START_FAIL: {e}")

    yield

    await stop_engine_task()


app = FastAPI(
    title="V66 Pump Trading API",
    version="66.0.0",
    lifespan=lifespan,
)


# =========================================================
# ROOT / HEALTH
# =========================================================

@app.get("/")
async def root():
    return {
        "status": "ok",
        "name": "V66 COMPLETE LIVE ENGINE API",
        "real_trading": str(os.getenv("REAL_TRADING", "false")).lower() == "true",
        "engine_running": bool(getattr(engine, "running", False)),
        "task_alive": bool(ENGINE_TASK and not ENGINE_TASK.done()),
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "engine_running": bool(getattr(engine, "running", False)),
        "task_alive": bool(ENGINE_TASK and not ENGINE_TASK.done()),
        "real_trading": str(os.getenv("REAL_TRADING", "false")).lower() == "true",
        "capital": float(getattr(engine, "capital", 0.0)),
        "positions": len(getattr(engine, "positions", []) or []),
        "errors": int((getattr(engine, "stats", {}) or {}).get("errors", 0)),
    }


# =========================================================
# METRICS / LOGS
# =========================================================

@app.get("/metrics")
async def metrics():
    try:
        data = ENGINE_GET_METRICS() if callable(ENGINE_GET_METRICS) else _safe_get_metrics_fallback()
        return JSONResponse(content=data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"metrics_error: {e}")


@app.get("/logs")
async def logs(limit: int = 200):
    xs = getattr(engine, "logs", []) or []
    return {
        "count": min(limit, len(xs)),
        "logs": xs[-limit:],
    }


# =========================================================
# CONTROL
# =========================================================

@app.post("/start")
async def start():
    try:
        started = await start_engine_task()
        return {
            "ok": True,
            "started": started,
            "engine_running": bool(getattr(engine, "running", False)),
            "task_alive": bool(ENGINE_TASK and not ENGINE_TASK.done()),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"start_error: {e}")


@app.post("/stop")
async def stop():
    await stop_engine_task()
    return {
        "ok": True,
        "engine_running": bool(getattr(engine, "running", False)),
        "task_alive": bool(ENGINE_TASK and not ENGINE_TASK.done()),
    }


@app.post("/restart")
async def restart():
    await stop_engine_task()
    await asyncio.sleep(1)
    started = await start_engine_task()
    return {
        "ok": True,
        "started": started,
        "engine_running": bool(getattr(engine, "running", False)),
        "task_alive": bool(ENGINE_TASK and not ENGINE_TASK.done()),
    }


@app.post("/killswitch")
async def killswitch():
    await stop_engine_task()
    return {
        "ok": True,
        "killed": True,
        "engine_running": False,
    }


# =========================================================
# STATUS DATA
# =========================================================

@app.get("/positions")
async def positions():
    return {
        "count": len(getattr(engine, "positions", []) or []),
        "positions": getattr(engine, "positions", []) or [],
    }


@app.get("/trades")
async def trades(limit: int = 50):
    xs = getattr(engine, "trade_history", []) or []
    return {
        "count": min(limit, len(xs)),
        "trades": xs[-limit:],
    }


@app.get("/signal")
async def signal():
    return {
        "last_signal": getattr(engine, "last_signal", ""),
        "last_trade": getattr(engine, "last_trade", ""),
        "stats": getattr(engine, "stats", {}) or {},
    }


@app.get("/config")
async def config():
    keys = [
        "REAL_TRADING",
        "AUTO_START_ENGINE",
        "MAX_POSITIONS",
        "MAX_EXPOSURE",
        "MAX_POSITION_SIZE",
        "TAKE_PROFIT",
        "STOP_LOSS",
        "ENTRY_THRESHOLD",
        "SOLANA_RPC_HTTP",
        "SOLANA_RPC_WSS",
        "JUP_BASE_API",
        "USE_JITO",
        "BIRDEYE_API_KEY",
        "MIN_LIQUIDITY_TRADE",
        "TOP_K_PRESELECT",
        "TOP_N_TO_TRADE",
        "TOKEN_COOLDOWN",
    ]
    return {k: os.getenv(k) for k in keys}


# =========================================================
# MANUAL TRADE HELPERS
# =========================================================

def _find_position_by_mint(mint: str):
    positions = getattr(engine, "positions", []) or []
    for p in positions:
        if p.get("mint") == mint:
            return p
    return None


async def _fallback_manual_buy(mint: str, amount_sol: float):
    amt_atomic = int(amount_sol * SOL_DECIMALS)
    res = await execute_swap(SOL, mint, amt_atomic)

    if not res:
        raise RuntimeError("empty_swap_result")

    if res.get("error"):
        raise RuntimeError(str(res.get("error")))

    out_amount = int((res.get("quote", {}) or {}).get("outAmount") or 0)
    tx_sig = res.get("result") if isinstance(res.get("result"), str) else res.get("signature")

    price_guess = 0.0
    if out_amount > 0:
        try:
            price_guess = amt_atomic / out_amount
        except Exception:
            price_guess = 0.0

    position = {
        "mint": mint,
        "entry": price_guess,
        "size": amount_sol,
        "order_sol": amount_sol,
        "token_amount_atomic": out_amount,
        "time": time.time(),
        "mode": "manual",
        "source": "manual_api",
        "meta": {"manual": True},
        "price_source": "manual_api",
        "liq": 0,
        "high": price_guess,
        "wallet_count": 0,
        "tx_buy": tx_sig,
        "forced": False,
        "paper": bool(res.get("paper")),
        "score": 0.0,
        "tier": "MANUAL",
    }

    engine.positions.append(position)
    engine.capital = max(float(getattr(engine, "capital", 0.0)) - amount_sol, 0.0)
    engine.stats["executed"] = int(engine.stats.get("executed", 0)) + 1
    engine.stats["signals"] = int(engine.stats.get("signals", 0)) + 1
    engine.last_trade = f"MANUAL BUY {mint[:6]} sol={amount_sol:.4f}"
    engine.last_signal = engine.last_trade
    push_log(engine.last_trade)

    return {
        "swap": res,
        "position": position,
    }


async def _fallback_manual_sell(mint: str, pct: float):
    pos = _find_position_by_mint(mint)
    if not pos:
        raise RuntimeError("position_not_found")

    token_amount_atomic = int(pos.get("token_amount_atomic") or 0)
    if token_amount_atomic <= 0:
        raise RuntimeError("token_amount_atomic_missing")

    sell_atomic = int(token_amount_atomic * pct)
    if sell_atomic <= 0:
        raise RuntimeError("sell_amount_zero")

    res = await execute_swap(mint, SOL, sell_atomic)
    if not res:
        raise RuntimeError("empty_swap_result")
    if res.get("error"):
        raise RuntimeError(str(res.get("error")))

    if pct >= 0.999:
        try:
            engine.positions.remove(pos)
        except ValueError:
            pass
    else:
        pos["token_amount_atomic"] = max(token_amount_atomic - sell_atomic, 0)
        pos["size"] = float(pos.get("size", 0.0)) * (1 - pct)

    engine.last_trade = f"MANUAL SELL {mint[:6]} pct={pct:.2f}"
    push_log(engine.last_trade)

    return {
        "swap": res,
        "mint": mint,
        "pct": pct,
    }


# =========================================================
# MANUAL TRADE ENDPOINTS
# =========================================================

@app.post("/trade/buy")
async def trade_buy(payload: Dict[str, Any]):
    mint = str(payload.get("mint", "")).strip()
    amount_sol = float(payload.get("amount_sol", 0.0))

    if not mint:
        raise HTTPException(status_code=400, detail="mint_required")
    if amount_sol <= 0:
        raise HTTPException(status_code=400, detail="amount_sol_must_be_positive")

    try:
        mod = _resolve_engine_module()

        if mod is not None:
            manual_buy = getattr(mod, "manual_buy", None)
            if callable(manual_buy):
                res = await manual_buy(mint, amount_sol)
                return {"ok": True, "result": res}

        res = await _fallback_manual_buy(mint, amount_sol)
        return {"ok": True, "result": res}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"manual_buy_error: {e}")


@app.post("/trade/sell")
async def trade_sell(payload: Dict[str, Any]):
    mint = str(payload.get("mint", "")).strip()
    pct = float(payload.get("pct", 1.0))

    if not mint:
        raise HTTPException(status_code=400, detail="mint_required")
    if pct <= 0 or pct > 1:
        raise HTTPException(status_code=400, detail="pct_must_be_between_0_and_1")

    try:
        mod = _resolve_engine_module()

        if mod is not None:
            manual_sell = getattr(mod, "manual_sell", None)
            if callable(manual_sell):
                res = await manual_sell(mint, pct)
                return {"ok": True, "result": res}

        res = await _fallback_manual_sell(mint, pct)
        return {"ok": True, "result": res}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"manual_sell_error: {e}")


# =========================================================
# FUND / BRAIN
# =========================================================

@app.get("/fund/brain")
async def fund_brain():
    try:
        mod = _resolve_engine_module()
        if mod is None:
            return {
                "ok": True,
                "brain": {
                    "allocator": getattr(engine, "engine_allocator", {}),
                    "engine_stats": getattr(engine, "engine_stats", {}),
                },
                "note": "engine_not_loaded_fallback",
            }

        getter = getattr(mod, "get_fund_brain", None)
        if callable(getter):
            return {"ok": True, "brain": getter()}

        return {
            "ok": True,
            "brain": {
                "allocator": getattr(engine, "engine_allocator", {}),
                "engine_stats": getattr(engine, "engine_stats", {}),
            },
            "note": "fallback_brain_snapshot",
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"fund_brain_error: {e}")


@app.post("/fund/rebalance")
async def fund_rebalance():
    try:
        mod = _resolve_engine_module()
        if mod is None:
            raise HTTPException(status_code=500, detail="engine_not_loaded")

        fn = getattr(mod, "manual_rebalance", None)
        if not callable(fn):
            raise HTTPException(status_code=500, detail="manual_rebalance_not_implemented")

        res = await fn()
        return {"ok": True, "result": res}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"rebalance_error: {e}")


# =========================================================
# DEBUG
# =========================================================

@app.get("/debug/state")
async def debug_state():
    return {
        "engine_running": bool(getattr(engine, "running", False)),
        "task_alive": bool(ENGINE_TASK and not ENGINE_TASK.done()),
        "capital": float(getattr(engine, "capital", 0.0)),
        "start_capital": float(getattr(engine, "start_capital", 0.0)),
        "positions": len(getattr(engine, "positions", []) or []),
        "trades": len(getattr(engine, "trade_history", []) or []),
        "stats": getattr(engine, "stats", {}) or {},
        "last_signal": getattr(engine, "last_signal", ""),
        "last_trade": getattr(engine, "last_trade", ""),
        "engine_module": ENGINE_MODULE.__name__ if ENGINE_MODULE else None,
    }
