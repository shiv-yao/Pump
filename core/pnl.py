
class Tracker:
    def __init__(self):
        self.realized = 0
        self.trades = []

    def record(self, pnl):
        self.realized += pnl
        self.trades.append(pnl)
        return pnl
