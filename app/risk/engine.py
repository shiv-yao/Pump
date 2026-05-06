class RiskEngine:
    MIN_CONFIDENCE = 0.55
    MAX_EXPOSURE = 0.8

    def validate(self, decision, portfolio):
        if decision["action"] == "HOLD":
            return True, "hold_allowed"
        if decision["confidence"] < self.MIN_CONFIDENCE:
            return False, "low_confidence"
        if portfolio["exposure"] >= self.MAX_EXPOSURE:
            return False, "max_exposure_reached"
        return True, "approved"
