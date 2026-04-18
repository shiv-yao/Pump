from __future__ import annotations

from app.models.schemas import Decision, TradeResult


async def execute_trade(decision: Decision) -> TradeResult:
    """Placeholder for a real execution adapter.

    Keep disabled by default. Replace this with a proper quote/order/execute
    integration only after thoroughly testing on paper.
    """
    return TradeResult(
        token=decision.token,
        status="FAILED",
        amount=decision.size,
        venue="jupiter_stub",
        detail={
            "message": "Real trading disabled. Wire a real adapter and set REAL_TRADING=true.",
        },
    )
