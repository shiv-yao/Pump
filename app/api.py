import os
import asyncio
from contextlib import asynccontextmanager
from typing import Dict, Optional

from fastapi import FastAPI
from app.utils.loader import call as _call_tool


# =========================
# ENV
# =========================
def _env_bool(k, d="false"):
    return os.getenv(k, d).lower() == "true"

def _env_int(k, d):
    try:
        return int(os.getenv(k, str(d)))
    except:
        return d

ENABLE_AUTOML = _env_bool("OPTIMIZER_ENABLE", "true")
AUTOML_INTERVAL = _env_int("OPTIMIZER_INTERVAL", 300)

AUTO_START_ENGINE = True
AUTO_START_SNIPER = True
AUTO_START_MEMPOOL = True


# =========================
# TASK REGISTRY
# =========================
TASKS: Dict[str, Optional[asyncio.Task]] = {}


def start_task(name: str, coro):
    if name in TASKS and TASKS[name] and not TASKS[name].done():
        return
    TASKS[name] = asyncio.create_task(coro)


async def stop_all():
    for t in TASKS.values():
        if t:
            t.cancel()


# =========================
# SAFE CALL
# =========================
async def safe_call(name, payload=None):
    try:
        return await _call_tool(name, payload or {})
    except Exception as e:
        return {"error": str(e)}


# =========================
# AutoML
# =========================
async def automl_loop():
    while True:
        try:
            print("🧠 AutoML running...")

            await safe_call("auto_optimize_env", {
                "sample_size": 200,
                "num_candidates": 30
            })

        except Exception as e:
            print("AutoML error:", e)

        await asyncio.sleep(AUTOML_INTERVAL)


# =========================
# Guard（自動修復）
# =========================
async def guard_loop():
    while True:
        try:
            state = await safe_call("get_state", {})

            if not state.get("running"):
                print("🚀 restart engine")
                await safe_call("start_v7_engine", {
                    "markets": ["SOL"],
                    "capital": 100
                })

            if AUTO_START_SNIPER:
                await safe_call("start_sniper", {})

            if AUTO_START_MEMPOOL:
                await safe_call("start_mempool_sniper", {})

        except Exception as e:
            print("Guard error:", e)

        await asyncio.sleep(5)


# =========================
# LIFESPAN
# =========================
@asynccontextmanager
async def lifespan(app: FastAPI):

    print("🔥 API START")

    if ENABLE_AUTOML:
        start_task("automl", automl_loop())

    start_task("guard", guard_loop())

    yield

    print("🛑 shutdown")
    await stop_all()


# =========================
# APP
# =========================
app = FastAPI(
    title="AI Fund PRO MAX FINAL",
    lifespan=lifespan
)


@app.get("/")
async def root():
    return {"status": "ok"}
