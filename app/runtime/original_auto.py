from __future__ import annotations

import asyncio
import os
import time
from typing import Any

import httpx

from app.state import state
from app.utils.loader import call

TASK: asyncio.Task | None = None
PLUGIN_SNIPER_STARTED = False
SEEN_MINTS: set[str] = set()

SOL_MINT = "So11111111111111111111111111111111111111112"


def _b(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).lower() in {"1", "true", "yes", "on"}


def _f(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _i(x: Any, default: int = 0) -> int:
    try:
        return int(float(x))
    except Exception:
        return default


def log_event(msg: str):
    print(msg)
    logs = state.setdefault("logs", [])
    logs.append(msg)
    if len(logs) > 300:
        del logs[:-300]


def _mode() -> str:
    return "REAL" if _b("REAL_TRADING", "false") else "PAPER"


def _trade_size() -> float:
    return _f(
        os.getenv("SNIPER_TRADE_SIZE_SOL")
        or os.getenv("MAX_POSITION_SOL")
        or os.getenv("MAX_POSITION_PER_TRADE")
        or "0.001",
        0.001,
    )


async def _start_existing_plugin_sniper_once():
    global PLUGIN_SNIPER_STARTED
    if PLUGIN_SNIPER_STARTED or not _b("START_PLUGIN_SNIPER", "false"):
        return

    res = await call(
        "start_sniper",
        {"capital": _f(os.getenv("SNIPER_CAPITAL", "100"), 100)},
    )
    PLUGIN_SNIPER_STARTED = True
    log_event(f"[AUTO] existing sniper plugin start: {res}")


async def _fetch_pump_candidates() -> list[dict]:
    limit = _i(os.getenv("SNIPER_LIMIT", "10"), 10)
    max_age = _i(os.getenv("SNIPER_MAX_AGE_SEC", "180"), 180)

    res = await call("pump_candidates", {"limit": limit, "max_age_sec": max_age})
    if isinstance(res, dict) and not res.get("error"):
        candidates = res.get("candidates") or res.get("tokens") or res.get("results") or []
        if candidates:
            return [x for x in candidates if isinstance(x, dict)]

    latest = await call("pump_latest", {"limit": max(limit, 20)})
    if isinstance(latest, dict) and not latest.get("error"):
        rows = latest.get("tokens") or []
        out = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            age = _i(row.get("age_sec", 999999), 999999)
            if age > max_age:
                continue
            out.append(
                {
                    "mint": row.get("mint"),
                    "symbol": row.get("symbol") or row.get("mint"),
                    "name": row.get("name"),
                    "age_sec": age,
                    "alpha_score": 0.72 if age <= max_age else 0.0,
                    "source": "pump_latest_fallback",
                }
            )
        if out:
            return out[:limit]

    log_event(f"[PUMP] no candidates: {res}")
    return []


async def _fetch_dex_candidates() -> list[dict]:
    """
    Dexscreener fallback.
    不靠 pump.fun，避免 Railway IP 被 Cloudflare 530 擋。
    """
    query = os.getenv("DEX_SEARCH_QUERY", "SOL")
    url = os.getenv(
        "DEXSCREENER_URL",
        f"https://api.dexscreener.com/latest/dex/search?q={query}",
    )

    limit = _i(os.getenv("SNIPER_LIMIT", "10"), 10)
    min_liq = _f(os.getenv("DEX_MIN_LIQ_USD", os.getenv("EARLY_MIN_LIQ_USD", "10000")), 10000)
    min_vol = _f(os.getenv("DEX_MIN_VOL_24H", "20000"), 20000)
    min_score = _f(os.getenv("SNIPER_MIN_SCORE", os.getenv("MIN_SCORE", "0.70")), 0.70)

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        log_event(f"[DEX] fetch failed: {e}")
        return []

    pairs = data.get("pairs") or []
    out: list[dict] = []

    for p in pairs:
        if not isinstance(p, dict):
            continue

        base = p.get("baseToken") or {}
        quote = p.get("quoteToken") or {}

        mint = base.get("address")
        symbol = base.get("symbol") or mint

        if not mint:
            continue

        # 避免買到 SOL 自己或 USDC 類 quote/base
        if mint == SOL_MINT:
            continue

        liquidity = _f((p.get("liquidity") or {}).get("usd"), 0.0)
        volume_24h = _f((p.get("volume") or {}).get("h24"), 0.0)
        price_change_h1 = _f((p.get("priceChange") or {}).get("h1"), 0.0)
        price_change_m5 = _f((p.get("priceChange") or {}).get("m5"), 0.0)
        txns = p.get("txns") or {}
        buys = _i((txns.get("h1") or {}).get("buys"), 0)
        sells = _i((txns.get("h1") or {}).get("sells"), 0)

        if liquidity < min_liq:
            continue
        if volume_24h < min_vol:
            continue

        buy_pressure = buys / max(buys + sells, 1)

        # 簡單可解釋 score：流動性、量、短線動能、買壓
        liq_score = min(liquidity / 50000, 1.0)
        vol_score = min(volume_24h / 100000, 1.0)
        mom_score = max(min((price_change_m5 + price_change_h1) / 100, 1.0), -1.0)
        pressure_score = buy_pressure

        score = (
            liq_score * 0.30
            + vol_score * 0.30
            + max(mom_score, 0.0) * 0.20
            + pressure_score * 0.20
        )

        if score < min_score:
            continue

        out.append(
            {
                "mint": mint,
                "symbol": symbol,
                "name": base.get("name") or symbol,
                "price": _f(p.get("priceUsd"), 0.0),
                "liquidity": liquidity,
                "volume": volume_24h,
                "price_change_m5": price_change_m5,
                "price_change_h1": price_change_h1,
                "buys_h1": buys,
                "sells_h1": sells,
                "alpha_score": score,
                "source": "dexscreener",
                "pair_url": p.get("url"),
                "dex_id": p.get("dexId"),
                "quote_symbol": quote.get("symbol"),
            }
        )

    out.sort(key=lambda x: x.get("alpha_score", 0), reverse=True)
    log_event(f"[DEX] candidates={len(out)} min_liq={min_liq} min_vol={min_vol}")
    return out[:limit]


async def _fetch_candidates() -> list[dict]:
    """
    主候選入口：
    1. 如果 ENABLE_PUMP_SNIPER=true，先試 pump
    2. 如果 pump 失敗或關閉，走 DEX fallback
    """
    if _b("ENABLE_PUMP_SNIPER", "false"):
        pump = await _fetch_pump_candidates()
        if pump:
            return pump

    if _b("ENABLE_DEX_SNIPER", "true"):
        dex = await _fetch_dex_candidates()
        if dex:
            return dex

    log_event("[SCAN] no candidates from pump/dex")
    return []


async def _quote_ok(mint: str, size_sol: float) -> tuple[bool, str]:
    """
    用 Jupiter quote 做成交可行性檢查。
    REAL/PAPER 都可以跑，避免買沒路由或 price impact 太高的幣。
    """
    if not _b("ENABLE_JUPITER_QUOTE_CHECK", "true"):
        return True, "quote_check_disabled"

    amount_lamports = int(size_sol * 1_000_000_000)
    max_impact = _f(os.getenv("MAX_PRICE_IMPACT", os.getenv("EARLY_MAX_IMPACT", "0.15")), 0.15)
    slippage_bps = _i(os.getenv("SLIPPAGE_BPS", "80"), 80)

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                os.getenv("JUP_QUOTE_URL", "https://quote-api.jup.ag/v6/quote"),
                params={
                    "inputMint": SOL_MINT,
                    "outputMint": mint,
                    "amount": amount_lamports,
                    "slippageBps": slippage_bps,
                },
            )
            r.raise_for_status()
            q = r.json()
    except Exception as e:
        return False, f"quote_error:{e}"

    out_amount = _f(q.get("outAmount"), 0.0)
    impact = _f(q.get("priceImpactPct"), 1.0)

    if out_amount <= 0:
        return False, "quote_no_out_amount"

    if impact > max_impact:
        return False, f"price_impact_high:{impact:.4f}>{max_impact:.4f}"

    return True, f"quote_ok impact={impact:.4f}"


async def _risk_and_alpha_ok(c: dict, size: float) -> tuple[bool, str, float]:
    mint = c.get("mint") or c.get("asset_id") or c.get("symbol")
    score = _f(c.get("alpha_score", c.get("score", 0.0)), 0.0)
    min_score = _f(os.getenv("SNIPER_MIN_SCORE", os.getenv("MIN_SCORE", "0.70")), 0.70)

    if not mint:
        return False, "missing_mint", score

    if score < min_score:
        return False, f"score_low:{score:.3f}<{min_score:.3f}", score

    quote_ok, quote_reason = await _quote_ok(mint, size)
    if not quote_ok:
        return False, quote_reason, score

    rug = await call("rug_check", {"asset_id": mint, "symbol": mint})
    if isinstance(rug, dict) and not rug.get("error"):
        if rug.get("allowed") is False:
            return False, "rug_blocked", score
        if _f(rug.get("score", 0.0), 0.0) > _f(os.getenv("MAX_RUG_SCORE", "0.80"), 0.80):
            return False, "rug_score_high", score

    risk = await call("check_risk", {"asset_id": mint, "symbol": mint, "size": size})
    if isinstance(risk, dict) and not risk.get("error"):
        if risk.get("allowed") is False:
            return False, f"risk_blocked:{risk}", score

    return True, "ok", score


async def sniper_cycle():
    if state.get("kill"):
        log_event("[SNIPER] kill switch active; skip")
        return

    candidates = await _fetch_candidates()
    size = _trade_size()

    for c in candidates:
        mint = c.get("mint") or c.get("asset_id") or c.get("symbol")
        if not mint:
            continue

        # 同一輪生命周期不重複打同一 mint
        if mint in SEEN_MINTS:
            continue
        SEEN_MINTS.add(mint)

        ok, reason, score = await _risk_and_alpha_ok(c, size)
        if not ok:
            log_event(f"[SNIPER] skip {str(mint)[:8]} reason={reason}")
            continue

        log_event(
            f"[SNIPER] BUY_SIGNAL {c.get('symbol', mint)} "
            f"mint={mint} score={score:.3f} size={size} mode={_mode()} source={c.get('source')}"
        )

        payload = {
            "symbol": mint,
            "side": "buy",
            "size": size,
            "slippage_bps": _i(os.getenv("SLIPPAGE_BPS", "80"), 80),
            "confirm": not _b("MANUAL_CONFIRM", "true"),
            "reason": f"sniper source={c.get('source')} score={score:.3f}",
        }

        if not _b("REAL_TRADING", "false"):
            res = {"success": True, "paper": True, "message": "REAL_TRADING=false; not sent"}
        elif _b("MANUAL_CONFIRM", "true"):
            res = {"success": True, "waiting_manual_confirm": True, "payload": payload}
        else:
            res = await call("trade_order", payload)

        trades = state.setdefault("trade_history", [])
        trades.append({"ts": int(time.time()), "payload": payload, "candidate": c, "result": res})
        if len(trades) > 200:
            del trades[:-200]

        log_event(f"[SNIPER] trade_order result: {res}")


async def auto_runtime_loop():
    state["running"] = True
    state["mode"] = _mode()
    state.setdefault("logs", [])
    state.setdefault("positions", [])
    state.setdefault("trade_history", [])

    log_event(f"[AUTO] original-core runtime started mode={state['mode']}")

    while state.get("running", True):
        try:
            state["mode"] = _mode()
            await _start_existing_plugin_sniper_once()

            if _b("ENABLE_SNIPER", "true"):
                await sniper_cycle()

            if _b("RUN_FUND_CYCLE", "false"):
                res = await call("run_fund_cycle", {})
                log_event(f"[AUTO] fund_cycle: {res}")

            await asyncio.sleep(
                _f(os.getenv("TRADING_INTERVAL_SEC", os.getenv("SNIPER_SCAN_INTERVAL", "2")), 2.0)
            )

        except asyncio.CancelledError:
            break
        except Exception as e:
            log_event(f"[AUTO_ERROR] {e}")
            await asyncio.sleep(5)

    state["running"] = False
    log_event("[AUTO] original-core runtime stopped")


def start_runtime() -> bool:
    global TASK

    if TASK and not TASK.done():
        state["running"] = True
        return False

    TASK = asyncio.create_task(auto_runtime_loop())
    return True


def stop_runtime():
    global TASK

    state["running"] = False

    if TASK and not TASK.done():
        TASK.cancel()

    TASK = None
