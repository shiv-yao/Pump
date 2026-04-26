import asyncio
from app.utils.loader import call

TP_RATIO = 0.25      # +25% 止盈
SL_RATIO = -0.10     # -10% 止損
TRAILING = 0.15      # 回撤 15% 出場

CHECK_INTERVAL = 2


def pnl_pct(entry, mark):
    if entry == 0:
        return 0
    return (mark - entry) / entry


async def manage_positions_loop():
    while True:
        try:
            state = await call("get_state", {})
            positions = state.get("positions", {})

            for symbol, pos in positions.items():
                size = pos.get("size", 0)
                avg = pos.get("avg", 0)
                mark = pos.get("mark", avg)

                p = pnl_pct(avg, mark)

                # === STOP LOSS ===
                if p <= SL_RATIO:
                    print(f"🛑 SL triggered {symbol}")
                    await call("trade_order", {
                        "symbol": symbol,
                        "side": "sell",
                        "size": size,
                    })

                # === TAKE PROFIT ===
                elif p >= TP_RATIO:
                    print(f"💰 TP triggered {symbol}")
                    await call("trade_order", {
                        "symbol": symbol,
                        "side": "sell",
                        "size": size * 0.7,
                    })

                # === TRAILING STOP ===
                peak = pos.get("peak", mark)
                if mark > peak:
                    pos["peak"] = mark

                drop = (mark - pos["peak"]) / pos["peak"] if pos["peak"] else 0
                if drop <= -TRAILING:
                    print(f"📉 Trailing stop {symbol}")
                    await call("trade_order", {
                        "symbol": symbol,
                        "side": "sell",
                        "size": size,
                    })

        except Exception as e:
            print("position_manager error:", e)

        await asyncio.sleep(CHECK_INTERVAL)
