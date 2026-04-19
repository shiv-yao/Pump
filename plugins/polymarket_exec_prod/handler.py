import os
import time
from typing import Dict, Any

# 官方 SDK
from py_clob_client.client import ClobClient
from py_clob_client.types import OrderArgs, OrderType

# ========= 環境 =========
# 必填
# POLY_PRIVATE_KEY: 你的錢包私鑰（0x...）
# POLY_CHAIN_ID: 137 (Polygon) 或依官方
# POLY_API_URL: https://clob.polymarket.com
# 選填
# POLY_SUBACCOUNT: 若你使用子帳戶

API_URL = os.getenv("POLY_API_URL", "https://clob.polymarket.com")
PRIVATE_KEY = os.getenv("POLY_PRIVATE_KEY", "")
CHAIN_ID = int(os.getenv("POLY_CHAIN_ID", "137"))
SUBACCOUNT = os.getenv("POLY_SUBACCOUNT", None)

if not PRIVATE_KEY:
    raise RuntimeError("POLY_PRIVATE_KEY not set")

# ========= Client =========
_client: ClobClient | None = None

def get_client() -> ClobClient:
    global _client
    if _client is None:
        _client = ClobClient(
            host=API_URL,
            key=PRIVATE_KEY,
            chain_id=CHAIN_ID,
            subaccount=SUBACCOUNT
        )
    return _client


# ========= 工具 =========

def _side_to_enum(side: str):
    s = side.lower()
    if s in ("buy", "bid"):
        return "buy"
    if s in ("sell", "ask"):
        return "sell"
    raise ValueError(f"invalid side: {side}")


def pm_limit(asset_id: str, side: str, price: float, size: float, ioc: bool = False) -> Dict[str, Any]:
    """
    限價單（預設 maker），ioc=True 則為 IOC（taker）
    price: 0~1 機率價格（YES token）
    size: 數量（shares）
    """
    client = get_client()
    side = _side_to_enum(side)

    # OrderArgs 依 SDK 定義（名稱可能因版本略有差異）
    order = OrderArgs(
        asset_id=asset_id,
        is_buy=(side == "buy"),
        price=price,
        size=size,
        order_type=OrderType.IOC if ioc else OrderType.GTC
    )

    # 簽名並送出
    resp = client.create_order(order)

    return {
        "ok": True,
        "order_id": resp.get("orderID") or resp.get("id"),
        "raw": resp
    }


def pm_cancel(order_id: str) -> Dict[str, Any]:
    client = get_client()
    resp = client.cancel_order(order_id)
    return {"ok": True, "raw": resp}


def pm_get_order(order_id: str) -> Dict[str, Any]:
    client = get_client()
    resp = client.get_order(order_id)
    return {"ok": True, "order": resp}


def pm_get_fills(limit: int = 50) -> Dict[str, Any]:
    client = get_client()
    resp = client.get_trades(limit=limit)
    return {"ok": True, "fills": resp}


def pm_balance() -> Dict[str, Any]:
    client = get_client()
    resp = client.get_balances()
    return {"ok": True, "balances": resp}
