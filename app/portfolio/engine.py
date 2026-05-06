class PortfolioEngine:
    def __init__(self):
        self._equity = 10000.0
        self._exposure = 0.0
        self._positions = []

    def summary(self):
        return {
            "equity": round(self._equity, 2),
            "exposure": round(self._exposure, 4),
            "positions": self._positions,
        }

    def apply_fill(self, fill):
        side = fill["side"]
        qty = float(fill["qty"])
        price = float(fill["price"])
        notional = qty * price

        if side == "BUY":
            self._exposure = min(1.0, self._exposure + qty)
            self._positions.append({"symbol": fill["symbol"], "side": "LONG", "qty": qty, "entry": price})
            self._equity -= notional * 0.001
        else:
            self._exposure = max(0.0, self._exposure - qty)
            self._positions.append({"symbol": fill["symbol"], "side": "SHORT", "qty": qty, "entry": price})
            self._equity -= notional * 0.001
