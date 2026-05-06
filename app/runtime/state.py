from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class SystemState:
    mode: str = "paper"
    running: bool = False
    pnl: float = 0.0
    positions: list[dict[str, Any]] = field(default_factory=list)
    equity: float = 10000.0
    exposure: float = 0.0
    last_tick: dict[str, Any] | None = None
    feature_snapshot: dict[str, Any] | None = None
    decision_snapshot: dict[str, Any] | None = None
    events: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=200))

    def add_event(self, event_type: str, payload: dict[str, Any]) -> None:
        self.events.appendleft(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "type": event_type,
                "payload": payload,
            }
        )


SYSTEM_STATE = SystemState()
