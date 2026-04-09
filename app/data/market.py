import httpx
from app.config import HTTP_TIMEOUT, JUP_API_KEY, JUP_SWAP_BASE, SOL_MINT, BIRDEYE_API_KEY

async def get_quote(input_mint: str, output_mint: str, amount: int):
    headers = {"x-api-key": JUP_API_KEY} if JUP_API_KEY else {}
    params = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": str(amount),
        "slippageBps": "150",
    }
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        # Re-using /order for quote + tx assembly keeps behavior aligned with Jupiter Swap V2.
        r = await client.get(f"{JUP_SWAP_BASE}/order", params=params, headers=headers)
        if r.status_code >= 400:
            return None
        return r.json()

def looks_like_solana_mint(value: str) -> bool:
    return isinstance(value, str) and 32 <= len(value) <= 44 and value.isalnum()

async def birdeye_price(address: str):
    if not BIRDEYE_API_KEY:
        return None
    headers = {"X-API-KEY": BIRDEYE_API_KEY}
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        r = await client.get("https://public-api.birdeye.so/defi/price", params={"address": address}, headers=headers)
        if r.status_code >= 400:
            return None
        return r.json()
