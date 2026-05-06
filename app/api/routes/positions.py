from fastapi import APIRouter

router = APIRouter()

@router.get("/api/positions")
async def positions():
    return []