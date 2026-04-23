from app.state import state

MAX_DD = 0.25

async def check_kill():
    pnl = state.get("pnl", 0)

    if pnl < -MAX_DD:
        state["kill"] = True
        return True

    return False
