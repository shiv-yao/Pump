from fastapi import APIRouter

router = APIRouter()

@router.get("/api/state")
async def state():
    return {
        "mode": "paper",
        "running": True,
        "pnl": 0,
        "positions": 0
    }