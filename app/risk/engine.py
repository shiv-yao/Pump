class RiskEngine:
    MAX_DAILY_LOSS = 5

    def validate(self, decision):
        if decision["confidence"] < 0.55:
            return False

        return True