from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health():
    return {
        "status": "ok",
        "services": {
            "api": "up",
            "market_stream": "configured",
            "feature_engine": "configured",
            "ai_fund_brain": "configured",
            "risk_engine": "configured",
            "execution_engine": "configured",
            "portfolio_engine": "configured",
            "strategy_router": "configured",
            "replay_engine": "configured",
            "observer_logger": "configured",
            "trading_loop": "running",
            "dashboard": "mounted",
            "redis": "configured",
            "postgresql": "configured",
        },
    }
