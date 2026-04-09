import os
import asyncio
import time
import random
import json
from collections import defaultdict, Counter

import httpx
import websockets

from app.state import engine
from app.alpha.adaptive_filter import adaptive_filter
from app.execution.jupiter_exec import execute_swap
from app.data.market import get_quote
from app.alpha.helius_wallet_tracker import update_token_wallets
from app.config import SOL_MINT as SOL, SOL_DECIMALS, HTTP_TIMEOUT, BIRDEYE_API_KEY, REAL_TRADING


# =========================================================
# CONFIG
# =========================================================

AMOUNT = int(os.getenv("AMOUNT", "1000000"))
MAX_POSITIONS = int(os.getenv("MAX_POSITIONS", "2"))
MAX_EXPOSURE = float(os.getenv("MAX_EXPOSURE", "0.35"))
MAX_POSITION_SIZE = float(os.getenv("MAX_POSITION_SIZE", "0.03"))

TAKE_PROFIT = float(os.getenv("TAKE_PROFIT", "0.024"))
STOP_LOSS = float(os.getenv("STOP_LOSS", "-0.013"))
TRAILING_GAP = float(os.getenv("TRAILING_GAP", "0.01"))
MAX_HOLD_SEC = int(os.getenv("MAX_HOLD_SEC", "120"))

HARD_STOP_LOSS = float(os.getenv("HARD_STOP_LOSS", "-0.020"))
FORCE_EXIT_SEC = int(os.getenv("FORCE_EXIT_SEC", "90"))

TOKEN_COOLDOWN = int(os.getenv("TOKEN_COOLDOWN", "15"))
BLACKLIST_TIME = int(os.getenv("BLACKLIST_TIME", "60"))
FORCE_TRADE_AFTER = int(os.getenv("FORCE_TRADE_AFTER", "120"))
LOOP_SLEEP_SEC = float(os.getenv("LOOP_SLEEP_SEC", "2"))

ENTRY_THRESHOLD = float(os.getenv("ENTRY_THRESHOLD", "0.11"))
FILTER_SCORE_BYPASS = float(os.getenv("FILTER_SCORE_BYPASS", "0.12"))
SOFT_DISABLE_FILTER = os.getenv("SOFT_DISABLE_FILTER", "false").lower() == "true"

MIN_ORDER_SOL = float(os.getenv("MIN_ORDER_SOL", "0.01"))

MAX_PRICE_JUPITER = float(os.getenv("MAX_PRICE_JUPITER", "0.1"))
MAX_PRICE_FALLBACK = float(os.getenv("MAX_PRICE_FALLBACK", "10"))

MIN_LIQUIDITY_TRADE = float(os.getenv("MIN_LIQUIDITY_TRADE", "20000"))
MIN_LIQUIDITY_OBSERVE = float(os.getenv("MIN_LIQUIDITY_OBSERVE", "3000"))

MAX_BREAKOUT_ABS = float(os.getenv("MAX_BREAKOUT_ABS", "0.20"))
MAX_SCORE = float(os.getenv("MAX_SCORE", "1.5"))
MAX_PNL_ABS = float(os.getenv("MAX_PNL_ABS", "0.2"))
MAX_CAPITAL = float(os.getenv("MAX_CAPITAL", "20"))

MIN_OUT_AMOUNT = int(os.getenv("MIN_OUT_AMOUNT", "300"))
MIN_UNIVERSE = int(os.getenv("MIN_UNIVERSE", "20"))
BOOT_SYNTHETIC_UNIVERSE = os.getenv("BOOT_SYNTHETIC_UNIVERSE", "true").lower() == "true"

ADAPTIVE_THRESHOLD_MIN = float(os.getenv("ADAPTIVE_THRESHOLD_MIN", "0.04"))
ADAPTIVE_THRESHOLD_MAX = float(os.getenv("ADAPTIVE_THRESHOLD_MAX", "0.10"))

TOP_N_TO_TRADE = int(os.getenv("TOP_N_TO_TRADE", "1"))
MAX_TOKENS_PER_CYCLE = int(os.getenv("MAX_TOKENS_PER_CYCLE", "80"))
TOP_K_PRESELECT = int(os.getenv("TOP_K_PRESELECT", "3"))

MEMPOOL_WSS = os.getenv("MEMPOOL_WSS", "wss://api.mainnet-beta.solana.com")

MIN_CONFIRM_MOMENTUM = float(os.getenv("MIN_CONFIRM_MOMENTUM", "0.002"))
MIN_CONFIRM_BREAKOUT = float(os.getenv("MIN_CONFIRM_BREAKOUT", "0.003"))
STRICT_A_TIER_THRESHOLD = float(os.getenv("STRICT_A_TIER_THRESHOLD", "0.095"))

BREATHING_LOSS_STREAK = int(os.getenv("BREATHING_LOSS_STREAK", "2"))
BREATHING_COOLDOWN_SEC = int(os.getenv("BREATHING_COOLDOWN_SEC", "180"))
BREATHING_MIN_RISK_MULT = float(os.getenv("BREATHING_MIN_RISK_MULT", "0.45"))
BREATHING_MAX_RISK_MULT = float(os.getenv("BREATHING_MAX_RISK_MULT", "1.20"))

MAX_NEW_BUYS_PER_CYCLE = int(os.getenv("MAX_NEW_BUYS_PER_CYCLE", "1"))
MAX_BUYS_PER_10MIN = int(os.getenv("MAX_BUYS_PER_10MIN", "8"))
BUY_WINDOW_SEC = int(os.getenv("BUY_WINDOW_SEC", "600"))

ALPHA_BREAKOUT_WEIGHT = float(os.getenv("ALPHA_BREAKOUT_WEIGHT", "0.35"))
ALPHA_MOMENTUM_WEIGHT = float(os.getenv("ALPHA_MOMENTUM_WEIGHT", "0.25"))
ALPHA_SMART_WEIGHT = float(os.getenv("ALPHA_SMART_WEIGHT", "0.25"))
ALPHA_LIQ_WEIGHT = float(os.getenv("ALPHA_LIQ_WEIGHT", "0.10"))
ALPHA_WALLET_WEIGHT = float(os.getenv("ALPHA_WALLET_WEIGHT", "0.05"))

SNIPER_MULTIPLIER = float(os.getenv("SNIPER_MULTIPLIER", "1.30"))
SMART_MULTIPLIER = float(os.getenv("SMART_MULTIPLIER", "1.20"))
MOMENTUM_MULTIPLIER = float(os.getenv("MOMENTUM_MULTIPLIER", "1.00"))

AGENT_UPDATE_SEC = int(os.getenv("AGENT_UPDATE_SEC", "20"))
AGENT_MIN_TRADES = int(os.getenv("AGENT_MIN_TRADES", "5"))
AGENT_LOOKBACK_TRADES = int(os.getenv("AGENT_LOOKBACK_TRADES", "10"))
AGENT_BULL_WINRATE = float(os.getenv("AGENT_BULL_WINRATE", "0.60"))
AGENT_BEAR_WINRATE = float(os.getenv("AGENT_BEAR_WINRATE", "0.35"))
AGENT_RISK_MIN = float(os.getenv("AGENT_RISK_MIN", "0.45"))
AGENT_RISK_MAX = float(os.getenv("AGENT_RISK_MAX", "1.35"))

AGENT_DEFENSIVE_ENTRY = float(os.getenv("AGENT_DEFENSIVE_ENTRY", "0.095"))
AGENT_NORMAL_ENTRY = float(os.getenv("AGENT_NORMAL_ENTRY", "0.085"))
AGENT_AGGRESSIVE_ENTRY = float(os.getenv("AGENT_AGGRESSIVE_ENTRY", "0.078"))

AGENT_DEFENSIVE_TP = float(os.getenv("AGENT_DEFENSIVE_TP", "0.018"))
AGENT_NORMAL_TP = float(os.getenv("AGENT_NORMAL_TP", "0.022"))
AGENT_AGGRESSIVE_TP = float(os.getenv("AGENT_AGGRESSIVE_TP", "0.026"))

AGENT_DEFENSIVE_SL = float(os.getenv("AGENT_DEFENSIVE_SL", "-0.010"))
AGENT_NORMAL_SL = float(os.getenv("AGENT_NORMAL_SL", "-0.012"))
AGENT_AGGRESSIVE_SL = float(os.getenv("AGENT_AGGRESSIVE_SL", "-0.014"))

AGENT_KILL_LOSS_STREAK = int(os.getenv("AGENT_KILL_LOSS_STREAK", "4"))
AGENT_KILL_COOLDOWN_SEC = int(os.getenv("AGENT_KILL_COOLDOWN_SEC", "300"))
AGENT_FORCE_TRADE_ENABLE = os.getenv("AGENT_FORCE_TRADE_ENABLE", "true").lower() == "true"

EXPLORATION_ENABLE = os.getenv("EXPLORATION_ENABLE", "true").lower() == "true"
EXPLORATION_MIN_SCORE = float(os.getenv("EXPLORATION_MIN_SCORE", "0.05"))
EXPLORATION_SIZE_FRAC = float(os.getenv("EXPLORATION_SIZE_FRAC", "0.02"))

DEFAULT_TOKEN_DECIMALS = int(os.getenv("DEFAULT_TOKEN_DECIMALS", "6"))
ESTIMATED_TX_FEE_SOL = float(os.getenv("ESTIMATED_TX_FEE_SOL", "0.000005"))
ENABLE_EQUITY_MARK = os.getenv("ENABLE_EQUITY_MARK", "true").lower() == "true"

WALLET_TRACKER_TIMEOUT_SEC = float(os.getenv("WALLET_TRACKER_TIMEOUT_SEC", "1.2"))
QUOTE_TIMEOUT_RETRY = int(os.getenv("QUOTE_TIMEOUT_RETRY", "3"))
HTTP_GET_RETRY = int(os.getenv("HTTP_GET_RETRY", "2"))

SEARCH_TERMS = [
    "SOL", "USDC", "BONK", "MEME", "PEPE", "DOG", "AI", "PUMP", "NEW", "MOON", "100x"
]
MEME_SEARCH_TERMS = [
    "pumpfun", "pepe", "doge", "meme", "cat", "frog", "moonshot", "100x"
]

JUPITER_PROGRAM_ID = os.getenv(
    "JUPITER_PROGRAM_ID",
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"
)


# =========================================================
# RUNTIME MEMORY
# =========================================================

LAST_TRADE = defaultdict(float)
LAST_PRICE = {}
LAST_MOMENTUM = {}
LAST_PRICE_SOURCE = {}
TOKEN_TRADE_COUNT = defaultdict(int)
BLACKLIST = {}

SOURCE_STATS = defaultdict(lambda: {
    "count": 0,
    "wins": 0,
    "losses": 0,
    "total_pnl": 0.0,
})

STRATEGY_STATS = defaultdict(lambda: {
    "count": 0,
    "wins": 0,
    "losses": 0,
    "total_pnl": 0.0,
})

SCORE_COMPONENT_STATS = defaultdict(lambda: {
    "count": 0,
    "sum": 0.0,
})

BUY_TIMES = []
MEMPOOL_BUFFER = []
MEMPOOL_TASK = None

BREATHING_STATE = {
    "risk_mult": 1.0,
    "cooldown_until": 0.0,
}

REGIME_STATE = {
    "mode": "neutral",
    "last_update": 0.0,
}

AGENT_STATE = {
    "last_update": 0.0,
    "mode": "normal",
    "risk_mult": 1.0,
    "confidence": 0.5,
    "cooldown_until": 0.0,
    "last_reason": "boot",
}

AUTO_PARAMS = {
    "entry_threshold": ENTRY_THRESHOLD,
    "take_profit": TAKE_PROFIT,
    "stop_loss": STOP_LOSS,
}


# =========================================================
# BASIC HELPERS
# =========================================================

def log(x):
    print(x)
    engine.logs.append(str(x))
    engine.logs = engine.logs[-1200:]


def sf(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default


def safe_int(x, default=0):
    try:
        return int(float(x))
    except Exception:
        return default


def now():
    return time.time()


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def exposure():
    return sum(sf(p.get("entry_value", p.get("size", 0.0))) for p in engine.positions)


def update_open_stats():
    engine.stats["open_positions"] = len(engine.positions)
    engine.stats["open_exposure"] = exposure()


async def update_peak_capital():
    eq = await calc_equity() if ENABLE_EQUITY_MARK else sf(engine.capital, 0.0)
    engine.peak_capital = max(sf(engine.peak_capital), sf(eq))


def push_trade(row):
    engine.trade_history.append(row)
    engine.trade_history = engine.trade_history[-1000:]
    engine.stats["trades"] = len(engine.trade_history)


def source_stat_win(src, pnl):
    s = SOURCE_STATS[src]
    s["count"] += 1
    s["wins"] += 1
    s["total_pnl"] += pnl


def source_stat_loss(src, pnl):
    s = SOURCE_STATS[src]
    s["count"] += 1
    s["losses"] += 1
    s["total_pnl"] += pnl


def strategy_stat_update(strategy, pnl):
    s = STRATEGY_STATS[strategy]
    s["count"] += 1
    s["total_pnl"] += pnl
    if pnl > 0:
        s["wins"] += 1
    else:
        s["losses"] += 1


def score_stat_add(name, value):
    s = SCORE_COMPONENT_STATS[name]
    s["count"] += 1
    s["sum"] += sf(value)


def dedup(tokens):
    seen = set()
    out = []
    for t in tokens:
        m = t.get("mint")
        if not m or m in seen:
            continue
        seen.add(m)
        out.append(t)
    return out


def limit_token_frequency(tokens, max_per_token=2):
    count = Counter()
    out = []
    for t in tokens:
        m = t.get("mint")
        if not m:
            continue
        if count[m] >= max_per_token:
            continue
        count[m] += 1
        out.append(t)
    return out


def recent_closed_trades(n=5):
    return [x for x in (getattr(engine, "trade_history", []) or []) if isinstance(x, dict)][-n:]


def extract_token_decimals(meta):
    d = None
    if isinstance(meta, dict):
        d = meta.get("decimals")
    try:
        d = int(d)
    except Exception:
        d = DEFAULT_TOKEN_DECIMALS
    return max(0, min(d, 12))


def safe_div(a, b, default=0.0):
    try:
        if b == 0:
            return default
        return a / b
    except Exception:
        return default


def valid_mint_like(word: str) -> bool:
    return isinstance(word, str) and 32 <= len(word) <= 44 and word.isalnum()


def parse_out_amount(obj):
    if not isinstance(obj, dict):
        return 0
    candidates = [
        obj.get("outAmount"),
        (obj.get("quote") or {}).get("outAmount"),
        (obj.get("order") or {}).get("outAmount"),
        ((obj.get("routePlan") or [{}])[0] or {}).get("swapInfo", {}).get("outAmount"),
    ]
    for x in candidates:
        v = safe_int(x, 0)
        if v > 0:
            return v
    return 0


def parse_signature(obj):
    if not isinstance(obj, dict):
        return None
    candidates = [
        obj.get("signature"),
        obj.get("result"),
        (obj.get("result") or {}).get("signature") if isinstance(obj.get("result"), dict) else None,
    ]
    for x in candidates:
        if isinstance(x, str) and x:
            return x
    return None


# =========================================================
# SAFE WRAPPERS
# =========================================================

async def safe_update_token_wallets(mint: str):
    try:
        return await asyncio.wait_for(update_token_wallets(mint), timeout=WALLET_TRACKER_TIMEOUT_SEC)
    except Exception:
        return []


def safe_adaptive_filter(feature_row, _context=None, _no_trade_cycles=0):
    try:
        ok, meta = adaptive_filter(feature_row, _context, _no_trade_cycles)
        return bool(ok), meta if isinstance(meta, dict) else {}
    except Exception:
        score = sf(feature_row.get("_score", feature_row.get("score", 0.0)), 0.0)
        liq = sf(feature_row.get("liq", 0.0), 0.0)
        breakout = sf(feature_row.get("breakout", 0.0), 0.0)
        ok = score >= 0.08 and liq >= 3_000 and breakout > -0.03
        return ok, {"fallback": True}


async def safe_execute_swap(input_mint: str, output_mint: str, amount: int):
    try:
        res = await execute_swap(input_mint, output_mint, amount)
    except Exception as e:
        return {"error": f"execute_swap_exception: {e}"}

    if not isinstance(res, dict):
        return {"error": "execute_swap_invalid_response"}

    if res.get("paper"):
        q = await safe_quote(input_mint, output_mint, amount)
        out_amount = parse_out_amount(q)
        if out_amount <= 0:
            out_amount = 1
        res["quote"] = dict(res.get("quote") or {})
        res["quote"]["outAmount"] = str(out_amount)
        return res

    return res


# =========================================================
# ENGINE INIT
# =========================================================

def ensure_engine():
    engine.positions = getattr(engine, "positions", [])
    engine.trade_history = getattr(engine, "trade_history", [])
    engine.logs = getattr(engine, "logs", [])

    engine.capital = float(getattr(engine, "capital", 5.0))
    engine.start_capital = float(getattr(engine, "start_capital", engine.capital))
    engine.peak_capital = float(getattr(engine, "peak_capital", engine.capital))

    engine.running = getattr(engine, "running", True)
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
        "fees_paid_sol": 0.0,
        "realized_pnl_sol": 0.0,
        "unrealized_pnl_sol": 0.0,
    }
    for k, v in defaults.items():
        engine.stats.setdefault(k, v)


# =========================================================
# BREATHING / REGIME / AGENT
# =========================================================

def breathing_risk_mult():
    return clamp(
        sf(BREATHING_STATE.get("risk_mult", 1.0), 1.0),
        BREATHING_MIN_RISK_MULT,
        BREATHING_MAX_RISK_MULT,
    )


def update_breathing_state():
    rows = recent_closed_trades(6)
    if not rows:
        BREATHING_STATE["risk_mult"] = 1.0
        return

    last2 = rows[-2:] if len(rows) >= 2 else rows
    streak = 0
    for r in reversed(last2):
        if sf(r.get("pnl"), 0.0) < 0:
            streak += 1
        else:
            break

    if streak >= BREATHING_LOSS_STREAK:
        BREATHING_STATE["risk_mult"] = max(
            BREATHING_MIN_RISK_MULT,
            BREATHING_STATE["risk_mult"] * 0.70
        )
        BREATHING_STATE["cooldown_until"] = now() + BREATHING_COOLDOWN_SEC
        log(f"BREATHING_DE_RISK streak={streak} risk={BREATHING_STATE['risk_mult']:.2f}")
        return

    recent = rows[-3:]
    if recent and all(sf(x.get("pnl"), 0.0) > 0 for x in recent):
        BREATHING_STATE["risk_mult"] = min(
            BREATHING_MAX_RISK_MULT,
            BREATHING_STATE["risk_mult"] + 0.08
        )
        return

    if now() > sf(BREATHING_STATE.get("cooldown_until", 0.0), 0.0):
        BREATHING_STATE["risk_mult"] = min(
            BREATHING_MAX_RISK_MULT,
            BREATHING_STATE["risk_mult"] + 0.03
        )


def detect_regime():
    if now() - sf(REGIME_STATE.get("last_update", 0.0), 0.0) < 15:
        return REGIME_STATE["mode"]

    rows = recent_closed_trades(8)
    if len(rows) < 4:
        REGIME_STATE.update({"mode": "neutral", "last_update": now()})
        return "neutral"

    pnls = [sf(x.get("pnl"), 0.0) for x in rows]
    wins = sum(1 for x in pnls if x > 0)
    avg_pnl = sum(pnls) / max(len(pnls), 1)
    winrate = wins / max(len(pnls), 1)

    mode = "neutral"
    if winrate >= 0.60 and avg_pnl > 0:
        mode = "bull"
    elif winrate <= 0.30 and avg_pnl < 0:
        mode = "bear"

    REGIME_STATE.update({"mode": mode, "last_update": now()})
    return mode


def buy_window_count():
    cutoff = now() - BUY_WINDOW_SEC
    while BUY_TIMES and BUY_TIMES[0] < cutoff:
        BUY_TIMES.pop(0)
    return len(BUY_TIMES)


def agent_in_cooldown():
    return now() < sf(AGENT_STATE.get("cooldown_until", 0.0), 0.0)


def agent_recent_rows():
    return [x for x in recent_closed_trades(AGENT_LOOKBACK_TRADES) if isinstance(x, dict)]


def agent_loss_streak(rows=None):
    rows = rows or agent_recent_rows()
    streak = 0
    for r in reversed(rows):
        if sf(r.get("pnl"), 0.0) < 0:
            streak += 1
        else:
            break
    return streak


def agent_update():
    if now() - sf(AGENT_STATE.get("last_update", 0.0), 0.0) < AGENT_UPDATE_SEC:
        return

    rows = agent_recent_rows()
    if len(rows) < AGENT_MIN_TRADES:
        AGENT_STATE["last_update"] = now()
        AGENT_STATE["last_reason"] = "not_enough_trades"
        return

    pnls = [sf(x.get("pnl"), 0.0) for x in rows]
    wins = sum(1 for x in pnls if x > 0)
    count = len(pnls)
    winrate = wins / count if count else 0.0
    avg_pnl = sum(pnls) / count if count else 0.0
    streak = agent_loss_streak(rows)

    mode = "normal"
    reason = "balanced"

    if streak >= AGENT_KILL_LOSS_STREAK:
        AGENT_STATE["cooldown_until"] = now() + AGENT_KILL_COOLDOWN_SEC
        mode = "defensive"
        reason = f"kill_loss_streak_{streak}"
    elif winrate >= AGENT_BULL_WINRATE and avg_pnl > 0:
        mode = "aggressive"
        reason = "good_recent_performance"
    elif winrate <= AGENT_BEAR_WINRATE and avg_pnl < 0:
        mode = "defensive"
        reason = "bad_recent_performance"

    AGENT_STATE["mode"] = mode
    AGENT_STATE["confidence"] = clamp(winrate if count else 0.5, 0.1, 0.95)

    risk_mult = AGENT_STATE.get("risk_mult", 1.0)
    if mode == "aggressive":
        risk_mult += 0.08
    elif mode == "defensive":
        risk_mult *= 0.82
    else:
        risk_mult += 0.03

    AGENT_STATE["risk_mult"] = clamp(risk_mult, AGENT_RISK_MIN, AGENT_RISK_MAX)
    AGENT_STATE["last_update"] = now()
    AGENT_STATE["last_reason"] = reason


def agent_adjust_params():
    mode = AGENT_STATE.get("mode", "normal")
    if mode == "aggressive":
        AUTO_PARAMS.update({
            "entry_threshold": AGENT_AGGRESSIVE_ENTRY,
            "take_profit": AGENT_AGGRESSIVE_TP,
            "stop_loss": AGENT_AGGRESSIVE_SL,
        })
    elif mode == "defensive":
        AUTO_PARAMS.update({
            "entry_threshold": AGENT_DEFENSIVE_ENTRY,
            "take_profit": AGENT_DEFENSIVE_TP,
            "stop_loss": AGENT_DEFENSIVE_SL,
        })
    else:
        AUTO_PARAMS.update({
            "entry_threshold": AGENT_NORMAL_ENTRY,
            "take_profit": AGENT_NORMAL_TP,
            "stop_loss": AGENT_NORMAL_SL,
        })


def agent_effective_entry_threshold():
    return clamp(
        sf(AUTO_PARAMS.get("entry_threshold", ENTRY_THRESHOLD), ENTRY_THRESHOLD),
        ADAPTIVE_THRESHOLD_MIN,
        0.20,
    )


def agent_effective_tp():
    return sf(AUTO_PARAMS.get("take_profit", TAKE_PROFIT), TAKE_PROFIT)


def agent_effective_sl():
    return sf(AUTO_PARAMS.get("stop_loss", STOP_LOSS), STOP_LOSS)


def agent_force_trade_allowed():
    return (
        AGENT_FORCE_TRADE_ENABLE
        and (not agent_in_cooldown())
        and AGENT_STATE.get("mode") != "defensive"
    )


def current_dynamic_threshold():
    base = agent_effective_entry_threshold()
    regime = detect_regime()

    if regime == "bull":
        base *= 0.94
    elif regime == "bear":
        base *= 1.10

    if engine.no_trade_cycles > 30:
        base *= 0.78
    elif engine.no_trade_cycles > 15:
        base *= 0.90

    if AGENT_STATE.get("mode") == "aggressive":
        base *= 0.96
    elif AGENT_STATE.get("mode") == "defensive":
        base *= 1.05

    return clamp(base, ADAPTIVE_THRESHOLD_MIN, 0.20)


# =========================================================
# SCORE HELPERS
# =========================================================

def breakout_strength(b):
    b = clamp(sf(b), -MAX_BREAKOUT_ABS, MAX_BREAKOUT_ABS)
    if b <= 0:
        return 0.0
    return min(b / 0.05, 1.0) * 0.35


def momentum_strength(m):
    m = clamp(sf(m), -MAX_BREAKOUT_ABS, MAX_BREAKOUT_ABS)
    if m <= 0:
        return 0.0
    return min(m / 0.05, 1.0) * 0.30


# =========================================================
# HTTP / MARKET SOURCES
# =========================================================

async def http_get(url, params=None, headers=None):
    for _ in range(max(1, HTTP_GET_RETRY)):
        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                r = await client.get(url, params=params, headers=headers)
                r.raise_for_status()
                return r.json()
        except Exception:
            await asyncio.sleep(0.15)
    return None


async def mempool_stream():
    while True:
        try:
            async with websockets.connect(MEMPOOL_WSS, ping_interval=20) as ws:
                sub = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "logsSubscribe",
                    "params": [
                        {"mentions": [JUPITER_PROGRAM_ID]},
                        {"commitment": "processed"},
                    ],
                }
                await ws.send(json.dumps(sub))

                while True:
                    msg = await ws.recv()
                    data = json.loads(msg)
                    text = json.dumps(data)
                    for word in text.replace('"', " ").replace(",", " ").split():
                        if valid_mint_like(word):
                            MEMPOOL_BUFFER.append({
                                "mint": word,
                                "source": "mempool",
                                "meta": {},
                            })
                            if len(MEMPOOL_BUFFER) > 300:
                                del MEMPOOL_BUFFER[:-300]
        except Exception as e:
            log(f"MEMPOOL_ERR {e}")
            await asyncio.sleep(2)


def flush_mempool():
    out = []
    while MEMPOOL_BUFFER:
        out.append(MEMPOOL_BUFFER.pop(0))
    return out


async def fetch_fusion_candidates():
    return []


async def fetch_pumpfun_candidates(limit=30):
    data = await http_get("https://frontend-api.pump.fun/coins/latest")
    out = []
    if not isinstance(data, list):
        return out

    for row in data[:limit]:
        mint = row.get("mint")
        if mint and valid_mint_like(mint):
            meta = {
                "symbol": row.get("symbol"),
                "name": row.get("name"),
                "reply_count": row.get("reply_count"),
                "market_cap": row.get("market_cap"),
            }
            out.append({
                "mint": mint,
                "source": "pumpfun",
                "meta": meta,
            })
    return out


async def fetch_jupiter_candidates(limit=80):
    urls = [
        "https://lite-api.jup.ag/tokens/v1/mints/tradable",
        "https://cache.jup.ag/tokens",
    ]
    all_rows = []
    for url in urls:
        data = await http_get(url)
        if isinstance(data, list):
            all_rows.extend(data)

    out = []
    random.shuffle(all_rows)

    for row in all_rows[:limit]:
        if isinstance(row, str):
            mint, meta = row, {}
        else:
            mint, meta = row.get("address") or row.get("mint"), row

        if mint and mint != SOL and valid_mint_like(mint):
            out.append({
                "mint": mint,
                "source": "jupiter",
                "meta": {
                    "symbol": meta.get("symbol"),
                    "name": meta.get("name"),
                    "decimals": meta.get("decimals"),
                },
            })
    return out


async def fetch_dexscreener_candidates(query="SOL", limit=30):
    data = await http_get(
        "https://api.dexscreener.com/latest/dex/search/",
        params={"q": query}
    )
    out = []
    if not data:
        return out

    for row in (data.get("pairs", []) or [])[:limit]:
        base = row.get("baseToken", {}) or {}
        mint = base.get("address")
        if mint and mint != SOL and valid_mint_like(mint):
            out.append({
                "mint": mint,
                "source": "dexscreener",
                "meta": {
                    "symbol": base.get("symbol"),
                    "name": base.get("name"),
                    "liquidity_usd": (row.get("liquidity", {}) or {}).get("usd"),
                    "volume_h24": (row.get("volume", {}) or {}).get("h24"),
                    "price_native": row.get("priceNative"),
                },
            })
    return out


async def fetch_dex_bulk():
    tasks = [fetch_dexscreener_candidates(q) for q in SEARCH_TERMS + MEME_SEARCH_TERMS]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    merged = []
    for r in results:
        if isinstance(r, list):
            merged.extend(r)
    return merged


async def fetch_alpha_candidates():
    results = await asyncio.gather(
        fetch_fusion_candidates(),
        fetch_pumpfun_candidates(),
        fetch_jupiter_candidates(),
        fetch_dex_bulk(),
        return_exceptions=True,
    )

    merged = []
    for r in results:
        if isinstance(r, list):
            merged.extend(r)

    merged.extend(flush_mempool())
    out = dedup(merged)

    if len(out) < MIN_UNIVERSE and BOOT_SYNTHETIC_UNIVERSE:
        for i in range(10):
            out.append({
                "mint": f"SIM{i}{random.randint(1000,9999)}",
                "source": "synthetic",
                "meta": {},
            })

    return out


def source_quality(source):
    return {
        "pumpfun": 1.18,
        "mempool": 1.22,
        "dexscreener": 0.75,
        "fusion": 1.05,
        "jupiter": 1.00,
        "synthetic": 0.25,
    }.get(source, 1.0)


async def safe_quote(input_mint, output_mint, amount):
    for _ in range(max(1, QUOTE_TIMEOUT_RETRY)):
        try:
            q = await get_quote(input_mint, output_mint, amount)
            if q:
                return q
        except Exception:
            pass
        await asyncio.sleep(0.15)
    return None


async def jupiter_price(m):
    q = await safe_quote(SOL, m, AMOUNT)
    if not q:
        return None

    in_amt = sf(q.get("inAmount", AMOUNT))
    out_amt = sf(parse_out_amount(q))

    if in_amt <= 0 or out_amt <= 0 or out_amt < MIN_OUT_AMOUNT:
        return None

    price = in_amt / out_amt
    if price <= 0 or price > MAX_PRICE_JUPITER:
        return None

    return {"price": price, "liq": out_amt, "source": "jupiter"}


async def birdeye_price(m):
    if not BIRDEYE_API_KEY:
        return None

    headers = {"X-API-KEY": BIRDEYE_API_KEY}
    token_res = await http_get(
        "https://public-api.birdeye.so/defi/price",
        params={"address": m},
        headers=headers,
    )
    sol_res = await http_get(
        "https://public-api.birdeye.so/defi/price",
        params={"address": SOL},
        headers=headers,
    )

    try:
        token_usd = sf(token_res["data"]["value"])
        sol_usd = sf(sol_res["data"]["value"])
        if token_usd <= 0 or sol_usd <= 0:
            return None

        price = token_usd / sol_usd
        if price <= 0 or price > MAX_PRICE_FALLBACK:
            return None

        return {"price": price, "liq": 0, "source": "birdeye"}
    except Exception:
        return None


async def dexscreener_price(m):
    res = await http_get(
        "https://api.dexscreener.com/latest/dex/search/",
        params={"q": m}
    )
    if not res:
        return None

    try:
        pairs = sorted(
            res.get("pairs", []),
            key=lambda x: sf((x.get("liquidity", {}) or {}).get("usd", 0)),
            reverse=True,
        )
        if not pairs:
            return None

        pair = pairs[0]
        native_price = sf(pair.get("priceNative", 0))
        liq = sf((pair.get("liquidity", {}) or {}).get("usd", 0))

        if native_price <= 0 or native_price > MAX_PRICE_FALLBACK or liq < MIN_LIQUIDITY_OBSERVE:
            return None

        return {"price": native_price, "liq": liq, "source": "dexscreener"}
    except Exception:
        return None


async def get_price_info(m, prefer_clean=False):
    candidates = []

    for fn in (jupiter_price, birdeye_price, dexscreener_price):
        try:
            r = await fn(m)
            if r and r.get("price"):
                candidates.append(r)
        except Exception:
            pass

    if prefer_clean:
        for r in candidates:
            if r.get("source") == "jupiter" and sf(r.get("liq", 0), 0.0) >= MIN_LIQUIDITY_TRADE:
                return r
        if candidates:
            return max(candidates, key=lambda x: sf(x.get("liq", 0), 0.0))
        return None

    for r in candidates:
        if r.get("source") == "jupiter":
            return r

    if candidates:
        return max(candidates, key=lambda x: sf(x.get("liq", 0), 0.0))

    last = LAST_PRICE.get(m)
    if last:
        return {
            "price": last,
            "liq": 0,
            "source": LAST_PRICE_SOURCE.get(m, "last_price"),
        }
    return None


async def get_price(m):
    info = await get_price_info(m, prefer_clean=False)
    return None if not info else info["price"]


# =========================================================
# FEATURES / SCORE
# =========================================================

async def features(t):
    m = t.get("mint")
    if not m:
        return None

    pinfo = await get_price_info(m, prefer_clean=True)
    if not pinfo or pinfo.get("source") not in {"jupiter", "dexscreener"}:
        return None

    liq = sf(pinfo.get("liq", 0), 0.0)
    if liq < MIN_LIQUIDITY_TRADE:
        return None

    price = pinfo["price"]
    prev = LAST_PRICE.get(m)

    breakout = (price - prev) / prev if prev and prev > 0 else random.uniform(0.003, 0.015)
    breakout = clamp(breakout, -MAX_BREAKOUT_ABS, MAX_BREAKOUT_ABS)
    if abs(breakout) < 0.001:
        breakout = 0.003

    momentum = 0.0
    try:
        await asyncio.sleep(0.25)
        p2 = await get_price(m)
        if price and p2 and p2 > 0:
            momentum = (p2 - price) / price
    except Exception:
        momentum = 0.0

    momentum = clamp(momentum, -MAX_BREAKOUT_ABS, MAX_BREAKOUT_ABS)
    if abs(momentum) < 0.001:
        momentum = breakout * 0.5

    LAST_MOMENTUM[m] = momentum
    LAST_PRICE[m] = price
    LAST_PRICE_SOURCE[m] = pinfo.get("source", "unknown")

    wallets = await safe_update_token_wallets(m)
    wallet_count = len(wallets)
    smart = min(wallet_count / 3.0, 1.0)

    sniper_boost = 0.0
    if t.get("source") == "pumpfun":
        sniper_boost += 0.05
    if t.get("source") == "mempool":
        sniper_boost += 0.08
    if pinfo.get("source") == "jupiter":
        sniper_boost += 0.02

    return {
        "mint": m,
        "price": price,
        "breakout": breakout,
        "momentum": momentum,
        "smart": smart,
        "sniper_boost": sniper_boost,
        "is_new": prev is None,
        "wallet_count": wallet_count,
        "source": t.get("source", "unknown"),
        "meta": t.get("meta", {}),
        "price_source": pinfo.get("source", "unknown"),
        "liq": liq,
    }


def mode(f):
    if f["is_new"]:
        return "sniper"
    if f["smart"] > 0.6:
        return "smart"
    return "momentum"


def zero_detail():
    return {
        "bscore": 0.0,
        "mscore": 0.0,
        "sscore": 0.0,
        "lscore": 0.0,
        "wscore": 0.0,
        "nscore": 0.0,
    }


def score_alpha(f):
    breakout = sf(f.get("breakout", 0.0), 0.0)
    momentum = sf(f.get("momentum", 0.0), 0.0)
    smart = sf(f.get("smart", 0.0), 0.0)
    liq = sf(f.get("liq", 0.0), 0.0)
    price_source = f.get("price_source", "unknown")

    if liq < MIN_LIQUIDITY_OBSERVE:
        return 0.0, zero_detail()

    source_penalty = 1.0 if price_source == "jupiter" else 0.70
    if price_source == "jupiter" and liq < MIN_LIQUIDITY_TRADE:
        source_penalty = 0.85

    if momentum < MIN_CONFIRM_MOMENTUM:
        momentum *= 0.5
    if breakout < MIN_CONFIRM_BREAKOUT:
        breakout *= 0.5

    if breakout > 0.012 and momentum < 0:
        return 0.0, zero_detail()

    bscore = breakout_strength(breakout)
    mscore = momentum_strength(momentum)
    sscore = clamp(smart, 0.0, 1.0) * 0.40
    lscore = min(liq / 1_000_000, 1.0) * 0.12

    wc = f.get("wallet_count", 0)
    wscore = 0.08 if wc >= 3 else 0.05 if wc >= 2 else 0.02 if wc >= 1 else 0.0
    nscore = clamp(sf(f.get("sniper_boost", 0)), 0.0, 0.12)

    for name, val in [
        ("breakout", breakout),
        ("momentum", momentum),
        ("smart_money", smart),
        ("liquidity", liq),
        ("wallet_count", wc),
        ("price", f.get("price", 0)),
    ]:
        score_stat_add(name, val)

    score = (
        bscore * ALPHA_BREAKOUT_WEIGHT
        + mscore * ALPHA_MOMENTUM_WEIGHT
        + sscore * ALPHA_SMART_WEIGHT
        + lscore * ALPHA_LIQ_WEIGHT
        + wscore * ALPHA_WALLET_WEIGHT
        + nscore * 0.05
    ) * source_penalty

    mtype = mode(f)
    if mtype == "sniper":
        score *= SNIPER_MULTIPLIER
    elif mtype == "smart":
        score *= SMART_MULTIPLIER
    else:
        score *= MOMENTUM_MULTIPLIER

    return clamp(score, 0.0, MAX_SCORE), {
        "bscore": bscore,
        "mscore": mscore,
        "sscore": sscore,
        "lscore": lscore,
        "wscore": wscore,
        "nscore": nscore,
    }


def source_weight(src):
    s = SOURCE_STATS[src]
    total = s["wins"] + s["losses"]
    mem = 1.0
    if total >= 5:
        winrate = s["wins"] / total if total else 0.0
        if winrate > 0.6:
            mem = 1.12
        elif winrate < 0.3:
            mem = 0.82
    return mem * source_quality(src)


def score_with_allocator(f):
    base, detail = score_alpha(f)
    base *= source_weight(f["source"])

    if TOKEN_TRADE_COUNT[f["mint"]] > 2:
        base *= 0.7

    regime = detect_regime()
    if regime == "bull":
        base *= 1.08
    elif regime == "bear":
        base *= 0.88

    return max(base, 0.0), mode(f), detail


def allocate_size(score, n_candidates):
    if n_candidates <= 0:
        return 0.0

    base = engine.capital / max(n_candidates * 2, 2)
    regime = detect_regime()

    if regime == "bull":
        base *= 1.20
    elif regime == "bear":
        base *= 0.65

    if score > 0.16:
        base *= 2.0
    elif score > 0.14:
        base *= 1.65
    elif score > 0.12:
        base *= 1.15
    else:
        base *= 0.55

    base *= breathing_risk_mult()
    base *= clamp(sf(AGENT_STATE.get("risk_mult", 1.0), 1.0), AGENT_RISK_MIN, AGENT_RISK_MAX)

    if agent_in_cooldown():
        base *= 0.60

    base = min(base, 0.20)
    return min(base, engine.capital * MAX_POSITION_SIZE)


# =========================================================
# ACCOUNTING HELPERS
# =========================================================

def extract_fee_sol_from_res(res):
    if not isinstance(res, dict):
        return ESTIMATED_TX_FEE_SOL

    fee_candidates = [
        res.get("fee_sol"),
        res.get("tx_fee_sol"),
        res.get("network_fee_sol"),
        (res.get("quote") or {}).get("fee_sol"),
        (res.get("quote") or {}).get("tx_fee_sol"),
    ]
    for x in fee_candidates:
        v = sf(x, None)
        if v is not None and v >= 0:
            return v
    return ESTIMATED_TX_FEE_SOL


def atomic_to_token_amount(out_amount, decimals):
    if out_amount <= 0:
        return 0.0
    scale = 10 ** decimals
    return out_amount / scale


async def calc_position_market_value(p):
    price = await get_price(p["mint"])
    if price is None or price <= 0:
        return sf(p.get("entry_value", 0.0), 0.0), sf(p.get("entry_price", 0.0), 0.0)

    token_amount = sf(p.get("token_amount", 0.0), 0.0)
    return token_amount * price, price


async def calc_unrealized_pnl_sol():
    total = 0.0
    for p in list(engine.positions or []):
        entry_value = sf(p.get("entry_value", 0.0), 0.0)
        fees_paid = sf(p.get("fees_paid_sol", 0.0), 0.0)
        mv, _ = await calc_position_market_value(p)
        total += (mv - entry_value - fees_paid)
    return total


async def calc_equity():
    if not ENABLE_EQUITY_MARK:
        return sf(engine.capital, 0.0)

    total = sf(engine.capital, 0.0)
    for p in list(engine.positions or []):
        mv, _ = await calc_position_market_value(p)
        total += mv
    return total


# =========================================================
# EXECUTION
# =========================================================

async def buy(m, f, position_size, mtype, forced=False):
    order_sol = max(position_size, MIN_ORDER_SOL)
    amt_atomic = int(order_sol * SOL_DECIMALS)

    res = await safe_execute_swap(SOL, m, amt_atomic)

    if not res:
        engine.stats["errors"] += 1
        log(f"BUY_EMPTY {m[:6]}")
        return False

    if res.get("error"):
        engine.stats["errors"] += 1
        log(f"BUY_FAIL {m[:6]} {res.get('error')}")
        return False

    out_amount = parse_out_amount(res)
    if out_amount <= 0:
        q = await safe_quote(SOL, m, amt_atomic)
        out_amount = parse_out_amount(q)
    if out_amount <= 0:
        engine.stats["errors"] += 1
        log(f"BUY_NO_OUT {m[:6]}")
        return False

    token_decimals = extract_token_decimals(f.get("meta", {}))
    token_amount = atomic_to_token_amount(out_amount, token_decimals)

    if token_amount <= 0:
        engine.stats["errors"] += 1
        log(f"BUY_BAD_TOKEN_AMOUNT {m[:6]}")
        return False

    tx_sig = parse_signature(res)
    fee_sol = extract_fee_sol_from_res(res)

    engine.capital = max(engine.capital - order_sol - fee_sol, 0.0)
    engine.stats["fees_paid_sol"] += fee_sol

    meta = dict(f.get("meta", {}) or {})
    meta.update({
        "source": f.get("source"),
        "strategy": mtype,
        "forced": forced,
        "breakout": f.get("breakout"),
        "momentum": f.get("momentum"),
        "smart_money": f.get("smart"),
        "liquidity": f.get("liq"),
        "wallet_count": f.get("wallet_count"),
        "price": f.get("price"),
        "score": f.get("_score"),
        "tier": f.get("_tier"),
        "regime": detect_regime(),
        "agent_mode": AGENT_STATE.get("mode"),
        "token_decimals": token_decimals,
    })

    position = {
        "mint": m,
        "entry": f["price"],
        "entry_price": f["price"],
        "size": order_sol,
        "size_sol": order_sol,
        "entry_value": order_sol,
        "token_amount_atomic": out_amount,
        "token_amount": token_amount,
        "token_decimals": token_decimals,
        "fees_paid_sol": fee_sol,
        "time": now(),
        "mode": mtype,
        "source": f["source"],
        "meta": meta,
        "price_source": f.get("price_source"),
        "liq": f.get("liq", 0),
        "high": f["price"],
        "wallet_count": f.get("wallet_count", 0),
        "tx_buy": tx_sig,
        "forced": forced,
        "paper": bool(res.get("paper")),
        "score": f.get("_score", 0.0),
        "tier": f.get("_tier", "C"),
        "realized_partial_sol": 0.0,
    }

    engine.positions.append(position)

    LAST_TRADE[m] = now()
    BUY_TIMES.append(now())
    engine.stats["executed"] += 1
    engine.stats["signals"] += 1
    if forced:
        engine.stats["forced_trades"] += 1

    update_open_stats()
    engine.last_signal = f"BUY {m[:6]} {mtype} tier={f.get('_tier','C')} score={f.get('_score',0):.4f}"
    engine.last_trade = engine.last_signal
    log(engine.last_signal)
    return True


async def sell(p, reason, price, sell_fraction=1.0):
    m = p["mint"]
    sell_fraction = clamp(sell_fraction, 0.0, 1.0)
    if sell_fraction <= 0:
        return False

    token_amount = sf(p.get("token_amount", 0.0), 0.0)
    entry_value_total = sf(p.get("entry_value", 0.0), 0.0)
    fees_paid_total = sf(p.get("fees_paid_sol", 0.0), 0.0)

    if token_amount <= 0 or entry_value_total <= 0:
        engine.stats["errors"] += 1
        log(f"SELL_BAD_POSITION {m[:6]}")
        return False

    token_amount_to_sell = token_amount * sell_fraction
    token_amount_remain = max(0.0, token_amount - token_amount_to_sell)

    token_decimals = int(p.get("token_decimals", DEFAULT_TOKEN_DECIMALS))
    atomic_sell = int(token_amount_to_sell * (10 ** token_decimals))

    if atomic_sell <= 0:
        engine.stats["errors"] += 1
        log(f"SELL_NO_AMOUNT {m[:6]}")
        return False

    if p.get("paper"):
        res = {"paper": True}
        fee_sol = ESTIMATED_TX_FEE_SOL
    else:
        res = await safe_execute_swap(m, SOL, atomic_sell)
        fee_sol = extract_fee_sol_from_res(res)

    if not res or res.get("error"):
        engine.stats["errors"] += 1
        log(f"SELL_FAIL {m[:6]} {res.get('error') if res else 'empty'}")
        return False

    engine.stats["fees_paid_sol"] += fee_sol

    exit_value = token_amount_to_sell * price

    entry_value_sold = entry_value_total * sell_fraction
    fees_allocated = fees_paid_total * sell_fraction + fee_sol

    pnl_sol = exit_value - entry_value_sold - fees_allocated
    pnl = safe_div(pnl_sol, entry_value_sold, 0.0)
    pnl = clamp(pnl, -MAX_PNL_ABS, MAX_PNL_ABS)

    engine.capital += max(0.0, exit_value - fee_sol)
    engine.stats["realized_pnl_sol"] += pnl_sol

    src = p.get("source", "unknown")
    strategy = p.get("mode", "unknown")

    is_full_exit = token_amount_remain <= 0.000000000001 or sell_fraction >= 0.999999

    if is_full_exit:
        if p in engine.positions:
            engine.positions.remove(p)
    else:
        p["token_amount"] = token_amount_remain
        p["token_amount_atomic"] = int(token_amount_remain * (10 ** token_decimals))
        p["entry_value"] = entry_value_total * (1.0 - sell_fraction)
        p["size"] = p["entry_value"]
        p["size_sol"] = p["entry_value"]
        p["fees_paid_sol"] = fees_paid_total * (1.0 - sell_fraction)
        p["realized_partial_sol"] = sf(p.get("realized_partial_sol", 0.0), 0.0) + pnl_sol

    if pnl_sol > 0:
        engine.stats["wins"] += 1
        source_stat_win(src, pnl)
    else:
        engine.stats["losses"] += 1
        source_stat_loss(src, pnl)

    strategy_stat_update(strategy, pnl)

    push_trade({
        "mint": m,
        "entry": p.get("entry_price", p.get("entry")),
        "exit": price,
        "pnl": pnl,
        "pnl_sol": pnl_sol,
        "reason": reason,
        "size": entry_value_sold,
        "mode": strategy,
        "source": src,
        "price_source": p.get("price_source"),
        "time_open": p.get("time"),
        "time_close": now(),
        "tx_buy": p.get("tx_buy"),
        "meta": p.get("meta", {}),
        "sell_fraction": sell_fraction,
        "exit_value": exit_value,
        "entry_value": entry_value_sold,
        "fees_paid_sol": fees_allocated,
        "token_amount_sold": token_amount_to_sell,
    })

    update_breathing_state()
    update_open_stats()

    if is_full_exit:
        BLACKLIST[m] = now()
        engine.last_trade = f"SELL {m[:6]} {reason} pnl={pnl:.4f} pnl_sol={pnl_sol:.6f}"
    else:
        engine.last_trade = f"PARTIAL {m[:6]} {reason} pnl={pnl:.4f} pnl_sol={pnl_sol:.6f}"

    log(engine.last_trade)
    return True


# =========================================================
# EXIT LOGIC
# =========================================================

async def check_sell(p):
    m = p["mint"]
    price = await get_price(m)
    entry = sf(p.get("entry_price", p.get("entry")), 0.0)

    if price is None or entry <= 0:
        return False

    hold_sec = now() - sf(p.get("time"), now())
    if price < 1e-8 or hold_sec < 8:
        return False

    last = LAST_PRICE.get(m)
    if last and last > 0:
        jump = abs(price - last) / last
        if jump > 0.25 and hold_sec < 20:
            return False

    token_amount = sf(p.get("token_amount", 0.0), 0.0)
    entry_value = sf(p.get("entry_value", 0.0), 0.0)
    if token_amount <= 0 or entry_value <= 0:
        return False

    market_value = token_amount * price
    pnl = safe_div(market_value - entry_value, entry_value, 0.0)
    pnl = clamp(pnl, -MAX_PNL_ABS, MAX_PNL_ABS)

    p["high"] = max(sf(p.get("high"), entry), price)

    tier = p.get("tier") or (p.get("meta", {}) or {}).get("tier", "C")
    momentum_now = sf(LAST_MOMENTUM.get(m, 0.0), 0.0)
    regime = detect_regime()

    if pnl <= HARD_STOP_LOSS:
        return await sell(p, "HARD_STOP", price, 1.0)

    if hold_sec > FORCE_EXIT_SEC:
        return await sell(p, "FORCE_EXIT", price, 1.0)

    fast_cut_line = -0.02 if regime != "bear" else -0.015
    if pnl < fast_cut_line and hold_sec > 20:
        return await sell(p, "FAST_CUT", price, 1.0)

    if pnl > 0 and momentum_now > 0.0035:
        return False

    if -0.02 < pnl < 0 and momentum_now > 0.0045:
        return False

    if pnl >= 0.008 and not p.get("tp1_done"):
        p["tp1_done"] = True
        return await sell(p, "PARTIAL_TP", price, 0.50)

    tp = agent_effective_tp()
    if tier == "A+":
        tp *= 2.2
    elif tier == "A":
        tp *= 1.8

    if regime == "bull":
        tp *= 1.15
    elif regime == "bear":
        tp *= 0.85

    if pnl >= tp:
        return await sell(p, "TP", price, 1.0)

    effective_sl = agent_effective_sl()
    if pnl <= effective_sl:
        await asyncio.sleep(0.4)
        price2 = await get_price(m)
        if price2:
            market_value2 = token_amount * price2
            pnl2 = safe_div(market_value2 - entry_value, entry_value, 0.0)
            pnl2 = clamp(pnl2, -MAX_PNL_ABS, MAX_PNL_ABS)
            if pnl2 <= effective_sl:
                return await sell(p, "SL", price2, 1.0)
        return False

    dynamic_trailing_gap = TRAILING_GAP * (1.15 if tier == "A+" else 1.0) * (0.85 if regime == "bear" else 1.0)
    if price < p["high"] * (1 - dynamic_trailing_gap):
        return await sell(p, "TRAIL", price, 1.0)

    dynamic_hold = int(MAX_HOLD_SEC * (1.25 if regime == "bull" else 0.70 if regime == "bear" else 1.0))
    if hold_sec > dynamic_hold:
        if tier in {"A", "A+"} and momentum_now > 0.0025 and pnl > 0:
            return False
        if pnl < 0.003:
            return await sell(p, "TIME", price, 1.0)

    return False


# =========================================================
# CANDIDATE PROCESS / PORTFOLIO
# =========================================================

async def process_candidates(tokens):
    ranked = []
    dyn_threshold = current_dynamic_threshold()
    regime = detect_regime()

    for t in tokens:
        m = t.get("mint")
        if not m:
            continue
        if (m in BLACKLIST and now() - BLACKLIST[m] < BLACKLIST_TIME) or now() - LAST_TRADE[m] < 30:
            continue

        f = await features(t)
        if not f:
            continue

        f["source"] = t.get("source", f.get("source", "unknown"))
        f["meta"] = t.get("meta", {})

        sc, mtype, detail = score_with_allocator(f)

        min_threshold = max(dyn_threshold * 0.90, agent_effective_entry_threshold())
        if regime == "bear":
            min_threshold = max(min_threshold, agent_effective_entry_threshold() + 0.005)
        elif regime == "bull":
            min_threshold *= 0.97

        if sc < min_threshold:
            continue

        f["_score"] = sc
        f["_mode"] = mtype
        f["_tier"] = "A+" if sc >= 0.145 else "A" if sc >= STRICT_A_TIER_THRESHOLD else "B"

        log(
            f"SCORE {m[:6]} sc={sc:.4f} tier={f['_tier']} "
            f"b={detail['bscore']:.4f} m={detail['mscore']:.4f} "
            f"s={detail['sscore']:.4f} l={detail['lscore']:.4f}"
        )

        ranked.append(f)

    ranked.sort(key=lambda x: x["_score"], reverse=True)

    if not ranked:
        for t in tokens[:5]:
            f = await features(t)
            if not f:
                continue
            sc, mtype, _ = score_with_allocator(f)
            if sc > EXPLORATION_MIN_SCORE:
                f["_score"] = sc
                f["_mode"] = mtype
                f["_tier"] = "B"
                ranked.append(f)

    return ranked[:10]


async def exploration_trade():
    if not EXPLORATION_ENABLE:
        return False

    tokens = await fetch_alpha_candidates()
    if not isinstance(tokens, list):
        return False

    for t in tokens[:6]:
        f = await features(t)
        if not f:
            continue

        sc, _mtype, _ = score_with_allocator(f)
        if sc > EXPLORATION_MIN_SCORE:
            f["_score"] = sc
            f["_mode"] = "explore"
            f["_tier"] = "B"

            size = min(
                engine.capital * EXPLORATION_SIZE_FRAC,
                engine.capital * MAX_POSITION_SIZE
            )
            return bool(await buy(t["mint"], f, size, "explore", forced=True))

    return False


async def execute_portfolio(ranked):
    if not ranked:
        return await exploration_trade()

    traded = False
    buys_this_cycle = 0
    ranked = sorted(ranked, key=lambda x: x["_score"], reverse=True)[:TOP_K_PRESELECT]

    in_breathing_cooldown = now() < sf(BREATHING_STATE.get("cooldown_until", 0.0), 0.0)

    if buy_window_count() >= MAX_BUYS_PER_10MIN:
        return False

    for f in ranked:
        m = f["mint"]

        if engine.stats.get("executed", 0) > 10 and engine.stats.get("wins", 0) == 0:
            return False

        allowed_tiers = {"A+"} if AGENT_STATE.get("mode") == "defensive" else {"A", "A+"}
        if f.get("_mode") != "explore" and f.get("_tier") not in allowed_tiers:
            continue

        if any(p["mint"] == m for p in engine.positions):
            continue

        if len(engine.positions) >= MAX_POSITIONS or exposure() >= engine.capital * MAX_EXPOSURE:
            break

        if now() - LAST_TRADE[m] < TOKEN_COOLDOWN:
            continue

        if sf(f.get("liq", 0), 0.0) < MIN_LIQUIDITY_TRADE and f.get("_mode") != "explore":
            continue

        if (
            (in_breathing_cooldown or agent_in_cooldown())
            and f.get("_tier") != "A+"
            and sf(f.get("_score"), 0.0) < max(agent_effective_entry_threshold() + 0.02, 0.14)
        ):
            continue

        ok = True
        if not SOFT_DISABLE_FILTER:
            ok, _meta = safe_adaptive_filter(f, None, engine.no_trade_cycles)
            if not ok and f["_score"] >= FILTER_SCORE_BYPASS:
                ok = True

        if not ok:
            continue

        pos_size = allocate_size(f["_score"], len(ranked))
        if f.get("_mode") == "explore":
            pos_size = min(pos_size, engine.capital * EXPLORATION_SIZE_FRAC)
        if in_breathing_cooldown:
            pos_size *= 0.70

        if pos_size <= 0 or engine.capital < pos_size + ESTIMATED_TX_FEE_SOL:
            continue

        success = await buy(m, f, pos_size, f["_mode"], forced=(f.get("_mode") == "explore"))
        if success:
            TOKEN_TRADE_COUNT[m] += 1
            buys_this_cycle += 1
            traded = True

            if buys_this_cycle >= MAX_NEW_BUYS_PER_CYCLE or TOP_N_TO_TRADE <= 1:
                break

    return traded


# =========================================================
# METRICS
# =========================================================

def _avg_stat(name):
    s = SCORE_COMPONENT_STATS.get(name, {"count": 0, "sum": 0.0})
    c = s.get("count", 0)
    return {"count": c, "avg_score": (s.get("sum", 0.0) / c if c else 0.0)}


def _source_perf(src):
    s = SOURCE_STATS.get(src, {"count": 0, "wins": 0, "losses": 0, "total_pnl": 0.0})
    c = s["count"]
    return {
        "count": c,
        "wins": s["wins"],
        "losses": s["losses"],
        "total_pnl": s["total_pnl"],
        "avg_pnl": s["total_pnl"] / c if c else 0.0,
        "win_rate": s["wins"] / c if c else 0.0,
    }


def _strategy_perf(name):
    s = STRATEGY_STATS.get(name, {"count": 0, "wins": 0, "losses": 0, "total_pnl": 0.0})
    c = s["count"]
    return {
        "count": c,
        "wins": s["wins"],
        "losses": s["losses"],
        "total_pnl": s["total_pnl"],
        "avg_pnl": s["total_pnl"] / c if c else 0.0,
        "win_rate": s["wins"] / c if c else 0.0,
    }


async def get_metrics_async():
    start_capital = sf(engine.start_capital, 5.0)
    cash = sf(engine.capital, start_capital)
    equity = await calc_equity()
    unrealized = await calc_unrealized_pnl_sol()
    engine.stats["unrealized_pnl_sol"] = unrealized

    capital = equity
    peak = max(sf(engine.peak_capital, capital), capital)

    total_return = capital - start_capital
    return_pct = total_return / start_capital if start_capital > 0 else 0.0
    drawdown = ((peak - capital) / peak) if peak > 0 else 0.0

    wins = int(engine.stats.get("wins", 0))
    losses = int(engine.stats.get("losses", 0))
    trades = int(engine.stats.get("trades", 0))

    win_pnls = [sf(x.get("pnl")) for x in engine.trade_history if sf(x.get("pnl")) > 0]
    loss_pnls = [sf(x.get("pnl")) for x in engine.trade_history if sf(x.get("pnl")) <= 0]

    avg_win = sum(win_pnls) / len(win_pnls) if win_pnls else 0.0
    avg_loss = sum(loss_pnls) / len(loss_pnls) if loss_pnls else 0.0

    gross_win = sum(win_pnls)
    gross_loss = abs(sum(loss_pnls))
    profit_factor = gross_win / gross_loss if gross_loss > 0 else 0.0

    source_perf = {k: _source_perf(k) for k in SOURCE_STATS.keys()}
    strategy_perf = {k: _strategy_perf(k) for k in STRATEGY_STATS.keys()}

    open_positions_detail = []
    for p in (engine.positions or []):
        px = await get_price(p.get("mint"))
        token_amount = sf(p.get("token_amount", 0.0), 0.0)
        mv = token_amount * px if px else 0.0
        entry_value = sf(p.get("entry_value", 0.0), 0.0)
        u_pnl_sol = mv - entry_value if px else 0.0
        u_pnl_pct = safe_div(u_pnl_sol, entry_value, 0.0)

        open_positions_detail.append({
            "mint": p.get("mint"),
            "tier": p.get("tier"),
            "source": p.get("source"),
            "mode": p.get("mode"),
            "entry": p.get("entry_price", p.get("entry")),
            "size": p.get("size_sol", p.get("size")),
            "entry_value": entry_value,
            "token_amount": token_amount,
            "mark_price": px,
            "market_value": mv,
            "unrealized_pnl_sol": u_pnl_sol,
            "unrealized_pnl_pct": u_pnl_pct,
            "hold_sec": round(time.time() - sf(p.get("time"), time.time()), 2),
            "high": p.get("high"),
            "price_source": p.get("price_source"),
            "last_momentum": sf(LAST_MOMENTUM.get(p.get("mint"), 0.0), 0.0),
        })

    return {
        "summary": {
            "capital": capital,
            "cash": cash,
            "equity": equity,
            "unrealized_pnl_sol": unrealized,
            "realized_pnl_sol": sf(engine.stats.get("realized_pnl_sol", 0.0), 0.0),
            "fees_paid_sol": sf(engine.stats.get("fees_paid_sol", 0.0), 0.0),
            "start_capital": start_capital,
            "peak_capital": peak,
            "equity_gain": total_return,
            "return_pct": return_pct,
            "drawdown": drawdown,
            "running": bool(engine.running),
            "mode": "REAL" if REAL_TRADING else "PAPER",
            "regime": detect_regime(),
        },
        "performance": {
            "trades": trades,
            "wins": wins,
            "losses": losses,
            "win_rate": (wins / trades) if trades else 0.0,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "profit_factor": profit_factor,
            "total_return": total_return,
        },
        "trading": {
            "signals": engine.stats.get("signals", 0),
            "executed": engine.stats.get("executed", 0),
            "rejected": engine.stats.get("rejected", 0),
            "errors": engine.stats.get("errors", 0),
            "open_positions": len(engine.positions),
            "open_exposure": exposure(),
            "forced_trades": engine.stats.get("forced_trades", 0),
            "no_trade_cycles": engine.no_trade_cycles,
            "breathing_risk_mult": breathing_risk_mult(),
            "breathing_cooldown_left": max(
                0,
                int(sf(BREATHING_STATE.get("cooldown_until", 0.0), 0.0) - now())
            ),
            "buy_window_count": buy_window_count(),
            "agent_mode": AGENT_STATE.get("mode"),
            "agent_risk_mult": AGENT_STATE.get("risk_mult"),
            "agent_confidence": AGENT_STATE.get("confidence"),
            "agent_cooldown_left": max(
                0,
                int(sf(AGENT_STATE.get("cooldown_until", 0.0), 0.0) - now())
            ),
            "agent_reason": AGENT_STATE.get("last_reason"),
            "auto_entry_threshold": agent_effective_entry_threshold(),
            "auto_take_profit": agent_effective_tp(),
            "auto_stop_loss": agent_effective_sl(),
        },
        "positions": engine.positions,
        "recent_trades": engine.trade_history[-20:],
        "logs": engine.logs[-120:],
        "source_stats": source_perf,
        "strategy_stats": strategy_perf,
        "score_component_stats": {
            k: _avg_stat(k)
            for k in ["breakout", "smart_money", "liquidity", "momentum", "wallet_count", "price"]
        },
        "portfolio": {
            "positions_by_source": dict(Counter([p.get("source", "unknown") for p in engine.positions])),
            "positions_by_strategy": dict(Counter([p.get("mode", "unknown") for p in engine.positions])),
            "total_exposure_ratio": exposure() / capital if capital > 0 else 0.0,
        },
        "open_positions_detail": open_positions_detail,
    }


def get_metrics():
    start_capital = sf(engine.start_capital, 5.0)
    cash = sf(engine.capital, start_capital)
    capital = cash
    peak = max(sf(engine.peak_capital, capital), capital)

    total_return = capital - start_capital
    return_pct = total_return / start_capital if start_capital > 0 else 0.0
    drawdown = ((peak - capital) / peak) if peak > 0 else 0.0

    wins = int(engine.stats.get("wins", 0))
    losses = int(engine.stats.get("losses", 0))
    trades = int(engine.stats.get("trades", 0))

    win_pnls = [sf(x.get("pnl")) for x in engine.trade_history if sf(x.get("pnl")) > 0]
    loss_pnls = [sf(x.get("pnl")) for x in engine.trade_history if sf(x.get("pnl")) <= 0]

    avg_win = sum(win_pnls) / len(win_pnls) if win_pnls else 0.0
    avg_loss = sum(loss_pnls) / len(loss_pnls) if loss_pnls else 0.0

    gross_win = sum(win_pnls)
    gross_loss = abs(sum(loss_pnls))
    profit_factor = gross_win / gross_loss if gross_loss > 0 else 0.0

    source_perf = {k: _source_perf(k) for k in SOURCE_STATS.keys()}
    strategy_perf = {k: _strategy_perf(k) for k in STRATEGY_STATS.keys()}

    return {
        "summary": {
            "capital": capital,
            "cash": cash,
            "start_capital": start_capital,
            "peak_capital": peak,
            "equity_gain": total_return,
            "return_pct": return_pct,
            "drawdown": drawdown,
            "running": bool(engine.running),
            "mode": "REAL" if REAL_TRADING else "PAPER",
            "regime": detect_regime(),
        },
        "performance": {
            "trades": trades,
            "wins": wins,
            "losses": losses,
            "win_rate": (wins / trades) if trades else 0.0,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "profit_factor": profit_factor,
            "total_return": total_return,
        },
        "trading": {
            "signals": engine.stats.get("signals", 0),
            "executed": engine.stats.get("executed", 0),
            "rejected": engine.stats.get("rejected", 0),
            "errors": engine.stats.get("errors", 0),
            "open_positions": len(engine.positions),
            "open_exposure": exposure(),
            "forced_trades": engine.stats.get("forced_trades", 0),
            "no_trade_cycles": engine.no_trade_cycles,
            "breathing_risk_mult": breathing_risk_mult(),
            "breathing_cooldown_left": max(
                0,
                int(sf(BREATHING_STATE.get("cooldown_until", 0.0), 0.0) - now())
            ),
            "buy_window_count": buy_window_count(),
            "agent_mode": AGENT_STATE.get("mode"),
            "agent_risk_mult": AGENT_STATE.get("risk_mult"),
            "agent_confidence": AGENT_STATE.get("confidence"),
            "agent_cooldown_left": max(
                0,
                int(sf(AGENT_STATE.get("cooldown_until", 0.0), 0.0) - now())
            ),
            "agent_reason": AGENT_STATE.get("last_reason"),
            "auto_entry_threshold": agent_effective_entry_threshold(),
            "auto_take_profit": agent_effective_tp(),
            "auto_stop_loss": agent_effective_sl(),
        },
        "positions": engine.positions,
        "recent_trades": engine.trade_history[-20:],
        "logs": engine.logs[-120:],
        "source_stats": source_perf,
        "strategy_stats": strategy_perf,
        "score_component_stats": {
            k: _avg_stat(k)
            for k in ["breakout", "smart_money", "liquidity", "momentum", "wallet_count", "price"]
        },
        "portfolio": {
            "positions_by_source": dict(Counter([p.get("source", "unknown") for p in engine.positions])),
            "positions_by_strategy": dict(Counter([p.get("mode", "unknown") for p in engine.positions])),
            "total_exposure_ratio": exposure() / capital if capital > 0 else 0.0,
        },
        "open_positions_detail": [
            {
                "mint": p.get("mint"),
                "tier": p.get("tier"),
                "source": p.get("source"),
                "mode": p.get("mode"),
                "entry": p.get("entry_price", p.get("entry")),
                "size": p.get("size_sol", p.get("size")),
                "entry_value": p.get("entry_value"),
                "token_amount": p.get("token_amount"),
                "high": p.get("high"),
                "price_source": p.get("price_source"),
                "last_momentum": sf(LAST_MOMENTUM.get(p.get("mint"), 0.0), 0.0),
            }
            for p in (engine.positions or [])
        ],
    }


# =========================================================
# START / LOOP
# =========================================================

async def start_once():
    global MEMPOOL_TASK
    ensure_engine()
    if MEMPOOL_TASK is None or MEMPOOL_TASK.done():
        MEMPOOL_TASK = asyncio.create_task(mempool_stream())


async def main_loop():
    global MEMPOOL_TASK

    await start_once()
    log("V66.1 COMPLETE LIVE ENGINE START")

    while engine.running:
        try:
            agent_update()
            agent_adjust_params()

            tokens = await fetch_alpha_candidates()
            if not isinstance(tokens, list):
                tokens = []

            tokens = dedup(tokens)
            tokens = limit_token_frequency(tokens, max_per_token=2)
            random.shuffle(tokens)
            tokens = tokens[:MAX_TOKENS_PER_CYCLE]

            if len(tokens) < 3:
                await asyncio.sleep(LOOP_SLEEP_SEC)
                continue

            for p in list(engine.positions):
                await check_sell(p)

            ranked = await process_candidates(tokens)
            traded = await execute_portfolio(ranked)

            if not traded:
                engine.no_trade_cycles += 1
            else:
                engine.no_trade_cycles = 0

            if (
                agent_force_trade_allowed()
                and engine.no_trade_cycles > FORCE_TRADE_AFTER
                and len(engine.positions) < MAX_POSITIONS
                and exposure() < engine.capital * MAX_EXPOSURE
            ):
                current_mints = {p["mint"] for p in engine.positions}
                for f in ranked[:TOP_K_PRESELECT]:
                    if f["mint"] in current_mints:
                        continue
                    if f["_score"] < STRICT_A_TIER_THRESHOLD:
                        continue
                    if f.get("_tier") not in {"A", "A+"}:
                        continue

                    ok = await buy(
                        f["mint"],
                        f,
                        allocate_size(max(f["_score"], STRICT_A_TIER_THRESHOLD), 1),
                        f["_mode"],
                        forced=True,
                    )
                    if ok:
                        TOKEN_TRADE_COUNT[f["mint"]] += 1
                        engine.no_trade_cycles = 0
                        break

            update_open_stats()
            await update_peak_capital()

            if ENABLE_EQUITY_MARK:
                engine.stats["unrealized_pnl_sol"] = await calc_unrealized_pnl_sol()

        except Exception as e:
            engine.stats["errors"] += 1
            log(f"ERR {e}")

        await asyncio.sleep(LOOP_SLEEP_SEC)
