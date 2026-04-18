from __future__ import annotations

from app.config import settings
from app.models.schemas import Decision, TradeResult
from app.execution.simulator import simulate_trade
from app.execution.jupiter_stub import execute_trade


class GPTAgent:
    """Execution layer."""

    async def execute(self, decisions: list[Decision]) -> list[TradeResult]:
        results: list[TradeResult] = []
        for decision in decisions:
            if settings.real_trading:
                result = await execute_trade(decision)
            else:
                result = await simulate_trade(decision)
            results.append(result)
        return results
