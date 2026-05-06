class FundBrain:
    async def decide(self, features):
        score = (
            features["trend_score"] +
            features["momentum_score"]
        ) / 2

        if score > 0.7:
            return {
                "action": "LONG",
                "confidence": score
            }

        return {
            "action": "HOLD",
            "confidence": score
        }