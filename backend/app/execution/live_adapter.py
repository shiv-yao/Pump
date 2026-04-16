from __future__ import annotations

# Replace this file with your verified Jupiter execution implementation.
# The function signature is intentionally simple so the product layer can call it safely.


def execute_verified_trade(
    symbol: str,
    size_usd: float,
    side: str = "buy",
    metadata: dict | None = None,
) -> dict:
    '''
    Safe default adapter.
    Replace the body with your verified execution implementation only after testing.

    Expected return shape:
    {
        "ok": True/False,
        "provider": "jupiter_v2",
        "symbol": "...",
        "size_usd": 100.0,
        "tx_id": "optional",
        "details": {...}
    }
    '''
    return {
        "ok": True,
        "provider": "integration_stub",
        "symbol": symbol,
        "size_usd": size_usd,
        "tx_id": None,
        "details": {
            "message": "Replace app/execution/live_adapter.py with your verified execution code."
        },
    }
