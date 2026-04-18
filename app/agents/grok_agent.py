from __future__ import annotations

import random
from app.models.schemas import Signal


class GrokAgent:
    """Market-intel layer.

    Current version uses lightweight heuristics and randomization so the app
    can run out of the box. Replace `find_opportunities` with real data feeds
    later (Dexscreener / X / custom scanners).
    """

    narratives = [
        "social buzz rising",
        "wallet activity increasing",
        "fresh listing momentum",
        "short-term breakout setup",
    ]

    def find_opportunities(self, watchlist: list[str]) -> list[Signal]:
        signals: list[Signal] = []
        for token in watchlist:
            base = 0.35 + (sum(ord(c) for c in token) % 40) / 100
            noise = random.uniform(-0.08, 0.12)
            score = max(0.0, min(1.0, base + noise))
            signals.append(
                Signal(
                    token=token,
                    source="grok",
                    score=score,
                    narrative=random.choice(self.narratives),
                )
            )
        return sorted(signals, key=lambda x: x.score, reverse=True)
