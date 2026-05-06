class ReplayEngine:
    def replay(self, ticks: list[dict]):
        return {"status": "completed", "ticks": len(ticks)}
