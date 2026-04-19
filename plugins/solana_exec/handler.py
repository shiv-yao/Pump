import os
import httpx

RPC = os.getenv("SOLANA_RPC", "")


async def sol_buy(mint: str, sol: float):
    # 這裡接 Jupiter / 自己 backend
    return {
        "action": "buy",
        "mint": mint,
        "sol": sol,
        "status": "sent"
    }


async def sol_sell(mint: str):
    return {
        "action": "sell",
        "mint": mint,
        "status": "sent"
    }
