async def risk_check(asset_id, size):
    # 可改成 call("check_risk")
    if size <= 0:
        return False
    if size > 100:
        return False
    return True
