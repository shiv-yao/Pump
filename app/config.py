import os


# =========================================================
# ENV HELPERS
# =========================================================
def env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return default


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


def env_str(name: str, default: str = "") -> str:
    try:
        return str(os.getenv(name, default)).strip()
    except Exception:
        return default


# =========================================================
# MODE
# =========================================================
REAL_TRADING = env_bool("REAL_TRADING", False)
USE_JITO = env_bool("USE_JITO", False)

# =========================================================
# KEYS / ENDPOINTS
# =========================================================
JUP_API_KEY = env_str("JUP_API_KEY", "")
JUP_SWAP_BASE = env_str("JUP_SWAP_BASE", "https://api.jup.ag/swap/v2").rstrip("/")

SOLANA_RPC_HTTP = env_str("SOLANA_RPC_HTTP", "https://api.mainnet-beta.solana.com")
SOLANA_RPC_WSS = env_str("SOLANA_RPC_WSS", "wss://api.mainnet-beta.solana.com")

JITO_BASE_URL = env_str("JITO_BASE_URL", "https://mainnet.block-engine.jito.wtf").rstrip("/")
JITO_AUTH_UUID = env_str("JITO_AUTH_UUID", "")

SOLANA_PRIVATE_KEY_B58 = env_str("SOLANA_PRIVATE_KEY_B58", env_str("PRIVATE_KEY_B58", ""))
BIRDEYE_API_KEY = env_str("BIRDEYE_API_KEY", "")

OPENAI_API_KEY = env_str("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = env_str("ANTHROPIC_API_KEY", "")
XAI_API_KEY = env_str("XAI_API_KEY", "")

# =========================================================
# CHAIN CONSTANTS
# =========================================================
SOL_MINT = "So11111111111111111111111111111111111111112"
SOL_DECIMALS = 1_000_000_000

# =========================================================
# NETWORK / TIMEOUT
# =========================================================
HTTP_TIMEOUT = env_float("HTTP_TIMEOUT", 8.0)
HTTP_GET_RETRY = env_int("HTTP_GET_RETRY", 2)
QUOTE_TIMEOUT_RETRY = env_int("QUOTE_TIMEOUT_RETRY", 3)
RPC_CONFIRM_RETRY = env_int("RPC_CONFIRM_RETRY", 3)

# =========================================================
# CORE POSITION / CAPITAL
# =========================================================
AMOUNT = env_int("AMOUNT", 1_000_000)

MAX_POSITIONS = env_int("MAX_POSITIONS", 2)
MAX_EXPOSURE = env_float("MAX_EXPOSURE", 0.20)
MAX_POSITION_SIZE = env_float("MAX_POSITION_SIZE", 0.03)
MIN_ORDER_SOL = env_float("MIN_ORDER_SOL", 0.015)

MAX_CAPITAL = env_float("MAX_CAPITAL", 20.0)
MAX_STRATEGY_EXPOSURE = env_float("MAX_STRATEGY_EXPOSURE", 0.18)
MAX_SNIPER_EXPOSURE = env_float("MAX_SNIPER_EXPOSURE", 0.14)

# =========================================================
# ENTRY / EXIT
# =========================================================
ENTRY_THRESHOLD = env_float("ENTRY_THRESHOLD", 0.065)
STABLE_ENTRY_THRESHOLD = env_float("STABLE_ENTRY_THRESHOLD", 0.075)
SNIPER_ENTRY_THRESHOLD = env_float("SNIPER_ENTRY_THRESHOLD", 0.060)
MOMENTUM_ENTRY_THRESHOLD = env_float("MOMENTUM_ENTRY_THRESHOLD", 0.078)

TAKE_PROFIT = env_float("TAKE_PROFIT", 0.035)
STOP_LOSS = env_float("STOP_LOSS", -0.012)
HARD_STOP_LOSS = env_float("HARD_STOP_LOSS", -0.015)
TRAILING_GAP = env_float("TRAILING_GAP", 0.012)

MAX_HOLD_SEC = env_int("MAX_HOLD_SEC", 120)
FORCE_EXIT_SEC = env_int("FORCE_EXIT_SEC", 90)

# =========================================================
# PRICE / LIQUIDITY
# =========================================================
MIN_LIQUIDITY_TRADE = env_float("MIN_LIQUIDITY_TRADE", 4000)
MIN_LIQUIDITY_OBSERVE = env_float("MIN_LIQUIDITY_OBSERVE", 1500)
MIN_OUT_AMOUNT = env_int("MIN_OUT_AMOUNT", 300)

MAX_PRICE_JUPITER = env_float("MAX_PRICE_JUPITER", 0.10)
MAX_PRICE_FALLBACK = env_float("MAX_PRICE_FALLBACK", 10.0)
HARD_REJECT_NON_JUPITER_PRICE = env_bool("HARD_REJECT_NON_JUPITER_PRICE", False)

DEFAULT_TOKEN_DECIMALS = env_int("DEFAULT_TOKEN_DECIMALS", 6)
ESTIMATED_TX_FEE_SOL = env_float("ESTIMATED_TX_FEE_SOL", 0.000005)
ENABLE_EQUITY_MARK = env_bool("ENABLE_EQUITY_MARK", True)

# =========================================================
# LOOP / TIMING
# =========================================================
LOOP_SLEEP_SEC = env_float("LOOP_SLEEP_SEC", 2.0)
TOKEN_COOLDOWN = env_int("TOKEN_COOLDOWN", 12)
BLACKLIST_TIME = env_int("BLACKLIST_TIME", 45)
FORCE_TRADE_AFTER = env_int("FORCE_TRADE_AFTER", 20)

MAX_TOKENS_PER_CYCLE = env_int("MAX_TOKENS_PER_CYCLE", 80)
TOP_K_PRESELECT = env_int("TOP_K_PRESELECT", 3)
TOP_N_TO_TRADE = env_int("TOP_N_TO_TRADE", 1)
MAX_NEW_BUYS_PER_CYCLE = env_int("MAX_NEW_BUYS_PER_CYCLE", 1)
MAX_BUYS_PER_10MIN = env_int("MAX_BUYS_PER_10MIN", 4)
BUY_WINDOW_SEC = env_int("BUY_WINDOW_SEC", 600)

# =========================================================
# SCORE / FILTER
# =========================================================
FILTER_SCORE_BYPASS = env_float("FILTER_SCORE_BYPASS", 0.12)
SOFT_DISABLE_FILTER = env_bool("SOFT_DISABLE_FILTER", False)

MIN_CONFIRM_MOMENTUM = env_float("MIN_CONFIRM_MOMENTUM", 0.0015)
MIN_CONFIRM_BREAKOUT = env_float("MIN_CONFIRM_BREAKOUT", 0.0020)
MAX_BREAKOUT_ABS = env_float("MAX_BREAKOUT_ABS", 0.18)
MAX_SCORE = env_float("MAX_SCORE", 1.5)
MAX_PNL_ABS = env_float("MAX_PNL_ABS", 0.25)
STRICT_A_TIER_THRESHOLD = env_float("STRICT_A_TIER_THRESHOLD", 0.095)

# =========================================================
# ALPHA WEIGHTS
# =========================================================
ALPHA_BREAKOUT_WEIGHT = env_float("ALPHA_BREAKOUT_WEIGHT", 0.35)
ALPHA_MOMENTUM_WEIGHT = env_float("ALPHA_MOMENTUM_WEIGHT", 0.25)
ALPHA_SMART_WEIGHT = env_float("ALPHA_SMART_WEIGHT", 0.25)
ALPHA_LIQ_WEIGHT = env_float("ALPHA_LIQ_WEIGHT", 0.10)
ALPHA_WALLET_WEIGHT = env_float("ALPHA_WALLET_WEIGHT", 0.05)

# =========================================================
# STRATEGY MULTIPLIERS
# =========================================================
STABLE_MULTIPLIER = env_float("STABLE_MULTIPLIER", 1.12)
SNIPER_MULTIPLIER = env_float("SNIPER_MULTIPLIER", 1.45)
SMART_MULTIPLIER = env_float("SMART_MULTIPLIER", 1.12)
MOMENTUM_MULTIPLIER = env_float("MOMENTUM_MULTIPLIER", 1.05)

STABLE_TOP_K = env_int("STABLE_TOP_K", 3)
SNIPER_TOP_K = env_int("SNIPER_TOP_K", 2)
STABLE_WALLET_GRAPH_CUTOFF = env_float("STABLE_WALLET_GRAPH_CUTOFF", 0.45)
STABLE_SMART_CUTOFF = env_float("STABLE_SMART_CUTOFF", 0.45)
SNIPER_A_PLUS_ONLY = env_bool("SNIPER_A_PLUS_ONLY", False)

# =========================================================
# AI
# =========================================================
AI_MIN_WIN_PROB = env_float("AI_MIN_WIN_PROB", 0.47)

# =========================================================
# AGENT
# =========================================================
AGENT_UPDATE_SEC = env_int("AGENT_UPDATE_SEC", 20)
AGENT_MIN_TRADES = env_int("AGENT_MIN_TRADES", 5)
AGENT_LOOKBACK_TRADES = env_int("AGENT_LOOKBACK_TRADES", 10)
AGENT_BULL_WINRATE = env_float("AGENT_BULL_WINRATE", 0.60)
AGENT_BEAR_WINRATE = env_float("AGENT_BEAR_WINRATE", 0.35)
AGENT_RISK_MIN = env_float("AGENT_RISK_MIN", 0.45)
AGENT_RISK_MAX = env_float("AGENT_RISK_MAX", 1.35)

AGENT_DEFENSIVE_ENTRY = env_float("AGENT_DEFENSIVE_ENTRY", 0.095)
AGENT_NORMAL_ENTRY = env_float("AGENT_NORMAL_ENTRY", 0.085)
AGENT_AGGRESSIVE_ENTRY = env_float("AGENT_AGGRESSIVE_ENTRY", 0.070)

AGENT_DEFENSIVE_TP = env_float("AGENT_DEFENSIVE_TP", 0.018)
AGENT_NORMAL_TP = env_float("AGENT_NORMAL_TP", 0.022)
AGENT_AGGRESSIVE_TP = env_float("AGENT_AGGRESSIVE_TP", 0.035)

AGENT_DEFENSIVE_SL = env_float("AGENT_DEFENSIVE_SL", -0.010)
AGENT_NORMAL_SL = env_float("AGENT_NORMAL_SL", -0.012)
AGENT_AGGRESSIVE_SL = env_float("AGENT_AGGRESSIVE_SL", -0.014)

AGENT_KILL_LOSS_STREAK = env_int("AGENT_KILL_LOSS_STREAK", 4)
AGENT_KILL_COOLDOWN_SEC = env_int("AGENT_KILL_COOLDOWN_SEC", 300)
AGENT_FORCE_TRADE_ENABLE = env_bool("AGENT_FORCE_TRADE_ENABLE", True)

# =========================================================
# BREATHING / RISK ADAPT
# =========================================================
BREATHING_LOSS_STREAK = env_int("BREATHING_LOSS_STREAK", 2)
BREATHING_COOLDOWN_SEC = env_int("BREATHING_COOLDOWN_SEC", 180)
BREATHING_MIN_RISK_MULT = env_float("BREATHING_MIN_RISK_MULT", 0.45)
BREATHING_MAX_RISK_MULT = env_float("BREATHING_MAX_RISK_MULT", 1.20)

# =========================================================
# FUND BRAIN
# =========================================================
FUND_BRAIN_UPDATE_SEC = env_int("FUND_BRAIN_UPDATE_SEC", 20)
FUND_MIN_TRADES = env_int("FUND_MIN_TRADES", 3)

FUND_STABLE_BASE = env_float("FUND_STABLE_BASE", 0.35)
FUND_SNIPER_BASE = env_float("FUND_SNIPER_BASE", 0.30)
FUND_SMART_BASE = env_float("FUND_SMART_BASE", 0.40)
FUND_MOMENTUM_BASE = env_float("FUND_MOMENTUM_BASE", 0.35)
FUND_EXPLORE_BASE = env_float("FUND_EXPLORE_BASE", 0.05)

# =========================================================
# EXPLORATION
# =========================================================
EXPLORATION_ENABLE = env_bool("EXPLORATION_ENABLE", True)
EXPLORATION_MIN_SCORE = env_float("EXPLORATION_MIN_SCORE", 0.04)
EXPLORATION_SIZE_FRAC = env_float("EXPLORATION_SIZE_FRAC", 0.03)

# =========================================================
# MEMPOOL / EARLY
# =========================================================
MEMPOOL_WSS = env_str("MEMPOOL_WSS", "wss://api.mainnet-beta.solana.com")
JUPITER_PROGRAM_ID = env_str(
    "JUPITER_PROGRAM_ID",
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4",
)

SNIPER_RECENT_WINDOW_SEC = env_int("SNIPER_RECENT_WINDOW_SEC", 18)
EARLY_ENTRY_BONUS = env_float("EARLY_ENTRY_BONUS", 0.025)
MEMPOOL_RECENCY_BONUS = env_float("MEMPOOL_RECENCY_BONUS", 0.035)
MEMPOOL_MAX_AGE_SEC = env_int("MEMPOOL_MAX_AGE_SEC", 25)

# =========================================================
# WALLET GRAPH
# =========================================================
WALLET_TRACKER_TIMEOUT_SEC = env_float("WALLET_TRACKER_TIMEOUT_SEC", 1.2)
WALLET_GRAPH_TIMEOUT_SEC = env_float("WALLET_GRAPH_TIMEOUT_SEC", 1.0)
WALLET_GRAPH_WEIGHT = env_float("WALLET_GRAPH_WEIGHT", 0.12)
WALLET_GRAPH_MIN_SCORE = env_float("WALLET_GRAPH_MIN_SCORE", 0.00)
WALLET_GRAPH_BONUS_CAP = env_float("WALLET_GRAPH_BONUS_CAP", 0.18)
MAX_WALLET_CLUSTER_CONCENTRATION = env_float("MAX_WALLET_CLUSTER_CONCENTRATION", 0.65)
MIN_SMART_RATIO = env_float("MIN_SMART_RATIO", 0.00)
MIN_FRESH_WALLET_RATIO = env_float("MIN_FRESH_WALLET_RATIO", 0.00)

# =========================================================
# JITO
# =========================================================
JITO_TIP_SOL = env_float("JITO_TIP_SOL", 0.0005)
JITO_MIN_SCORE = env_float("JITO_MIN_SCORE", 0.125)
JITO_ONLY_A_PLUS = env_bool("JITO_ONLY_A_PLUS", True)

# =========================================================
# INSTITUTIONAL RISK
# =========================================================
INSTITUTIONAL_MIN_TRADES = env_int("INSTITUTIONAL_MIN_TRADES", 8)
INSTITUTIONAL_LOSS_PAUSE_STREAK = env_int("INSTITUTIONAL_LOSS_PAUSE_STREAK", 5)
INSTITUTIONAL_LOSS_PAUSE_SEC = env_int("INSTITUTIONAL_LOSS_PAUSE_SEC", 600)
DAILY_LOSS_LIMIT_SOL = env_float("DAILY_LOSS_LIMIT_SOL", 0.20)
MAX_TRADES_PER_DAY = env_int("MAX_TRADES_PER_DAY", 20)

# =========================================================
# UNIVERSE / BOOT
# =========================================================
MIN_UNIVERSE = env_int("MIN_UNIVERSE", 20)
BOOT_SYNTHETIC_UNIVERSE = env_bool("BOOT_SYNTHETIC_UNIVERSE", False)

# =========================================================
# OPTIONAL / SEARCH
# =========================================================
ADAPTIVE_THRESHOLD_MIN = env_float("ADAPTIVE_THRESHOLD_MIN", 0.04)
ADAPTIVE_THRESHOLD_MAX = env_float("ADAPTIVE_THRESHOLD_MAX", 0.10)

# =========================================================
# PNL / ACCOUNTING FIX
# =========================================================
ENABLE_TRUE_SELL_ACCOUNTING = env_bool("ENABLE_TRUE_SELL_ACCOUNTING", True)
ENABLE_QUOTE_FALLBACK_ON_BUY = env_bool("ENABLE_QUOTE_FALLBACK_ON_BUY", True)
ENABLE_QUOTE_FALLBACK_ON_SELL = env_bool("ENABLE_QUOTE_FALLBACK_ON_SELL", True)
ENABLE_DECIMALS_FROM_QUOTE = env_bool("ENABLE_DECIMALS_FROM_QUOTE", True)
ENABLE_OUTAMOUNT_FROM_QUOTE = env_bool("ENABLE_OUTAMOUNT_FROM_QUOTE", True)

MARK_PRICE_MAX_MULT = env_float("MARK_PRICE_MAX_MULT", 50.0)
MARK_PRICE_MIN = env_float("MARK_PRICE_MIN", 0.0)
ENABLE_MARK_PRICE_CLAMP = env_bool("ENABLE_MARK_PRICE_CLAMP", True)
ENABLE_PRICE_JUMP_GUARD = env_bool("ENABLE_PRICE_JUMP_GUARD", True)
PRICE_JUMP_GUARD_PCT = env_float("PRICE_JUMP_GUARD_PCT", 0.25)
PRICE_JUMP_GUARD_SEC = env_int("PRICE_JUMP_GUARD_SEC", 20)

# =========================================================
# OPTIONAL LLM BRAIN
# =========================================================
ENABLE_LLM_BRAIN = env_bool("ENABLE_LLM_BRAIN", False)
LLM_REVIEW_TOP_K = env_int("LLM_REVIEW_TOP_K", 2)
LLM_MIN_SCORE = env_float("LLM_MIN_SCORE", 0.35)

LLM_ENABLE_OPENAI = env_bool("LLM_ENABLE_OPENAI", False)
LLM_ENABLE_CLAUDE = env_bool("LLM_ENABLE_CLAUDE", False)
LLM_ENABLE_GROK = env_bool("LLM_ENABLE_GROK", False)

OPENAI_MODEL = env_str("OPENAI_MODEL", "gpt-5.4")
ANTHROPIC_MODEL = env_str("ANTHROPIC_MODEL", "claude-sonnet-4.5")
XAI_MODEL = env_str("XAI_MODEL", "grok-4")
