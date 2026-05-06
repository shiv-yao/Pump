import asyncio

from app.ai.fund_brain import FundBrain
from app.execution.executor import ExecutionEngine
from app.features.engine import FeatureEngine
from app.market.binance_ws import BinanceWS
from app.observers.logger import Observer
from app.portfolio.engine import PortfolioEngine
from app.risk.engine import RiskEngine
from app.runtime.state import SYSTEM_STATE
from app.strategies.router import StrategyRouter


async def trading_loop():
    market = BinanceWS()
    features_engine = FeatureEngine()
    brain = FundBrain()
    risk = RiskEngine()
    execution = ExecutionEngine()
    portfolio = PortfolioEngine()
    router = StrategyRouter()
    observer = Observer()

    SYSTEM_STATE.running = True
    SYSTEM_STATE.add_event("system", {"msg": "trading loop started"})

    while True:
        tick = await market.next_tick()
        features = features_engine.compute(tick)
        strategy = router.select(features["regime"])
        decision = await brain.decide(features)

        SYSTEM_STATE.last_tick = tick
        SYSTEM_STATE.feature_snapshot = features
        SYSTEM_STATE.decision_snapshot = {**decision, "strategy": strategy}

        snapshot = portfolio.summary()
        approved, reason = risk.validate(decision, snapshot)

        if approved and decision["action"] != "HOLD":
            fill = await execution.execute(decision, tick["symbol"], tick["price"])
            portfolio.apply_fill(fill)
            SYSTEM_STATE.add_event("fill", fill)
            observer.log(fill)
        else:
            SYSTEM_STATE.add_event("decision", {"decision": decision, "reason": reason})

        current = portfolio.summary()
        SYSTEM_STATE.positions = current["positions"]
        SYSTEM_STATE.equity = current["equity"]
        SYSTEM_STATE.exposure = current["exposure"]
        SYSTEM_STATE.pnl = round(current["equity"] - 10000.0, 2)

        await asyncio.sleep(2)
