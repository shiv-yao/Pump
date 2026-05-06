class StrategyRouter:
    def select(self, regime):
        if regime == "trend_up":
            return "momentum"

        return "mean_reversion"