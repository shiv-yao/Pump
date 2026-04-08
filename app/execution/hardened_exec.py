import os
import asyncio
import time
import random
from typing import Any, Dict, List, Optional

import httpx

SOLANA_RPC_POOL = [
    x.strip()
    for x in os.getenv(
        "SOLANA_RPC_POOL",
        os.getenv("SOLANA_RPC_HTTP", "https://api.mainnet-beta.solana.com"),
    ).split(",")
    if x.strip()
]

JUP_BASE_API = os.getenv("JUP_BASE_API", "https://quote-api.jup.ag")
JUP_SWAP_API = os.getenv("JUP_SWAP_API", "https://quote-api.jup.ag")
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "8"))
MAX_EXEC_RETRY = int(os.getenv("MAX_EXEC_RETRY", "3"))
PRIORITY_FEE_LAMPORTS = int(os.getenv("PRIORITY_FEE_LAMPORTS", "200000"))
SLIPPAGE_BPS = int(os.getenv("SLIPPAGE_BPS", "150"))


class RpcPool:
    def __init__(self, urls: List[str]):
        self.urls = urls[:]
        self.bad_until = {u: 0.0 for u in self.urls}
        self.idx = 0

    def pick(self) -> str:
        now = time.time()
        alive = [u for u in self.urls if self.bad_until.get(u, 0.0) <= now]
        if not alive:
            alive = self.urls[:]
        self.idx = (self.idx + 1) % max(len(alive), 1)
        return alive[self.idx - 1]

    def mark_bad(self, url: str, sec: float = 15.0):
        self.bad_until[url] = time.time() + sec


RPC_POOL = RpcPool(SOLANA_RPC_POOL)


async def _http_post(url: str, json_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            r = await client.post(url, json=json_data)
            r.raise_for_status()
            return r.json()
    except Exception:
        return None


async def _http_get(url: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            return r.json()
    except Exception:
        return None


async def get_quote_jupiter(input_mint: str, output_mint: str, amount: int) -> Optional[Dict[str, Any]]:
    params = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": str(amount),
        "slippageBps": str(SLIPPAGE_BPS),
        "onlyDirectRoutes": "false",
    }
    return await _http_get(f"{JUP_BASE_API}/v6/quote", params=params)


async def get_swap_tx_jupiter(user_pubkey: str, quote: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    body = {
        "userPublicKey": user_pubkey,
        "quoteResponse": quote,
        "wrapAndUnwrapSol": True,
        "prioritizationFeeLamports": PRIORITY_FEE_LAMPORTS,
    }
    return await _http_post(f"{JUP_SWAP_API}/v6/swap", body)


async def send_raw_transaction(signed_b64: str) -> Optional[str]:
    rpc = RPC_POOL.pick()
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "sendTransaction",
        "params": [
            signed_b64,
            {
                "encoding": "base64",
                "skipPreflight": False,
                "maxRetries": 2,
                "preflightCommitment": "processed",
            },
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            r = await client.post(rpc, json=payload)
            r.raise_for_status()
            data = r.json()
            if "error" in data:
                RPC_POOL.mark_bad(rpc, 10)
                return None
            return data.get("result")
    except Exception:
        RPC_POOL.mark_bad(rpc, 10)
        return None


async def confirm_signature(sig: str, timeout_sec: int = 25) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        rpc = RPC_POOL.pick()
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getSignatureStatuses",
            "params": [[sig], {"searchTransactionHistory": True}],
        }
        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                r = await client.post(rpc, json=payload)
                r.raise_for_status()
                data = r.json()
                value = (((data or {}).get("result") or {}).get("value") or [None])[0]
                if value:
                    status = value.get("confirmationStatus")
                    err = value.get("err")
                    if err is None and status in {"processed", "confirmed", "finalized"}:
                        return True
                    if err is not None:
                        return False
        except Exception:
            RPC_POOL.mark_bad(rpc, 10)
        await asyncio.sleep(1.2)
    return False


async def execute_swap_hardened(
    *,
    input_mint: str,
    output_mint: str,
    amount: int,
    signer_pubkey: str,
    sign_tx_callable,
) -> Dict[str, Any]:
    """
    sign_tx_callable(swap_tx_b64) -> signed_tx_b64
    """
    last_error = None

    for _ in range(MAX_EXEC_RETRY):
        quote = await get_quote_jupiter(input_mint, output_mint, amount)
        if not quote or not quote.get("outAmount"):
            last_error = "quote_failed"
            await asyncio.sleep(0.6)
            continue

        swap = await get_swap_tx_jupiter(signer_pubkey, quote)
        swap_tx = (swap or {}).get("swapTransaction")
        if not swap_tx:
            last_error = "swap_tx_missing"
            await asyncio.sleep(0.6)
            continue

        try:
            signed_b64 = await sign_tx_callable(swap_tx)
        except Exception as e:
            return {"error": f"sign_failed:{e}"}

        sig = await send_raw_transaction(signed_b64)
        if not sig:
            last_error = "send_failed"
            await asyncio.sleep(0.8)
            continue

        ok = await confirm_signature(sig)
        if ok:
            return {
                "ok": True,
                "signature": sig,
                "quote": quote,
                "swap": swap,
                "rpc_pool": SOLANA_RPC_POOL,
            }

        last_error = "confirm_failed"
        await asyncio.sleep(0.8)

    return {"error": last_error or "unknown_exec_error"}
