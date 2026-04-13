import os
import time
from collections import defaultdict

from app.state import engine
from app.config import (
    SOL_MINT as SOL,
    SOL_DECIMALS,
    HTTP_TIMEOUT,
    BIRDEYE_API_KEY,
    REAL_TRADING,
)

# =========================================================
# OPTIONAL MODULES
# =========================================================
try:
    from app.execution.jito_exec import send_jito_bundle
except Exception:
    async def send_jito_bundle(*args, **kwargs):
        return {"error": "jito_exec_not_available"}


try:
    from app.alpha.wallet_graph import get_wallet_graph_score, get_wallet_cluster_stats
except Exception:
    async def get_wallet_graph_score(_mint: str, _wallets=None):
        return {
            "score": 0.0,
            "cluster_size": 0,
            "smart_ratio": 0.0,
            "concentration": 0.0,
            "fresh_wallet_ratio": 0.0,
        }

    async def get_wallet_cluster_stats(_mint: str, _wallets=None):
        return {
            "cluster_size": 0,
            "smart_ratio": 0.0,
            "concentration": 0.0,
            "fresh_wallet_ratio": 0.0,
        }


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
BOOT_SYNTHETIC_UNIVERSE = os.getenv("BOOT_SYNTHETIC_UNIVERSE", "false").lower() == "true"

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

SNIPER_MULTIPLIER = float(os.getenv("SNIPER_MULTIPLIER", "1.35"))
SMART_MULTIPLIER = float(os.getenv("SMART_MULTIPLIER", "1.15"))
MOMENTUM_MULTIPLIER = float(os.getenv("MOMENTUM_MULTIPLIER", "1.05"))
STABLE_MULTIPLIER = float(os.getenv("STABLE_MULTIPLIER", "1.12"))

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

SEARCH_TERMS = ["SOL", "USDC", "BONK", "MEME", "PEPE", "DOG", "AI", "PUMP", "NEW", "MOON", "100x"]
MEME_SEARCH_TERMS = ["pumpfun", "pepe", "doge", "meme", "cat", "frog", "moonshot", "100x"]

JUPITER_PROGRAM_ID = os.getenv(
    "JUPITER_PROGRAM_ID",
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4",
)

FUND_BRAIN_UPDATE_SEC = int(os.getenv("FUND_BRAIN_UPDATE_SEC", "20"))
FUND_MIN_TRADES = int(os.getenv("FUND_MIN_TRADES", "3"))

FUND_STABLE_BASE = float(os.getenv("FUND_STABLE_BASE", "0.40"))
FUND_SNIPER_BASE = float(os.getenv("FUND_SNIPER_BASE", "0.20"))
FUND_SMART_BASE = float(os.getenv("FUND_SMART_BASE", "0.35"))
FUND_MOMENTUM_BASE = float(os.getenv("FUND_MOMENTUM_BASE", "0.35"))
FUND_EXPLORE_BASE = float(os.getenv("FUND_EXPLORE_BASE", "0.05"))

USE_JITO = os.getenv("USE_JITO", "false").lower() == "true"
JITO_TIP_SOL = float(os.getenv("JITO_TIP_SOL", "0.0005"))
JITO_MIN_SCORE = float(os.getenv("JITO_MIN_SCORE", "0.125"))
JITO_ONLY_A_PLUS = os.getenv("JITO_ONLY_A_PLUS", "true").lower() == "true"

SNIPER_RECENT_WINDOW_SEC = int(os.getenv("SNIPER_RECENT_WINDOW_SEC", "10"))
EARLY_ENTRY_BONUS = float(os.getenv("EARLY_ENTRY_BONUS", "0.02"))
MEMPOOL_RECENCY_BONUS = float(os.getenv("MEMPOOL_RECENCY_BONUS", "0.025"))
MEMPOOL_MAX_AGE_SEC = int(os.getenv("MEMPOOL_MAX_AGE_SEC", "25"))

WALLET_GRAPH_WEIGHT = float(os.getenv("WALLET_GRAPH_WEIGHT", "0.12"))
WALLET_GRAPH_MIN_SCORE = float(os.getenv("WALLET_GRAPH_MIN_SCORE", "0.00"))
WALLET_GRAPH_TIMEOUT_SEC = float(os.getenv("WALLET_GRAPH_TIMEOUT_SEC", "1.0"))
WALLET_GRAPH_BONUS_CAP = float(os.getenv("WALLET_GRAPH_BONUS_CAP", "0.18"))
MAX_WALLET_CLUSTER_CONCENTRATION = float(os.getenv("MAX_WALLET_CLUSTER_CONCENTRATION", "0.65"))
MIN_SMART_RATIO = float(os.getenv("MIN_SMART_RATIO", "0.00"))
MIN_FRESH_WALLET_RATIO = float(os.getenv("MIN_FRESH_WALLET_RATIO", "0.00"))

RPC_CONFIRM_RETRY = int(os.getenv("RPC_CONFIRM_RETRY", "3"))
SNIPER_A_PLUS_ONLY = os.getenv("SNIPER_A_PLUS_ONLY", "false").lower() == "true"
HARD_REJECT_NON_JUPITER_PRICE = os.getenv("HARD_REJECT_NON_JUPITER_PRICE", "false").lower() == "true"

INSTITUTIONAL_MIN_TRADES = int(os.getenv("INSTITUTIONAL_MIN_TRADES", "8"))
INSTITUTIONAL_LOSS_PAUSE_STREAK = int(os.getenv("INSTITUTIONAL_LOSS_PAUSE_STREAK", "5"))
INSTITUTIONAL_LOSS_PAUSE_SEC = int(os.getenv("INSTITUTIONAL_LOSS_PAUSE_SEC", "600"))
DAILY_LOSS_LIMIT_SOL = float(os.getenv("DAILY_LOSS_LIMIT_SOL", "0.60"))
MAX_STRATEGY_EXPOSURE = float(os.getenv("MAX_STRATEGY_EXPOSURE", "0.18"))
MAX_SNIPER_EXPOSURE = float(os.getenv("MAX_SNIPER_EXPOSURE", "0.14"))

# =========================================================
# V80 3-STRATEGY CONFIG
# =========================================================
STABLE_ENTRY_THRESHOLD = float(os.getenv("STABLE_ENTRY_THRESHOLD", "0.075"))
SNIPER_ENTRY_THRESHOLD = float(os.getenv("SNIPER_ENTRY_THRESHOLD", "0.065"))
MOMENTUM_ENTRY_THRESHOLD = float(os.getenv("MOMENTUM_ENTRY_THRESHOLD", "0.082"))

STABLE_TOP_K = int(os.getenv("STABLE_TOP_K", "3"))
SNIPER_TOP_K = int(os.getenv("SNIPER_TOP_K", "2"))

STABLE_WALLET_GRAPH_CUTOFF = float(os.getenv("STABLE_WALLET_GRAPH_CUTOFF", "0.45"))
STABLE_SMART_CUTOFF = float(os.getenv("STABLE_SMART_CUTOFF", "0.45"))


# =========================================================
# RUNTIME MEMORY
# =========================================================
LAST_TRADE = defaultdict(float)
LAST_PRICE = {}
LAST_MOMENTUM = {}
LAST_PRICE_SOURCE = {}
TOKEN_TRADE_COUNT = defaultdict(int)
BLACKLIST = {}

SOURCE_STATS = defaultdict(lambda: {"count": 0, "wins": 0, "losses": 0, "total_pnl": 0.0})
STRATEGY_STATS = defaultdict(lambda: {"count": 0, "wins": 0, "losses": 0, "total_pnl": 0.0})
SCORE_COMPONENT_STATS = defaultdict(lambda: {"count": 0, "sum": 0.0})

BUY_TIMES = []
MEMPOOL_BUFFER = []
MEMPOOL_TASK = None

BREATHING_STATE = {"risk_mult": 1.0, "cooldown_until": 0.0}
REGIME_STATE = {"mode": "neutral", "last_update": 0.0}
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

FUND_ALLOCATOR = {
    "stable": FUND_STABLE_BASE,
    "sniper": FUND_SNIPER_BASE,
    "smart": FUND_SMART_BASE,
    "momentum": FUND_MOMENTUM_BASE,
    "explore": FUND_EXPLORE_BASE,
}
FUND_PERF = defaultdict(lambda: {"pnl": 0.0, "trades": 0, "wins": 0, "losses": 0})
FUND_STATE = {"last_update": 0.0, "last_reason": "boot"}

MEMPOOL_SEEN_TS = {}
MEMPOOL_HITS = defaultdict(int)
WALLET_GRAPH_CACHE = {}
JITO_STATS = {"sent": 0, "ok": 0, "fail": 0, "last_error": ""}
INSTITUTIONAL_STATE = {
    "pause_until": 0.0,
    "daily_realized_pnl_sol": 0.0,
    "day_bucket": int(time.time() // 86400),
    "last_reason": "boot",
}


# =========================================================
# HELPERS
# =========================================================
def ensure_engine_state():
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
        "jito_sent": 0,
        "jito_ok": 0,
        "jito_fail": 0,
    }
    for k, v in defaults.items():
        engine.stats.setdefault(k, v)


def reset_runtime_memory():
    LAST_TRADE.clear()
    LAST_PRICE.clear()
    LAST_MOMENTUM.clear()
    LAST_PRICE_SOURCE.clear()
    TOKEN_TRADE_COUNT.clear()
    BLACKLIST.clear()

    SOURCE_STATS.clear()
    STRATEGY_STATS.clear()
    SCORE_COMPONENT_STATS.clear()

    BUY_TIMES.clear()
    MEMPOOL_BUFFER.clear()

    BREATHING_STATE["risk_mult"] = 1.0
    BREATHING_STATE["cooldown_until"] = 0.0

    REGIME_STATE["mode"] = "neutral"
    REGIME_STATE["last_update"] = 0.0

    AGENT_STATE["last_update"] = 0.0
    AGENT_STATE["mode"] = "normal"
    AGENT_STATE["risk_mult"] = 1.0
    AGENT_STATE["confidence"] = 0.5
    AGENT_STATE["cooldown_until"] = 0.0
    AGENT_STATE["last_reason"] = "boot"

    AUTO_PARAMS["entry_threshold"] = ENTRY_THRESHOLD
    AUTO_PARAMS["take_profit"] = TAKE_PROFIT
    AUTO_PARAMS["stop_loss"] = STOP_LOSS

    FUND_ALLOCATOR.clear()
    FUND_ALLOCATOR.update({
        "stable": FUND_STABLE_BASE,
        "sniper": FUND_SNIPER_BASE,
        "smart": FUND_SMART_BASE,
        "momentum": FUND_MOMENTUM_BASE,
        "explore": FUND_EXPLORE_BASE,
    })

    FUND_PERF.clear()
    FUND_STATE["last_update"] = 0.0
    FUND_STATE["last_reason"] = "boot"

    MEMPOOL_SEEN_TS.clear()
    MEMPOOL_HITS.clear()
    WALLET_GRAPH_CACHE.clear()

    JITO_STATS["sent"] = 0
    JITO_STATS["ok"] = 0
    JITO_STATS["fail"] = 0
    JITO_STATS["last_error"] = ""

    INSTITUTIONAL_STATE["pause_until"] = 0.0
    INSTITUTIONAL_STATE["daily_realized_pnl_sol"] = 0.0
    INSTITUTIONAL_STATE["day_bucket"] = int(time.time() // 86400)
    INSTITUTIONAL_STATE["last_reason"] = "boot"


def ensure_runtime():
    ensure_engine_state()

from app.state import engine as _engine
engine = _engine
