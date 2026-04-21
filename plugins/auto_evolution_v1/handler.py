import time
from utils.loader import call

STATE = {
    "last_run": 0,
    "cycles": 0,
    "last_result": {}
}


# ========= 評估策略 =========
async def evaluate_strategies():
    stats = await call("strategy_get_stats", {})

    if not isinstance(stats, dict):
        return {}

    decisions = {}

    for sid, s in stats.items():
        pnl = float(s.get("pnl", 0))
        winrate = float(s.get("winrate", 0))
        dd = float(s.get("drawdown", 0))
        trades = int(s.get("trades", 0))

        decision = "keep"

        # ===== kill =====
        if trades > 20 and winrate < 0.35:
            decision = "disable"

        if trades > 20 and dd > abs(pnl) * 0.8:
            decision = "disable"

        # ===== boost =====
        if winrate > 0.6 and pnl > 0:
            decision = "boost"

        decisions[sid] = {
            "decision": decision,
            "pnl": pnl,
            "winrate": winrate,
            "dd": dd
        }

    return decisions


# ========= 執行策略控制 =========
async def apply_strategy_controls(decisions):
    results = {}

    for sid, d in decisions.items():
        action = d["decision"]

        if action == "disable":
            await call("strategy_disable", {"strategy_id": sid})
            results[sid] = "disabled"

        elif action == "boost":
            await call("allocator_boost", {
                "strategy_id": sid,
                "factor": 1.5
            })
            results[sid] = "boosted"

        else:
            results[sid] = "keep"

    return results


# ========= Env 演化 =========
async def evolve_env():
    # 1. replay
    replay = await call("replay_run", {})

    # 2. optimizer
    opt = await call("auto_optimize_env", {})

    # 3. apply
    await call("apply_best_env", {})

    return {
        "replay": replay,
        "optimizer": opt
    }


# ========= 主循環 =========
async def run_evolution_cycle():
    global STATE

    # ===== 1. 策略評估 =====
    decisions = await evaluate_strategies()

    # ===== 2. 套用策略 =====
    controls = await apply_strategy_controls(decisions)

    # ===== 3. Env 演化 =====
    env = await evolve_env()

    STATE["last_run"] = time.time()
    STATE["cycles"] += 1
    STATE["last_result"] = {
        "decisions": decisions,
        "controls": controls,
        "env": env
    }

    return STATE["last_result"]


def evolution_status():
    return STATE
