class FundBrain:
    async def decide(self, features):
        score = (features["trend_score"] + features["momentum_score"]) / 2
        volatility = features["volatility_score"]

        if score > 0.65 and volatility < 0.8:
            return {"action": "LONG", "confidence": round(score, 4), "size": 0.1}

        if score < 0.35 and volatility < 0.8:
            return {"action": "SHORT", "confidence": round(1 - score, 4), "size": 0.1}

        return {"action": "HOLD", "confidence": round(score, 4), "size": 0.0}
