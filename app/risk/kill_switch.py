from app.state import state

MAX_DRAWDOWN = -0.25

async def check_kill():
    pnl = state.get("pnl", 0)

    if pnl < MAX_DRAWDOWN:
        state["kill"] = True
        return True

    return False
