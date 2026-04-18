from __future__ import annotations

from datetime import datetime, UTC
from app.models.schemas import Decision, TradeResult


async def simulate_trade(decision: Decision) -> TradeResult:
    if decision.action != "BUY":
        return TradeResult(
            token=decision.token,
            status="SKIPPED",
            amount=0,
            venue="simulator",
            detail={"reason": decision.reason},
        )

    fake_fill = round(1 + (decision.confidence - 0.5) * 0.04, 6)
    return TradeResult(
        token=decision.token,
        status="SIMULATED",
        amount=decision.size,
        venue="simulator",
        detail={
            "fill_multiplier": fake_fill,
            "timestamp": datetime.now(UTC).isoformat(),
            "reason": decision.reason,
        },
    )
