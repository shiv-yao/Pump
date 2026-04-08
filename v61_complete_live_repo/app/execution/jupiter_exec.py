import base64
import httpx
from typing import Optional, Dict, Any

from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solders.message import to_bytes_versioned

from app.config import (
    HTTP_TIMEOUT, JUP_API_KEY, JUP_SWAP_BASE, SOLANA_RPC_HTTP, JITO_BASE_URL,
    JITO_AUTH_UUID, SOLANA_PRIVATE_KEY_B58, USE_JITO, REAL_TRADING,
)

def _keypair() -> Optional[Keypair]:
    if not SOLANA_PRIVATE_KEY_B58:
        return None
    try:
        import base58
        raw = base58.b58decode(SOLANA_PRIVATE_KEY_B58)
        return Keypair.from_bytes(raw)
    except Exception:
        return None

def _auth_headers() -> Dict[str, str]:
    h = {}
    if JUP_API_KEY:
        h["x-api-key"] = JUP_API_KEY
    return h

async def get_order(input_mint: str, output_mint: str, amount: int, taker: Optional[str] = None, slippage_bps: int = 150) -> Dict[str, Any]:
    params = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": str(amount),
        "slippageBps": str(slippage_bps),
    }
    if taker:
        params["taker"] = taker
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        r = await client.get(f"{JUP_SWAP_BASE}/order", params=params, headers=_auth_headers())
        try:
            data = r.json()
        except Exception:
            data = {"error": r.text}
        if r.status_code >= 400:
            data["error"] = data.get("error") or f"HTTP {r.status_code}"
        return data

def sign_order_transaction(tx_b64: str) -> str:
    kp = _keypair()
    if kp is None:
        raise RuntimeError("Missing SOLANA_PRIVATE_KEY_B58 / PRIVATE_KEY_B58")
    raw = base64.b64decode(tx_b64)
    tx = VersionedTransaction.from_bytes(raw)
    sig = kp.sign_message(to_bytes_versioned(tx.message))
    signed = VersionedTransaction.populate(tx.message, [sig])
    return base64.b64encode(bytes(signed)).decode()

async def execute_signed_transaction(signed_tx_b64: str, request_id: str) -> Dict[str, Any]:
    payload = {"signedTransaction": signed_tx_b64, "requestId": request_id}
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        r = await client.post(f"{JUP_SWAP_BASE}/execute", json=payload, headers=_auth_headers())
        try:
            data = r.json()
        except Exception:
            data = {"error": r.text}
        if r.status_code >= 400:
            data["error"] = data.get("error") or f"HTTP {r.status_code}"
        return data

async def rpc_send_transaction(signed_tx_b64: str) -> Dict[str, Any]:
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "sendTransaction",
        "params": [signed_tx_b64, {"encoding": "base64", "skipPreflight": False}],
    }
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        r = await client.post(SOLANA_RPC_HTTP, json=body)
        data = r.json()
        if "error" in data:
            return {"error": data["error"]}
        return {"result": data.get("result")}

async def rpc_get_signature_status(signature: str) -> Dict[str, Any]:
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getSignatureStatuses",
        "params": [[signature], {"searchTransactionHistory": True}],
    }
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        r = await client.post(SOLANA_RPC_HTTP, json=body)
        return r.json()

async def jito_send_transaction(signed_tx_b64: str, bundle_only: bool = False) -> Dict[str, Any]:
    url = f"{JITO_BASE_URL}/api/v1/transactions"
    if bundle_only:
        url += "?bundleOnly=true"
    headers = {"Content-Type": "application/json"}
    if JITO_AUTH_UUID:
        headers["x-jito-auth"] = JITO_AUTH_UUID
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "sendTransaction",
        "params": [signed_tx_b64, {"encoding": "base64"}],
    }
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        r = await client.post(url, json=body, headers=headers)
        try:
            data = r.json()
        except Exception:
            data = {"error": r.text}
        bundle_id = r.headers.get("x-bundle-id")
        if bundle_id:
            data["bundle_id"] = bundle_id
        if r.status_code >= 400:
            data["error"] = data.get("error") or f"HTTP {r.status_code}"
        return data

async def execute_swap(input_mint: str, output_mint: str, amount: int, slippage_bps: int = 150) -> Dict[str, Any]:
    if not REAL_TRADING:
        return {"paper": True, "quote": {"outAmount": "0"}}

    kp = _keypair()
    if kp is None:
        return {"error": "Missing private key"}

    taker = str(kp.pubkey())
    order = await get_order(input_mint, output_mint, amount, taker=taker, slippage_bps=slippage_bps)
    tx_b64 = order.get("transaction")
    request_id = order.get("requestId")
    if not tx_b64:
        return {"error": order.get("error") or "Jupiter /order returned no transaction", "order": order}

    try:
        signed_tx_b64 = sign_order_transaction(tx_b64)
    except Exception as e:
        return {"error": f"sign_failed: {e}", "order": order}

    # Primary: Jupiter managed landing
    if request_id:
        executed = await execute_signed_transaction(signed_tx_b64, request_id)
        if not executed.get("error"):
            executed["quote"] = order
            return executed

    # Secondary: Jito or RPC fallback
    if USE_JITO:
        jito_res = await jito_send_transaction(signed_tx_b64, bundle_only=False)
        if not jito_res.get("error"):
            jito_res["quote"] = order
            return jito_res

    rpc_res = await rpc_send_transaction(signed_tx_b64)
    rpc_res["quote"] = order
    return rpc_res
