from app.utils.loader import call

async def trade_order(p):
    symbol=p["symbol"]
    size=p["size"]

    # 1 quote/order
    order=await call("jup_create_order",{"symbol":symbol,"amount":size})
    if "tx" not in order:
        return {"error":"no_tx"}

    # 2 sign
    signed=await call("sign_tx",{"tx":order["tx"]})

    # 3 jito
    jito=await call("jito_send_bundle",{"tx":signed})
    if "error" not in jito:
        return {"status":"jito","tx":jito}

    # fallback
    return await call("send_tx",{"tx":signed})
