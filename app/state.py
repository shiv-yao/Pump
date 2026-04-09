from types import SimpleNamespace

engine = SimpleNamespace(
    running=True,
    positions=[],
    trade_history=[],
    logs=[],
    capital=5.0,
    start_capital=5.0,
    peak_capital=5.0,
    no_trade_cycles=0,
    last_signal="",
    last_trade="",
    stats={},
)
