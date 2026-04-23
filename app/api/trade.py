from fastapi import APIRouter
from app.utils.loader import call

router = APIRouter(prefix="/api")

@router.post("/quote")
async def quote(p: dict):
    q = await call("jup_get_quote", {
        "symbol": p["symbol"],
        "amount": p["size"]
    })
    return {"success": True, "data": q}

@router.post("/trade")
async def trade(p: dict):
    return {"success": True, "data": await call("trade_order", p)}

@router.post("/sell")
async def sell(p: dict):
    return {"success": True, "data": await call("sell_token", p)}

@router.post("/sniper/start")
async def start_sniper():
    from app.sniper.sniper_loop import start
    return await start()

@router.post("/sniper/stop")
async def stop_sniper():
    from app.sniper.sniper_loop import stop
    return await stop()
