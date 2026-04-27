from __future__ import annotations

import os
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


def _quote_urls() -> list[str]:
    urls = [
        os.getenv("JUP_QUOTE_URL", "").strip(),
        os.getenv("JUP_QUOTE_URL_BACKUP", "").strip(),
        "https://lite-api.jup.ag/swap/v1/quote",
        "https://quote-api.jup.ag/v6/quote",
    ]
    out = []
    for u in urls:
        if u and u not in out:
            out.append(u)
    return out


async def get_quote_multi(
    input_mint: str,
    output_mint: str,
    amount: int,
) -> dict:
    params = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": int(amount),
        "slippageBps": _i(os.getenv("SLIPPAGE_BPS", "150"), 150),
    }

    last_error = None

    for url in _quote_urls():
        try:
            async with httpx.AsyncClient(
                timeout=8,
                limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Accept": "application/json",
                },
            ) as client:
                r = await client.get(url, params=params)
                r.raise_for_status()
                data = r.json()

            if isinstance(data, dict) and not data.get("error"):
                return data

            last_error = data

        except Exception as e:
            last_error = str(e)

    return {
        "error": "ALL_QUOTE_FAILED",
        "last_error": last_error,
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": amount,
    }


def quote_is_tradable(quote: dict) -> tuple[bool, str]:
    if not quote or quote.get("error"):
        return False, f"quote_error:{quote}"

    out_amount = _i(quote.get("outAmount", 0), 0)
    impact = _f(quote.get("priceImpactPct", 1), 1)

    min_out = _i(os.getenv("MIN_OUT_AMOUNT", "1"), 1)
    max_impact = _f(os.getenv("MAX_PRICE_IMPACT", "0.50"), 0.50)

    if out_amount < min_out:
        return False, f"low_out:{out_amount}<{min_out}"

    if impact > max_impact:
        return False, f"high_impact:{impact}>{max_impact}"

    return True, "ok"
