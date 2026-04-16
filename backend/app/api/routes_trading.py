from fastapi import APIRouter, Depends

from app.core.security import require_token
from app.models.schemas import UpdateTradingConfigRequest
from app.services.trading import get_status, simulate_trade, start_trading, stop_trading, update_config

router = APIRouter(tags=["trading"])


@router.get("/trading/status")
def trading_status_route(user=Depends(require_token)):
    return get_status(user["id"])


@router.post("/trading/start")
def trading_start_route(user=Depends(require_token)):
    return start_trading(user["id"])


@router.post("/trading/stop")
def trading_stop_route(user=Depends(require_token)):
    return stop_trading(user["id"])


@router.post("/trading/config")
def trading_config_route(payload: UpdateTradingConfigRequest, user=Depends(require_token)):
    return update_config(user["id"], payload.model_dump())


@router.post("/trading/simulate")
def trading_simulate_route(user=Depends(require_token)):
    return simulate_trade(user["id"])\n