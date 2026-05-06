class FeatureEngine:
    def compute(self, market_data):
        return {
            "trend_score": 0.72,
            "momentum_score": 0.64,
            "volatility_score": 0.51,
            "liquidity_score": 0.82,
            "regime": "trend_up"
        }