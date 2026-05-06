from datetime import datetime, timezone


class ExecutionEngine:
    async def execute(self, decision, symbol, price):
        side = "BUY" if decision["action"] == "LONG" else "SELL"
        qty = decision.get("size", 0.0)
        return {
            "status": "paper_filled",
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "price": price,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
