from __future__ import annotations

import os
import time
import base64
import httpx
from typing import Any

SOL_MINT = "So11111111111111111111111111111111111111112"


def _i(x: Any, d: int = 0) -> int:
    try:
        return int(float(x))
    except Exception:
        return d


def _f(x: Any, d: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return d


def _b(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).lower() in {"1", "true", "yes", "on"}


async def safe_quote(
    input_mint: str,
    output_mint: str,
    size_sol: float,
) -> dict | None:
    amount = int(size_sol * 1_000_000_000)

    urls = [
        os.getenv("JUP_QUOTE_URL", "https://lite-api.jup.ag/swap/v1/quote"),
        os.getenv("JUP_QUOTE_URL_BACKUP", "https://quote-api.jup.ag/v6/quote"),
    ]

    last_error = None

    for url in urls:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(
                    url,
                    params={
                        "inputMint": input_mint,
                        "outputMint": output_mint,
                        "amount": amount,
                        "slippageBps": _i(os.getenv("SLIPPAGE_BPS", "120"), 120),
                    },
                )
                r.raise_for_status()
                data = r.json()

            if isinstance(data, dict) and not data.get("error"):
                return data

        except Exception as e:
            last_error = e

    return {
        "error": str(last_error) if last_error else "quote_failed",
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": amount,
    }


async def jupiter_order(
    output_mint: str,
    size_sol: float,
    quote: dict | None = None,
) -> dict:
    """
    Jupiter v2 /order wrapper.
    目前保留 paper + real-ready 結構。
    """
    if quote is None:
        quote = await safe_quote(SOL_MINT, output_mint, size_sol)

    if not quote or quote.get("error"):
        return {"success": False, "error": "quote_failed", "quote": quote}

    if not _b("REAL_TRADING", "false"):
        return {
            "success": True,
            "paper": True,
            "stage": "order",
            "message": "REAL_TRADING=false; order not requested",
            "quote": quote,
        }

    wallet = os.getenv("WALLET_PUBLIC_KEY") or os.getenv("PUBLIC_KEY") or ""
    if not wallet:
        return {
            "success": False,
            "error": "missing WALLET_PUBLIC_KEY/PUBLIC_KEY for real order",
            "quote": quote,
        }

    url = os.getenv("JUP_ORDER_URL", "https://api.jup.ag/swap/v2/order")

    payload = {
        "userPublicKey": wallet,
        "quoteResponse": quote,
        "prioritizationFeeLamports": _i(os.getenv("PRIORITY_FEE", "8000"), 8000),
    }

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(url, json=payload)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        return {"success": False, "error": str(e), "quote": quote}


async def jupiter_execute(signed_transaction: str, request_id: str | None = None) -> dict:
    """
    Jupiter v2 /execute wrapper.
    真的簽名要在你的 trade_order / wallet layer 做。
    """
    if not _b("REAL_TRADING", "false"):
        return {
            "success": True,
            "paper": True,
            "stage": "execute",
            "message": "REAL_TRADING=false; transaction not sent",
        }

    url = os.getenv("JUP_EXECUTE_URL", "https://api.jup.ag/swap/v2/execute")

    payload = {
        "signedTransaction": signed_transaction,
    }

    if request_id:
        payload["requestId"] = request_id

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(url, json=payload)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        return {"success": False, "error": str(e)}
