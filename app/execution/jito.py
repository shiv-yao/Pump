import base64
import httpx

JITO_URL = "https://mainnet.block-engine.jito.wtf/api/v1/bundles"


async def send_jito_bundle(tx_bytes: bytes, tip_lamports: int = 5000):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "sendBundle",
        "params": [
            {
                "bundle": [base64.b64encode(tx_bytes).decode()],
                "tip": tip_lamports,
            }
        ],
    }

    async with httpx.AsyncClient(timeout=3) as client:
        r = await client.post(JITO_URL, json=payload)
        return r.json()
