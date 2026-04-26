state = {
    "running": False,
    "mode": "PAPER",
    "pnl": 0.0,
    "unrealized_pnl": 0.0,
    "winrate": 0.0,
    "drawdown": 0.0,
    "total_exposure": 0.0,
    "positions": [],
    "trade_history": [],
    "logs": [],
    "kill": False,
}

from collections import deque

class EngineState:
    def __init__(self):
        self.running = False
        self.mode = "PAPER"
        self.pnl = 0.0
        self.unrealized_pnl = 0.0
        self.positions = []
        self.trade_history = []
        self.logs = deque(maxlen=300)
        self.winrate = 0.0
        self.drawdown = 0.0
        self.total_exposure = 0.0
        self.killswitch = False

engine = EngineState()
