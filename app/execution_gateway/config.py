import os

TRADING_API_BASE = os.getenv("TRADING_API_BASE", "").rstrip("/")
POLYMARKET_API_KEY = os.getenv("POLYMARKET_API_KEY", "").strip()

GATEWAY_TIMEOUT = float(os.getenv("GATEWAY_TIMEOUT", "5"))
GATEWAY_RETRY = int(os.getenv("GATEWAY_RETRY", "2"))
