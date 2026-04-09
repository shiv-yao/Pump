import os
import asyncio
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx


HELIUS_API_KEY = os.getenv("HELIUS_API_KEY", "").strip()
HELIUS_RPC_URL = os.getenv(
    "HELIUS_RPC_URL",
    f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}" if HELIUS_API_KEY else "",
).strip()
HELIUS_REST_URL = os.getenv(
    "HELIUS_REST_URL",
    "https://api.helius.xyz",
).strip()

HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "12"))
TRACK_SMART_LIMIT = int(os.getenv("TRACK_SMART_LIMIT", "12"))
TOKEN_HOLDER_SCAN_LIMIT = int(os.getenv("TOKEN_HOLDER_SCAN_LIMIT", "60"))
TOKEN_HOLDER_MIN_UI = float(os.getenv("TOKEN_HOLDER_MIN_UI", "1"))
WALLET_MIN_TOTAL_USD = float(os.getenv("WALLET_MIN_TOTAL_USD", "1000"))
WALLET_MIN_TOKEN_USD = float(os.getenv("WALLET_MIN_TOKEN_USD", "150"))
WALLET_MIN_TOKEN_RATIO = float(os.getenv("WALLET_MIN_TOKEN_RATIO", "0.03"))
HELIUS_PAGE_SIZE = int(os.getenv("HELIUS_PAGE_SIZE", "100"))

# 允許你用 env 指定固定 smart wallets，逗號分隔
STATIC_SMART_WALLETS = [
    x.strip()
    for x in os.getenv("STATIC_SMART_WALLETS", "").split(",")
    if x.strip()
]


# =========================================================
# INTERNAL STATE
# =========================================================

TOKEN_WALLETS: Dict[str, List[Dict[str, Any]]] = {}
WALLET_SCORES: Dict[str, float] = {}
TOKEN_LAST_REFRESH: Dict[str, float] = {}

_REFRESH_LOCKS: Dict[str, asyncio.Lock] = {}
_REFRESH_TTL_SEC = int(os.getenv("HELIUS_TRACKER_TTL_SEC", "45"))


# =========================================================
# HELPERS
# =========================================================

def _now_loop_time() -> float:
    try:
        return asyncio.get_running_loop().time()
    except Exception:
        return 0.0


def _sf(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _wallet_api_url(wallet: str) -> str:
    if HELIUS_API_KEY:
        return f"{HELIUS_REST_URL}/v1/wallet/{wallet}/balances?api-key={HELIUS_API_KEY}"
    return f"{HELIUS_REST_URL}/v1/wallet/{wallet}/balances"


def _has_helius() -> bool:
    return bool(HELIUS_API_KEY)


def _token_matches(entry: Dict[str, Any], mint: str) -> bool:
    possible = {
        str(entry.get("address") or "").strip(),
        str(entry.get("mint") or "").strip(),
        str(entry.get("tokenAddress") or "").strip(),
        str((entry.get("rawBalance") or {}).get("mint") or "").strip(),
    }
    return mint in possible


def _score_wallet(
    total_usd: float,
    token_usd: float,
    token_ratio: float,
    token_amount: float,
    has_price: bool,
) -> float:
    score = 0.0

    if total_usd >= 100_000:
        score += 0.45
    elif total_usd >= 25_000:
        score += 0.34
    elif total_usd >= 10_000:
        score += 0.26
    elif total_usd >= WALLET_MIN_TOTAL_USD:
        score += 0.16

    if token_usd >= 10_000:
        score += 0.28
    elif token_usd >= 2_500:
        score += 0.20
    elif token_usd >= 500:
        score += 0.12
    elif token_usd >= WALLET_MIN_TOKEN_USD:
        score += 0.08

    if token_ratio >= 0.35:
        score += 0.20
    elif token_ratio >= 0.15:
        score += 0.14
    elif token_ratio >= WALLET_MIN_TOKEN_RATIO:
        score += 0.08

    if token_amount > 0:
        score += 0.04

    if has_price:
        score += 0.03

    return _clamp(score, 0.0, 1.0)


def _is_candidate_wallet(total_usd: float, token_usd: float, token_ratio: float) -> bool:
    if total_usd >= WALLET_MIN_TOTAL_USD and token_usd >= WALLET_MIN_TOKEN_USD:
        return True
    if token_ratio >= WALLET_MIN_TOKEN_RATIO and token_usd > 0:
        return True
    return False


def _extract_total_usd(payload: Dict[str, Any]) -> float:
    # Wallet API beta 格式可能變動，做寬鬆兼容
    candidates = [
        payload.get("totalUsdValue"),
        payload.get("total_usd_value"),
        payload.get("portfolioValueUsd"),
        payload.get("portfolio_value_usd"),
        (payload.get("nativeBalance") or {}).get("usdValue"),
        (payload.get("summary") or {}).get("totalUsdValue"),
    ]
    best = 0.0
    for c in candidates:
        best = max(best, _sf(c, 0.0))
    return best


def _extract_tokens_list(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    for key in ("tokens", "tokenBalances", "fungibleTokens", "balances", "items"):
        val = payload.get(key)
        if isinstance(val, list):
            return val
    return []


def _extract_token_info_from_wallet_payload(payload: Dict[str, Any], mint: str) -> Optional[Dict[str, Any]]:
    tokens = _extract_tokens_list(payload)
    for t in tokens:
        if not isinstance(t, dict):
            continue
        if not _token_matches(t, mint):
            continue

        amount = _sf(
            t.get("amount")
            or t.get("uiAmount")
            or t.get("balance")
            or (t.get("rawBalance") or {}).get("tokenAmount")
            or (t.get("rawBalance") or {}).get("uiAmount")
            or (t.get("rawBalance") or {}).get("uiAmountString"),
            0.0,
        )

        usd_value = _sf(
            t.get("usdValue")
            or t.get("valueUsd")
            or t.get("usd_value")
            or (t.get("priceInfo") or {}).get("valueUsd")
            or (t.get("priceInfo") or {}).get("usdValue"),
            0.0,
        )

        price_usd = _sf(
            t.get("priceUsd")
            or (t.get("priceInfo") or {}).get("priceUsd")
            or (t.get("tokenPrice") or {}).get("usd"),
            0.0,
        )

        return {
            "mint": mint,
            "token_amount": amount,
            "token_usd": usd_value,
            "token_price_usd": price_usd,
            "has_price": price_usd > 0 or usd_value > 0,
        }
    return None


# =========================================================
# HTTP
# =========================================================

async def _http_get(url: str) -> Optional[Dict[str, Any]]:
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            r = await client.get(url)
            r.raise_for_status()
            data = r.json()
            return data if isinstance(data, dict) else {"data": data}
    except Exception:
        return None


async def _http_post(url: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            r = await client.post(url, json=payload)
            r.raise_for_status()
            data = r.json()
            return data if isinstance(data, dict) else {"data": data}
    except Exception:
        return None


# =========================================================
# HELIUS WALLET API
# =========================================================

async def _fetch_wallet_balances(wallet: str) -> Optional[Dict[str, Any]]:
    if not _has_helius():
        return None
    return await _http_get(_wallet_api_url(wallet))


async def _inspect_wallet_for_token(wallet: str, mint: str) -> Optional[Dict[str, Any]]:
    payload = await _fetch_wallet_balances(wallet)
    if not payload:
        return None

    total_usd = _extract_total_usd(payload)
    token_info = _extract_token_info_from_wallet_payload(payload, mint)
    if not token_info:
        return None

    token_usd = _sf(token_info.get("token_usd"), 0.0)
    token_amount = _sf(token_info.get("token_amount"), 0.0)
    has_price = bool(token_info.get("has_price"))
    token_ratio = token_usd / total_usd if total_usd > 0 else 0.0

    if not _is_candidate_wallet(total_usd, token_usd, token_ratio):
        return None

    score = _score_wallet(
        total_usd=total_usd,
        token_usd=token_usd,
        token_ratio=token_ratio,
        token_amount=token_amount,
        has_price=has_price,
    )

    return {
        "wallet": wallet,
        "score": score,
        "total_usd": total_usd,
        "token_usd": token_usd,
        "token_ratio": token_ratio,
        "token_amount": token_amount,
        "source": "helius_wallet_api",
    }


# =========================================================
# HELIUS DAS FALLBACK
# =========================================================

async def _das_get_token_accounts(owner: str, page: int = 1, limit: int = 100) -> Optional[Dict[str, Any]]:
    if not HELIUS_RPC_URL:
        return None

    payload = {
        "jsonrpc": "2.0",
        "id": f"getTokenAccounts-{owner}-{page}",
        "method": "getTokenAccounts",
        "params": {
            "owner": owner,
            "page": page,
            "limit": limit,
        },
    }
    return await _http_post(HELIUS_RPC_URL, payload)


async def _das_wallet_holds_mint(wallet: str, mint: str) -> Optional[Dict[str, Any]]:
    # 只檢查有沒有持有 + 數量，不含 USD；給 fallback 用
    page = 1
    total_amount = 0.0
    found = False

    while page <= 5:
        resp = await _das_get_token_accounts(wallet, page=page, limit=100)
        result = (resp or {}).get("result") or {}
        items = result.get("token_accounts") or result.get("items") or []
        if not items:
            break

        for it in items:
            account = it.get("account") or {}
            token_info = account.get("token_info") or it.get("token_info") or {}
            it_mint = (
                token_info.get("mint")
                or it.get("mint")
                or ((it.get("content") or {}).get("metadata") or {}).get("mint")
            )
            if it_mint != mint:
                continue

            amount = _sf(
                token_info.get("balance")
                or token_info.get("amount")
                or token_info.get("ui_amount")
                or token_info.get("uiAmount"),
                0.0,
            )
            total_amount += amount
            found = True

        if len(items) < 100:
            break
        page += 1

    if not found or total_amount < TOKEN_HOLDER_MIN_UI:
        return None

    score = _score_wallet(
        total_usd=0.0,
        token_usd=0.0,
        token_ratio=0.0,
        token_amount=total_amount,
        has_price=False,
    ) * 0.45

    return {
        "wallet": wallet,
        "score": score,
        "total_usd": 0.0,
        "token_usd": 0.0,
        "token_ratio": 0.0,
        "token_amount": total_amount,
        "source": "helius_das_fallback",
    }


# =========================================================
# DISCOVERY
# =========================================================

async def _discover_candidate_wallets_from_env() -> List[str]:
    return STATIC_SMART_WALLETS[:TOKEN_HOLDER_SCAN_LIMIT]


async def _discover_candidate_wallets_from_engine(mint: str) -> List[str]:
    candidates: List[str] = []

    try:
        positions = getattr(engine, "positions", []) or []
        trade_history = getattr(engine, "trade_history", []) or []
    except Exception:
        positions = []
        trade_history = []

    for p in positions:
        meta = p.get("meta", {}) if isinstance(p, dict) else {}
        for key in ("wallet", "owner", "trader", "smart_wallet"):
            w = meta.get(key)
            if isinstance(w, str) and len(w) >= 32:
                candidates.append(w)

    for tr in trade_history[-200:]:
        if not isinstance(tr, dict):
            continue
        meta = tr.get("meta", {}) or {}
        for key in ("wallet", "owner", "trader", "smart_wallet"):
            w = meta.get(key)
            if isinstance(w, str) and len(w) >= 32:
                candidates.append(w)

    # 去重保序
    out: List[str] = []
    seen: Set[str] = set()
    for w in candidates:
        if w in seen:
            continue
        seen.add(w)
        out.append(w)

    return out[:TOKEN_HOLDER_SCAN_LIMIT]


async def _discover_candidate_wallets(mint: str) -> List[str]:
    # 你之後如果有 wallet graph / top holders source，可以接在這裡
    wallets: List[str] = []

    env_wallets = await _discover_candidate_wallets_from_env()
    engine_wallets = await _discover_candidate_wallets_from_engine(mint)

    for group in (env_wallets, engine_wallets):
        for w in group:
            if w not in wallets:
                wallets.append(w)

    return wallets[:TOKEN_HOLDER_SCAN_LIMIT]


# =========================================================
# PUBLIC API
# =========================================================

async def update_token_wallets(mint: str) -> List[Dict[str, Any]]:
    """
    回傳格式範例:
    [
        {
            "wallet": "...",
            "score": 0.73,
            "total_usd": 15432.1,
            "token_usd": 912.0,
            "token_ratio": 0.059,
            "token_amount": 120340.0,
            "source": "helius_wallet_api"
        }
    ]
    """
    if not mint:
        return []

    ttl = TOKEN_LAST_REFRESH.get(mint, 0.0)
    now_ts = _now_loop_time()
    if mint in TOKEN_WALLETS and now_ts and (now_ts - ttl) < _REFRESH_TTL_SEC:
        return TOKEN_WALLETS[mint]

    lock = _REFRESH_LOCKS.setdefault(mint, asyncio.Lock())
    async with lock:
        ttl = TOKEN_LAST_REFRESH.get(mint, 0.0)
        now_ts = _now_loop_time()
        if mint in TOKEN_WALLETS and now_ts and (now_ts - ttl) < _REFRESH_TTL_SEC:
            return TOKEN_WALLETS[mint]

        candidate_wallets = await _discover_candidate_wallets(mint)
        if not candidate_wallets:
            TOKEN_WALLETS[mint] = []
            TOKEN_LAST_REFRESH[mint] = _now_loop_time()
            return []

        results: List[Dict[str, Any]] = []

        async def inspect_one(wallet: str) -> Optional[Dict[str, Any]]:
            # 優先 wallet api
            row = await _inspect_wallet_for_token(wallet, mint)
            if row:
                return row
            # fallback DAS
            return await _das_wallet_holds_mint(wallet, mint)

        inspected = await asyncio.gather(
            *(inspect_one(w) for w in candidate_wallets),
            return_exceptions=True,
        )

        for row in inspected:
            if isinstance(row, Exception) or not row:
                continue
            wallet = row["wallet"]
            prev = WALLET_SCORES.get(wallet, 0.0)
            WALLET_SCORES[wallet] = max(prev, _sf(row.get("score"), 0.0))
            results.append(row)

        results.sort(
            key=lambda x: (
                _sf(x.get("score"), 0.0),
                _sf(x.get("token_usd"), 0.0),
                _sf(x.get("total_usd"), 0.0),
                _sf(x.get("token_amount"), 0.0),
            ),
            reverse=True,
        )

        results = results[:TRACK_SMART_LIMIT]
        TOKEN_WALLETS[mint] = results
        TOKEN_LAST_REFRESH[mint] = _now_loop_time()
        return results


def get_wallet_score(wallet: str) -> float:
    return _sf(WALLET_SCORES.get(wallet, 0.0), 0.0)


def get_token_wallets(mint: str) -> List[Dict[str, Any]]:
    return TOKEN_WALLETS.get(mint, [])


def clear_wallet_tracker_cache(mint: Optional[str] = None) -> None:
    if mint:
        TOKEN_WALLETS.pop(mint, None)
        TOKEN_LAST_REFRESH.pop(mint, None)
        _REFRESH_LOCKS.pop(mint, None)
        return

    TOKEN_WALLETS.clear()
    TOKEN_LAST_REFRESH.clear()
    _REFRESH_LOCKS.clear()
    WALLET_SCORES.clear()


async def warm_token_wallets(mints: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    mints = [m for m in mints if m]
    if not mints:
        return {}

    rows = await asyncio.gather(
        *(update_token_wallets(m) for m in mints),
        return_exceptions=True,
    )

    out: Dict[str, List[Dict[str, Any]]] = {}
    for mint, row in zip(mints, rows):
        if isinstance(row, Exception):
            out[mint] = []
        else:
            out[mint] = row
    return out
