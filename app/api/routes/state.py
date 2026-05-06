from fastapi import APIRouter

from app.runtime.state import SYSTEM_STATE

router = APIRouter()


@router.get("/api/state")
async def state():
    return {
        "mode": SYSTEM_STATE.mode,
        "running": SYSTEM_STATE.running,
        "pnl": SYSTEM_STATE.pnl,
        "positions": len(SYSTEM_STATE.positions),
        "equity": SYSTEM_STATE.equity,
        "exposure": SYSTEM_STATE.exposure,
        "last_tick": SYSTEM_STATE.last_tick,
        "features": SYSTEM_STATE.feature_snapshot,
        "decision": SYSTEM_STATE.decision_snapshot,
        "recent_events": list(SYSTEM_STATE.events)[:20],
    }
