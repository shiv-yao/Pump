from fastapi import APIRouter, Depends, HTTPException

from app.core.security import require_token
from app.models.schemas import CheckoutRequest
from app.services.billing import checkout, get_plans

router = APIRouter(tags=["billing"])


@router.get("/plans")
def plans_route():
    return get_plans()


@router.post("/checkout")
def checkout_route(payload: CheckoutRequest, user=Depends(require_token)):
    try:
        return checkout(user["id"], payload.plan)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))\n