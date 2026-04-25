import base64
import httpx
from solders.transaction import VersionedTransaction
from solders.keypair import Keypair

JUP_ORDER = "https://api.jup.ag/swap/v2/order"
JUP_EXEC = "https://api.jup.ag/swap/v2/execute"

JITO_URL = "https://mainnet.block-engine.jito.wtf/api/v1/bundles"


async def jito_swap(
    user_pubkey: str,
    input_mint: str,
    output_mint: str,
    amount: int,
    private_key: bytes,
    use_jito=True
):
    async with httpx.AsyncClient(timeout=10) as client:

        # =========================
        # 1. GET ORDER（含交易）
        # =========================
        order = await client.post(JUP_ORDER, json={
            "inputMint": input_mint,
            "outputMint": output_mint,
            "amount": amount,
            "userPublicKey": user_pubkey,
            "slippageBps": 80
        })

        data = order.json()

        if "transaction" not in data:
            return {"error": "no tx", "raw": data}

        tx_b64 = data["transaction"]
        tx = VersionedTransaction.from_bytes(base64.b64decode(tx_b64))

        # =========================
        # 2. SIGN（本地）
        # =========================
        kp = Keypair.from_bytes(private_key)
        sig = kp.sign_message(tx.message.serialize())

        tx.signatures[0] = sig

        signed = base64.b64encode(bytes(tx)).decode()

        # =========================
        # 3. JITO（防 MEV）
        # =========================
        if use_jito:
            bundle = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "sendBundle",
                "params": [[signed]]
            }

            r = await client.post(JITO_URL, json=bundle)

            return {
                "status": "sent_jito",
                "result": r.json()
            }

        # =========================
        # 4. FALLBACK EXECUTE
        # =========================
        res = await client.post(JUP_EXEC, json={
            "signedTransaction": signed,
            "requestId": data.get("requestId")
        })

        return {
            "status": "sent",
            "result": res.json()
        }
