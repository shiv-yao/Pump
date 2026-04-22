import os
import base64
import httpx

from solders.keypair import Keypair
from solders.transaction import VersionedTransaction

RPC_URL = os.getenv("SOLANA_RPC", "https://api.mainnet-beta.solana.com")
JUP_ORDER = "https://api.jup.ag/swap/v2/order"
JUP_EXECUTE = "https://api.jup.ag/swap/v2/execute"

PRIVATE_KEY = os.getenv("SOLANA_PRIVATE_KEY")  # base64 或 bytes


def load_keypair():
    if not PRIVATE_KEY:
        raise Exception("Missing SOLANA_PRIVATE_KEY")

    data = base64.b64decode(PRIVATE_KEY)
    return Keypair.from_bytes(data)


async def jupiter_order(input_mint, output_mint, amount):
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.post(JUP_ORDER, json={
            "inputMint": input_mint,
            "outputMint": output_mint,
            "amount": int(amount),
            "slippageBps": 80
        })
        return res.json()


async def jupiter_execute(signed_tx, request_id):
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.post(JUP_EXECUTE, json={
            "signedTransaction": signed_tx,
            "requestId": request_id
        })
        return res.json()


def sign_tx(tx_base64):
    kp = load_keypair()

    tx_bytes = base64.b64decode(tx_base64)
    tx = VersionedTransaction.from_bytes(tx_bytes)

    tx.sign([kp])

    return base64.b64encode(bytes(tx)).decode()


# ===== MAIN =====
async def trade_order(symbol=None, side="buy", size=0.0, **kwargs):
    """
    symbol = token mint or symbol mapping（你之後可接 token resolver）
    """

    try:
        # ===== token mapping（簡化版）
        if symbol == "SOL":
            input_mint = "So11111111111111111111111111111111111111112"
            output_mint = "USDC"
        else:
            input_mint = "USDC"
            output_mint = symbol

        if side == "sell":
            input_mint, output_mint = output_mint, input_mint

        # ===== quote/order =====
        order = await jupiter_order(input_mint, output_mint, size)

        if "transaction" not in order:
            return {"error": "no_transaction", "raw": order}

        tx = order["transaction"]
        request_id = order.get("requestId")

        # ===== sign =====
        signed = sign_tx(tx)

        # ===== execute =====
        result = await jupiter_execute(signed, request_id)

        return {
            "filled": True,
            "tx": result.get("txid"),
            "raw": result
        }

    except Exception as e:
        return {"error": str(e)}
