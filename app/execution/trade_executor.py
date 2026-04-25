from app.utils.loader import call

async def execute_trade(decision: dict, symbol: str):
    if decision["action"] != "buy":
        return {"status": "skip"}

    size = decision["size"]

    # ===== 1. Jupiter order =====
    order = await call("jup_create_order", {
        "symbol": symbol,
        "amount": size
    })

    if not order or "tx" not in order:
        return {"error": "no_tx"}

    # ===== 2. sign =====
    signed = await call("sign_tx", {"tx": order["tx"]})

    # ===== 3. Jito =====
    jito = await call("jito_send_bundle", {"tx": signed})

    if isinstance(jito, dict) and "error" not in jito:
        return {
            "status": "jito_sent",
            "tx": jito
        }

    # ===== fallback =====
    rpc = await call("send_tx", {"tx": signed})

    return {
        "status": "rpc_sent",
        "tx": rpc
    }
