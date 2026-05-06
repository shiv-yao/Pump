from fastapi import APIRouter

from app.runtime.state import SYSTEM_STATE

router = APIRouter()


@router.get("/api/positions")
async def positions():
    return SYSTEM_STATE.positions
