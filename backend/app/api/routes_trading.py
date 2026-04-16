from fastapi import APIRouter, Depends, HTTPException

from app.core.security import require_token
from app.models.schemas import LiveConfirmRequest, UnlockRequest, UpdateTradingConfigRequest
from app.services.trading import (
    get_status,
    manual_confirm_trade,
    simulate_trade,
    start_trading,
    stop_trading,
    unlock_integration,
    update_config,
)

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


@router.post("/trading/unlock")
def trading_unlock_route(payload: UnlockRequest, user=Depends(require_token)):
    try:
        return unlock_integration(user["id"], payload.confirm_text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/trading/simulate")
def trading_simulate_route(user=Depends(require_token)):
    return simulate_trade(user["id"])


@router.post("/trading/manual-confirm")
def trading_manual_confirm_route(payload: LiveConfirmRequest, user=Depends(require_token)):
    try:
        return manual_confirm_trade(user["id"], payload.symbol, payload.size_usd, payload.confirm_text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
