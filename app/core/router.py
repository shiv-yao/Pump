from __future__ import annotations

from app.agents.grok_agent import GrokAgent
from app.agents.claude_agent import ClaudeAgent
from app.agents.gpt_agent import GPTAgent
from app.models.schemas import RunRequest, PipelineResponse
from app.core.state import engine


grok = GrokAgent()
claude = ClaudeAgent()
gpt = GPTAgent()


async def run_pipeline(payload: RunRequest) -> PipelineResponse:
    signals = grok.find_opportunities(payload.watchlist)
    decisions = claude.evaluate(signals, max_buys=payload.max_buys)
    trades = await gpt.execute(decisions)

    for trade in trades:
        engine.trades.append(trade.model_dump())
    engine.log(f"pipeline executed for {len(payload.watchlist)} tokens")

    return PipelineResponse(signals=signals, decisions=decisions, trades=trades)
