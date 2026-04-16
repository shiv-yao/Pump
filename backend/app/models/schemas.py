from typing import Literal, Optional
from pydantic import BaseModel, EmailStr, Field


class SignUpRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    full_name: str = Field(min_length=1)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: str
    email: EmailStr
    full_name: str
    plan: Literal["free", "pro", "fund"]
    active: bool


class SessionResponse(BaseModel):
    user: UserResponse
    token: str


class CheckoutRequest(BaseModel):
    plan: Literal["pro", "fund"]


class TradingConfig(BaseModel):
    paper_mode: bool = True
    strategy_mode: Literal["safe", "balanced", "aggressive"] = "safe"
    execution_provider: Literal["mock", "integration"] = "mock"
    max_position_usd: float = 100.0
    daily_loss_limit_usd: float = 100.0
    auto_trading_enabled: bool = False


class UpdateTradingConfigRequest(TradingConfig):
    pass


class DashboardMetrics(BaseModel):
    total_return_pct: float
    win_rate_pct: float
    max_drawdown_pct: float
    active_strategies: int
    monthly_revenue_usd: float


class StrategyAttributionItem(BaseModel):
    name: str
    pnl_usd: float
    weight_pct: float


class ReportResponse(BaseModel):
    period: Literal["weekly", "monthly"]
    summary: str
    metrics: DashboardMetrics
    attribution: list[StrategyAttributionItem]\n