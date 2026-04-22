async def rug_check(symbol=None, asset_id=None, **kwargs):
    target = symbol or asset_id or "unknown"
    return {
        "allowed": True,
        "score": 0.08,
        "reason": "ok",
        "target": target
    }
