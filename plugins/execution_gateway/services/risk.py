# services/risk.py

from utils.loader import call


async def risk_check(asset_id, size):
    """
    優先使用 risk_engine plugin
    fallback 用本地規則
    """

    try:
        res = await call("check_risk", {
            "asset_id": asset_id,
            "size": size
        })

        if isinstance(res, dict):
            # plugin 標準格式
            if res.get("allowed") is False:
                return False

            if res.get("ok") is False:
                return False

            return True

    except Exception:
        pass

    # ===== fallback（保底）=====
    if size <= 0:
        return False

    if size > 100:
        return False

    return True
