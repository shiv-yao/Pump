import asyncio

from app.features.engine import FeatureEngine
from app.ai.fund_brain import FundBrain
from app.risk.engine import RiskEngine
from app.execution.executor import ExecutionEngine
from app.strategies.router import StrategyRouter

async def trading_loop():
    features_engine = FeatureEngine()
    brain = FundBrain()
    risk = RiskEngine()
    execution = ExecutionEngine()
    router = StrategyRouter()

    while True:
        market_data = {"price": 100000}

        features = features_engine.compute(market_data)

        strategy = router.select(features["regime"])

        decision = await brain.decide(features)

        if risk.validate(decision):
            if decision["action"] != "HOLD":
                result = await execution.execute(decision)
                print(strategy, result)

        await asyncio.sleep(10)