import json
RUNNING = False
STATE = {"running": False, "trades": 0, "spread": 0.0, "last_trade": None}
async def start_arb_bot() -> str:
    global RUNNING, STATE
    RUNNING = True; STATE["running"] = True
    return "Arbitrage bot started"
async def stop_arb_bot() -> str:
    global RUNNING, STATE
    RUNNING = False; STATE["running"] = False
    return "Arbitrage bot stopped"
async def arb_status() -> str:
    return json.dumps(STATE, ensure_ascii=False, indent=2)
