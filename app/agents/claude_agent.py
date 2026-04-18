from __future__ import annotations

from app.models.schemas import Signal, Decision


class ClaudeAgent:
    """Decision layer.

    Converts candidate signals into portfolio actions using simple,
    deterministic risk logic. This is the easiest place to later insert a real
    allocator or LLM review step.
    """

    def evaluate(self, signals: list[Signal], max_buys: int = 2) -> list[Decision]:
        decisions: list[Decision] = []
        buys_used = 0
        for signal in signals:
            if signal.score >= 0.72 and buys_used < max_buys:
                action = "BUY"
                size = 0.02 if signal.score > 0.85 else 0.01
                reason = f"High conviction from {signal.source}: {signal.narrative}"
                buys_used += 1
            elif signal.score >= 0.50:
                action = "WATCH"
                size = 0.0
                reason = f"Monitor only: decent score with moderate confidence"
            else:
                action = "SKIP"
                size = 0.0
                reason = "Below risk threshold"

            decisions.append(
                Decision(
                    token=signal.token,
                    action=action,
                    size=size,
                    confidence=signal.score,
                    reason=reason,
                )
            )
        return decisions
