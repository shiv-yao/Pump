from fastapi import APIRouter, HTTPException
from models import OrderRequest, CancelRequest

from services.registry import get_adapter
from services.risk import risk_check

router = APIRouter()


@router.post("/order")
async def place_order(req: OrderRequest):
    # ===== 風控 =====
    ok = await risk_check(req.asset_id, req.size)
    if not ok:
        raise HTTPException(status_code=400, detail="risk_blocked")

    # ===== routing =====
    adapter = get_adapter(req.venue)

    res = await adapter.place_order(
        asset_id=req.asset_id,
        side=req.side,
        size=req.size,
        price=req.price,
        strategy_id=req.strategy_id
    )

    return res


@router.post("/cancel")
async def cancel(req: CancelRequest):
    adapter = get_adapter(req.venue)
    return await adapter.cancel_order(req.order_id)


@router.get("/balance")
async def balance():
    adapter = get_adapter("polymarket")
    return await adapter.get_balance()


@router.get("/status")
async def status():
    return {"ok": True}
