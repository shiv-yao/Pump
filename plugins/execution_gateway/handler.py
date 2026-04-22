import os
import base64
import httpx

from solders.keypair import Keypair
from solders.transaction import VersionedTransaction

RPC_URL = os.getenv("SOLANA_RPC", "https://api.mainnet-beta.solana.com")
JUP_ORDER = "https://api.jup.ag/swap/v2/order"
JUP_EXECUTE = "https://api.jup.ag/swap/v2/execute"

# Jito
USE_JITO = os.getenv("USE_JITO", "false").lower() == "true"
JITO_BUNDLE_URL = os.getenv(
    "JITO_BUNDLE_URL",
    "https://mainnet.block-engine.jito.wtf/api/v1/bundles"
)
JITO_TX_URL = os.getenv(
    "JITO_TX_URL",
    "https://mainnet.block-engine.jito.wtf/api/v1/transactions"
)
JITO_TIP_LAMPORTS = int(os.getenv("JITO_TIP_LAMPORTS", "2000"))

PRIVATE_KEY = os.getenv("SOLANA_PRIVATE_KEY", "").strip()


def load_keypair():
    if not PRIVATE_KEY:
        raise Exception("Missing SOLANA_PRIVATE_KEY")

    data = base64.b64decode(PRIVATE_KEY)
    return Keypair.from_bytes(data)


async def jupiter_order(input_mint, output_mint, amount):
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.post(
            JUP_ORDER,
            json={
                "inputMint": input_mint,
                "outputMint": output_mint,
                "amount": int(amount),
                "slippageBps": 80
            }
        )
        return res.json()


async def jupiter_execute(signed_tx, request_id):
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.post(
            JUP_EXECUTE,
            json={
                "signedTransaction": signed_tx,
                "requestId": request_id
            }
        )
        return res.json()


def sign_tx(tx_base64: str) -> str:
    kp = load_keypair()

    tx_bytes = base64.b64decode(tx_base64)
    tx = VersionedTransaction.from_bytes(tx_bytes)
    tx.sign([kp])

    return base64.b64encode(bytes(tx)).decode()


async def send_jito_bundle(signed_tx_base64: str):
    """
    Jito bundle: JSON-RPC 2.0, params[0] = [base64_signed_tx, ...]
    注意：真正穩定上鏈通常需要交易內含 tip 指令。
    """
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "sendBundle",
        "params": [[signed_tx_base64]]
    }

    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.post(
            JITO_BUNDLE_URL,
            headers={"Content-Type": "application/json"},
            json=payload
        )
        data = res.json()

    if "error" in data:
        return {"error": f"jito_bundle_error: {data['error']}"}

    return {
        "ok": True,
        "bundle_id": data.get("result"),
        "raw": data
    }


async def send_jito_transaction(signed_tx_base64: str):
    """
    單筆交易走 Jito transaction endpoint。
    比 bundle 簡單，但 bundle 的原子性更好。
    """
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "sendTransaction",
        "params": [signed_tx_base64, {"encoding": "base64"}]
    }

    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.post(
            JITO_TX_URL,
            headers={"Content-Type": "application/json"},
            json=payload
        )
        data = res.json()

    if "error" in data:
        return {"error": f"jito_tx_error: {data['error']}"}

    return {
        "ok": True,
        "signature": data.get("result"),
        "raw": data
    }


async def trade_order(symbol=None, side="buy", size=0.0, **kwargs):
    """
    symbol 這裡先沿用你現有簡化 mapping。
    真實版建議再接 token resolver。
    """
    try:
        if symbol == "SOL":
            input_mint = "So11111111111111111111111111111111111111112"
            output_mint = "USDC"
        else:
            input_mint = "USDC"
            output_mint = symbol

        if side == "sell":
            input_mint, output_mint = output_mint, input_mint

        order = await jupiter_order(input_mint, output_mint, size)

        tx_base64 = order.get("transaction")
        request_id = order.get("requestId")

        if not tx_base64:
            return {"error": "no_transaction", "raw": order}

        signed_tx = sign_tx(tx_base64)

        # ===== Jito path =====
        if USE_JITO:
            # 你可以二選一：
            # 1) bundle
            jito_res = await send_jito_bundle(signed_tx)

            if "error" not in jito_res:
                return {
                    "filled": True,
                    "via": "jito_bundle",
                    "bundle_id": jito_res.get("bundle_id"),
                    "raw": jito_res
                }

            # 2) bundle 失敗 fallback 到 Jito 單筆
            jito_tx_res = await send_jito_transaction(signed_tx)
            if "error" not in jito_tx_res:
                return {
                    "filled": True,
                    "via": "jito_tx",
                    "tx": jito_tx_res.get("signature"),
                    "raw": jito_tx_res
                }

            # 3) 再 fallback Jupiter execute
            execute_res = await jupiter_execute(signed_tx, request_id)
            return {
                "filled": True,
                "via": "jup_execute_fallback",
                "tx": execute_res.get("txid"),
                "raw": execute_res
            }

        # ===== default Jupiter path =====
        execute_res = await jupiter_execute(signed_tx, request_id)
        return {
            "filled": True,
            "via": "jupiter",
            "tx": execute_res.get("txid"),
            "raw": execute_res
        }

    except Exception as e:
        return {"error": str(e)}
