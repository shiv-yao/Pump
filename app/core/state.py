from __future__ import annotations

from dataclasses import dataclass, field
from collections import deque
from typing import Any


@dataclass
class EngineState:
    running: bool = True
    logs: deque[str] = field(default_factory=lambda: deque(maxlen=300))
    trades: list[dict[str, Any]] = field(default_factory=list)
    plugins_enabled: dict[str, bool] = field(default_factory=dict)

    def log(self, msg: str) -> None:
        self.logs.appendleft(msg)


engine = EngineState()
