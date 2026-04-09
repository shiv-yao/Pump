import os

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

REAL_TRADING = env_bool("REAL_TRADING", False)
USE_JITO = env_bool("USE_JITO", False)

JUP_API_KEY = os.getenv("JUP_API_KEY", "").strip()
JUP_SWAP_BASE = os.getenv("JUP_SWAP_BASE", "https://api.jup.ag/swap/v2").rstrip("/")
SOLANA_RPC_HTTP = os.getenv("SOLANA_RPC_HTTP", "https://api.mainnet-beta.solana.com").strip()
JITO_BASE_URL = os.getenv("JITO_BASE_URL", "https://mainnet.block-engine.jito.wtf").rstrip("/")
JITO_AUTH_UUID = os.getenv("JITO_AUTH_UUID", "").strip()

SOLANA_PRIVATE_KEY_B58 = os.getenv("SOLANA_PRIVATE_KEY_B58", os.getenv("PRIVATE_KEY_B58", "")).strip()
BIRDEYE_API_KEY = os.getenv("BIRDEYE_API_KEY", "").strip()

SOL_MINT = "So11111111111111111111111111111111111111112"
SOL_DECIMALS = 1_000_000_000

HTTP_TIMEOUT = env_float("HTTP_TIMEOUT", 8.0)
