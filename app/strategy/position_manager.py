from app.state import state
from app.utils.loader import call

TP = 0.25      # +25%
SL = -0.10     # -10%
TRAIL = 0.15   # trailing stop

async def manage_positions():

    positions = state.get("positions", {})

    for symbol, pos in positions.items():

        entry = pos["entry"]
        size = pos["size"]

        price_data = await call("price", {"symbol": symbol})
        price = float(price_data.get("price", entry))

        pnl = (price - entry) / entry

        # ===== Take Profit =====
        if pnl > TP:
            await call("sell_token", {
                "symbol": symbol,
                "size": size
            })
            continue

        # ===== Stop Loss =====
        if pnl < SL:
            await call("sell_token", {
                "symbol": symbol,
                "size": size
            })
            continue

        # ===== Trailing Stop =====
        peak = pos.get("peak", entry)
        if price > peak:
            pos["peak"] = price
        elif (price - peak) / peak < -TRAIL:
            await call("sell_token", {
                "symbol": symbol,
                "size": size
            })
