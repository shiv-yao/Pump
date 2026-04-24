import os
import asyncio
from contextlib import asynccontextmanager
from typing import Dict, Optional

from fastapi import FastAPI

from app.utils.loader import call as _call_tool


# =========================
# ENV CONFIG
# =========================

def _env_bool(k: str, default: str = "false") -> bool:
    return os.getenv(k, default).lower() == "true"


def _env_int(k: str, default: int) -> int:
    try:
        return int(os.getenv(k, str(default)))
    except Exception:
        return default


def _env_float(k: str, default: float) -> float:
    try:
        return float(os.getenv(k, str(default)))
    except Exception:
        return default


ENABLE_AUTOML = _env_bool("OPTIMIZER_ENABLE", "true")
AUTOML_INTERVAL = _env_int("OPTIMIZER_INTERVAL", 300)
AUTOML_AUTO_APPLY = _env_bool("OPTIMIZER_AUTO_APPLY", "false")

AUTO_START_ENGINE = _env_bool("AUTO_START_ENGINE", "false")
AUTO_START_SNIPER = _env_bool("AUTO_START_SNIPER", "false")
AUTO_START_MEMPOOL = _env_bool("AUTO_START_MEMPOOL", "false")

DEFAULT_CAPITAL = _env_float("DEFAULT_CAPITAL", 100.0)


# =========================
# GLOBAL TASK REGISTRY
# =========================

TASKS: Dict[str, Optional[asyncio.Task]] = {
    "automl": None,
    "guard": None,
}


# =========================
# SAFE TOOL CALL
# =========================

async def safe_call(name: str, payload=None):
    try:
        return await _call_tool(name, payload or {})
    except Exception as e:
        return {"error": f"{name} crashed: {str(e)}"}


# =========================
# AUTOML LOOP
# =========================

async def automl_loop():
    """
    AutoML:
    - replay optimize
    - auto env tuning
    - optional auto apply
    """

    while True:
        try:
            print("🧠 [AutoML] cycle start")

            result = await safe_call("auto_optimize_env", {
                "sample_size": 200,
                "num_candidates": 30
            })

            if isinstance(result, dict) and not result.get("error"):
                print("🧠 [AutoML] success")

                if AUTOML_AUTO_APPLY:
                    print("⚙️ [AutoML] applying best env...")
                    await safe_call("apply_best_env", {})
            else:
                print("⚠️ [AutoML] failed:", result)

        except asyncio.CancelledError:
            print("⏹ [AutoML] stopped")
            break

        except Exception as e:
            print("❌ [AutoML] error:", str(e))

        await asyncio.sleep(AUTOML_INTERVAL)


# =========================
# ENGINE GUARD LOOP
# =========================

async def guard_loop():
    """
    Keeps system alive:
    - engine
    - sniper
    - mempool
    """

    while True:
        try:
            state = await safe_call("get_state", {})

            running = False
            if isinstance(state, dict):
                running = state.get("running", False)

            # ===== ENGINE =====
            if AUTO_START_ENGINE and not running:
                print("🚀 [Guard] restarting engine...")
                await safe_call("start_v7_engine", {
                    "markets": ["SOL", "MEME"],
                    "capital": DEFAULT_CAPITAL
                })

            # ===== SNIPER =====
            if AUTO_START_SNIPER:
                await safe_call("start_sniper", {})

            # ===== MEMPOOL =====
            if AUTO_START_MEMPOOL:
                await safe_call("start_mempool_sniper", {})

        except asyncio.CancelledError:
            print("⏹ [Guard] stopped")
            break

        except Exception as e:
            print("❌ [Guard] error:", str(e))

        await asyncio.sleep(5)


# =========================
# TASK START/STOP HELPERS
# =========================

def start_task(name: str, coro):
    if TASKS.get(name) and not TASKS[name].done():
        return
    TASKS[name] = asyncio.create_task(coro)


async def stop_all_tasks():
    for name, task in TASKS.items():
        if task and not task.done():
            print(f"⏹ stopping {name}...")
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


# =========================
# LIFESPAN
# =========================

@asynccontextmanager
async def lifespan(app: FastAPI):

    print("🔥 API starting...")

    # === AutoML ===
    if ENABLE_AUTOML:
        print("🧠 AutoML ENABLED")
        start_task("automl", automl_loop())

    # === Guard ===
    print("🛡 Guard loop ENABLED")
    start_task("guard", guard_loop())

    yield

    print("🛑 API shutting down...")
    await stop_all_tasks()


# =========================
# FASTAPI APP
# =========================

app = FastAPI(
    title="AI Fund PRO MAX",
    version="final",
    lifespan=lifespan,
)


# =========================
# ROUTERS
# =========================

from app.api.dashboard_v4 import router as dashboard_router

app.include_router(dashboard_router)


# =========================
# HEALTH CHECK
# =========================

@app.get("/")
async def root():
    return {
        "status": "ok",
        "system": "AI Fund PRO MAX",
        "automl_enabled": ENABLE_AUTOML,
        "automl_interval": AUTOML_INTERVAL,
        "auto_apply": AUTOML_AUTO_APPLY,
    }
