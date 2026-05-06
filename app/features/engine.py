class FeatureEngine:
    def compute(self, market_data):
        price = float(market_data["price"])
        move = float(market_data["change_pct"])

        momentum = max(0.0, min(1.0, 0.5 + move / 2))
        trend = max(0.0, min(1.0, 0.5 + move / 3))
        volatility = min(1.0, abs(move) / 1.8)
        liquidity = 0.8

        regime = "trend_up" if move > 0 else "mean_revert"
        if abs(move) < 0.05:
            regime = "range"

        return {
            "price": price,
            "trend_score": round(trend, 4),
            "momentum_score": round(momentum, 4),
            "volatility_score": round(volatility, 4),
            "liquidity_score": liquidity,
            "regime": regime,
        }
