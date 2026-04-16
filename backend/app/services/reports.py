from __future__ import annotations

from app.alpha_ecosystem.service import active_ecosystem
from app.db.database import db
from app.investor.service import investor_overview
from app.models.schemas import DashboardMetrics, ReportResponse, StrategyAttributionItem


def build_dashboard_metrics(user_id: str) -> DashboardMetrics:
    with db() as conn:
        state = conn.execute(
            "SELECT total_pnl_usd, win_rate_pct, max_drawdown_pct FROM trading_state WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        user = conn.execute("SELECT plan FROM users WHERE id = ?", (user_id,)).fetchone()

    total_return = round(float(state["total_pnl_usd"]) / 1000 * 100, 2)
    monthly_revenue = 0.0
    if user["plan"] == "pro":
        monthly_revenue = 29.0
    elif user["plan"] == "fund":
        monthly_revenue = 199.0

    return DashboardMetrics(
        total_return_pct=total_return,
        win_rate_pct=float(state["win_rate_pct"]),
        max_drawdown_pct=float(state["max_drawdown_pct"]),
        active_strategies=len(active_ecosystem()),
        monthly_revenue_usd=monthly_revenue,
    )


def build_report(user_id: str, period: str) -> ReportResponse:
    limit = 50 if period == "weekly" else 200
    with db() as conn:
        rows = conn.execute(
            '''
            SELECT strategy_name, pnl_usd
            FROM trades
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            ''',
            (user_id, limit),
        ).fetchall()

    metrics = build_dashboard_metrics(user_id)
    by_strategy = {}
    for r in rows:
        by_strategy[r["strategy_name"]] = by_strategy.get(r["strategy_name"], 0.0) + float(r["pnl_usd"])

    total_abs = sum(abs(v) for v in by_strategy.values()) or 1.0
    attribution = [
        StrategyAttributionItem(name=k, pnl_usd=round(v, 2), weight_pct=round(abs(v) / total_abs * 100, 2))
        for k, v in by_strategy.items()
    ] or [StrategyAttributionItem(name="No trades yet", pnl_usd=0.0, weight_pct=100.0)]

    return ReportResponse(
        period=period,
        summary=f"{period.capitalize()} report generated from integrated AI Fund modules.",
        metrics=metrics,
        attribution=attribution,
    )


def build_investor_view(user_id: str) -> dict:
    metrics = build_dashboard_metrics(user_id).model_dump()
    return investor_overview(metrics)\n