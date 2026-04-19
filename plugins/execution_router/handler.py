from app.plugin_manager import execute_tool

async def route_order(target: str, side: str, symbol: str, amount: float):

    if target == "polymarket":
        return await execute_tool("pm_buy" if side=="buy" else "pm_sell", {
            "market": symbol,
            "amount": amount
        })

    if target == "solana":
        return await execute_tool("sol_buy" if side=="buy" else "sol_sell", {
            "mint": symbol,
            "sol": amount
        })

    return "Unknown target"
