from __future__ import annotations

import os

REQUIRED_ENV = [
    "SOLANA_RPC",
    "SOLANA_WS",
    "JUP_QUOTE_URL",
    "JUP_QUOTE_URL_BACKUP",
    "AUTO_TRADING",
    "ENABLE_ONCHAIN_SNIPER",
    "REAL_TRADING",
    "MANUAL_CONFIRM",
]

RECOMMENDED_ENV = [
    "SLIPPAGE_BPS",
    "PRIORITY_FEE",
    "MAX_POSITION_PER_TRADE",
    "MIN_OUT_AMOUNT",
    "MAX_PRICE_IMPACT",
    "TRADE_READY_RETRIES",
    "TRADE_READY_DELAY_SEC",
]


def env_value(name: str) -> str:
    return os.getenv(name, "").strip()


def check_env() -> dict:
    missing_required = [k for k in REQUIRED_ENV if not env_value(k)]
    missing_recommended = [k for k in RECOMMENDED_ENV if not env_value(k)]

    values = {
        k: env_value(k)
        for k in REQUIRED_ENV + RECOMMENDED_ENV
    }

    ok = len(missing_required) == 0

    return {
        "ok": ok,
        "missing_required": missing_required,
        "missing_recommended": missing_recommended,
        "values": values,
        "message": "ENV OK" if ok else "ENV MISSING REQUIRED VARIABLES",
    }


def assert_env_ready():
    result = check_env()
    if not result["ok"]:
        raise RuntimeError(
            "ENV not ready. Missing: "
            + ", ".join(result["missing_required"])
        )
