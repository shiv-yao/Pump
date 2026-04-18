from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


class Signal(BaseModel):
    token: str
    source: str
    score: float = Field(ge=0.0, le=1.0)
    narrative: str


class Decision(BaseModel):
    token: str
    action: Literal["BUY", "WATCH", "SKIP"]
    size: float = Field(ge=0.0)
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str


class TradeResult(BaseModel):
    token: str
    status: Literal["SIMULATED", "EXECUTED", "SKIPPED", "FAILED"]
    amount: float = Field(ge=0.0)
    venue: str
    detail: dict


class PipelineResponse(BaseModel):
    signals: list[Signal]
    decisions: list[Decision]
    trades: list[TradeResult]


class RunRequest(BaseModel):
    watchlist: list[str] = Field(default_factory=lambda: ["PEPE", "BONK", "WIF", "PUMPDOGE"])
    max_buys: int = 2


class PluginRecord(BaseModel):
    id: int
    name: str
    slug: str
    monthly_price_usd: int
    enabled: bool = False
    description: str
