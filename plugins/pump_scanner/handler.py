from __future__ import annotations

import time
from typing import Any

import httpx

from app.utils.loader import call


PUMP_API = "https://frontend-api.pump.fun/coins/latest"


def _f(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _i(x: Any, default: int = 0) -> int:
    try:
        return int(x)
    except Exception:
        return default


def _normalize_token(row: dict) -> dict:
    mint = row.get("mint") or row.get("address") or ""
    symbol = row.get("symbol") or ""
    name = row.get("name") or symbol or mint[:6]
    created_raw = row.get("created_timestamp") or row.get("created") or row.get("createdAt") or 0

    created_ts = _f(created_raw, 0.0)
    if created_ts > 1e12:
        created_ts = created_ts / 1000.0

    now = time.time()
    age_sec = max(0, int(now - created_ts)) if created_ts > 0 else 999999

    return {
        "mint": mint,
        "symbol": symbol,
        "name": name,
        "created_ts": created_ts,
        "age_sec": age_sec,
        "source": "pumpfun",
        "raw": row,
    }


async def _fetch_latest_rows(limit: int = 20) -> list[dict]:
    async with httpx.AsyncClient(timeout=6) as client:
        res = await client.get(PUMP_API)
        res.raise_for_status()
        data = res.json()

    if not isinstance(data, list):
        return []

    rows = [_normalize_token(x) for x in data[:max(1, limit)]]
    return rows


async def _candidate_score(token: dict) -> dict:
    """
    對單一 token 做早期 alpha 過濾：
    1. token resolver
    2. smart money
    3. rug guard
    4. regime（選填）
    """
    symbol = token.get("symbol") or token.get("mint")
    mint = token.get("mint")

    # token resolver（讓後續 execution 能接）
    resolved = await call("resolve_token", {"symbol": mint or symbol})

    # smart money
    smart = await call("get_smart_money_score", {
        "symbol": symbol,
        "asset_id": mint or symbol
    })

    # rug guard
    rug = await call("rug_check", {
        "symbol": symbol,
        "asset_id": mint or symbol
    })

    # regime（可選，不是每個新幣都查得到）
    regime = await call("get_market_regime", {"symbol": symbol})
    if not isinstance(regime, dict) or "error" in regime:
        regime = {"regime": "unknown", "confidence": 0.0}

    smart_score = _f(smart.get("score", 0.0), 0.0) if isinstance(smart, dict) else 0.0
    smart_direction = str(smart.get("direction", "hold")).lower() if isinstance(smart, dict) else "hold"

    rug_score = _f(rug.get("score", 1.0), 1.0) if isinstance(rug, dict) else 1.0
    rug_allowed = bool(rug.get("allowed", False)) if isinstance(rug, dict) else False

    regime_name = str(regime.get("regime", "unknown"))
    regime_conf = _f(regime.get("confidence", 0.0), 0.0)

    # 基本 early-alpha 分數
    alpha_score = smart_score * 0.7 + max(0.0, 1.0 - rug_score) * 0.3

    # regime 微調
    if regime_name == "trend":
        alpha_score *= 1.05
    elif regime_name == "risk_off":
        alpha_score *= 0.6

    alpha_score = min(max(alpha_score, 0.0), 1.0)

    # early entry 判斷
    early_ok = rug_allowed and rug_score <= 0.70 and smart_score >= 0.55

    return {
        "symbol": token.get("symbol"),
        "mint": token.get("mint"),
        "name": token.get("name"),
        "created_ts": token.get("created_ts"),
        "age_sec": token.get("age_sec"),
        "source": token.get("source"),
        "resolved": resolved if isinstance(resolved, dict) else {},
        "smart_money": {
            "score": round(smart_score, 4),
            "direction": smart_direction,
        },
        "rug_guard": {
            "allowed": rug_allowed,
            "score": round(rug_score, 4),
        },
        "regime": {
            "regime": regime_name,
            "confidence": round(regime_conf, 4),
        },
        "alpha_score": round(alpha_score, 4),
        "early_ok": early_ok,
    }


# =========================
# TOOLS
# =========================

async def pump_latest(limit: int = 20, **kwargs):
    try:
        limit = max(1, _i(limit, 20))
        rows = await _fetch_latest_rows(limit=limit)

        return {
            "tokens": rows,
            "count": len(rows),
            "source": "pumpfun"
        }
    except Exception as e:
        return {"error": str(e)}


async def pump_candidates(limit: int = 10, max_age_sec: int = 180, **kwargs):
    """
    取最新 pump 幣後，做 early alpha 過濾
    """
    try:
        fetch_n = max(limit * 3, 20)
        rows = await _fetch_latest_rows(limit=fetch_n)

        max_age_sec = max(10, _i(max_age_sec, 180))

        # 只留比較新的
        fresh = [x for x in rows if _i(x.get("age_sec", 999999), 999999) <= max_age_sec]

        scored = []
        for row in fresh:
            try:
                scored.append(await _candidate_score(row))
            except Exception:
                continue

        # 過濾
        filtered = [
            x for x in scored
            if x.get("early_ok") is True
        ]

        # 排序：alpha_score 高、越新越前
        filtered.sort(
            key=lambda x: (
                _f(x.get("alpha_score", 0.0), 0.0),
                -_i(x.get("age_sec", 999999), 999999)
            ),
            reverse=True
        )

        out = filtered[:max(1, _i(limit, 10))]

        return {
            "candidates": out,
            "count": len(out),
            "scanned": len(rows),
            "fresh_considered": len(fresh),
            "source": "pumpfun"
        }

    except Exception as e:
        return {"error": str(e)}
