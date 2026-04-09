import sys
import os
import asyncio
import traceback

from fastapi import FastAPI
from fastapi.responses import JSONResponse, HTMLResponse

sys.path.append(os.getcwd())

ENGINE_IMPORT_ERROR = None
main_loop = None
engine = None

try:
    from app.engine.main import main_loop
except Exception as e:
    ENGINE_IMPORT_ERROR = f"{type(e).__name__}: {e}"
    print("❌ ENGINE IMPORT ERROR:", ENGINE_IMPORT_ERROR)
    traceback.print_exc()

try:
    from app.state import engine
except Exception as e:
    extra = f"{type(e).__name__}: {e}"
    print("❌ ENGINE STATE IMPORT ERROR:", extra)
    if ENGINE_IMPORT_ERROR:
        ENGINE_IMPORT_ERROR += f" | state_error={extra}"
    else:
        ENGINE_IMPORT_ERROR = f"state_error={extra}"

try:
    from app.engine.metrics_runtime import build_metrics
except Exception as e:
    METRICS_IMPORT_ERROR = f"{type(e).__name__}: {e}"
    print("❌ METRICS IMPORT ERROR:", METRICS_IMPORT_ERROR)

    def build_metrics():
        return {
            "summary": {
                "capital": 0.0,
                "equity": 0.0,
                "drawdown": 0.0,
                "positions": 0,
            },
            "stats": {},
            "equity_curve": [],
            "error": METRICS_IMPORT_ERROR,
        }

app = FastAPI(title="Pump Fusion", version="debug-import")

ENGINE_TASK = None


def engine_task_running() -> bool:
    return ENGINE_TASK is not None and not ENGINE_TASK.done()


@app.on_event("startup")
async def startup():
    global ENGINE_TASK
    print("🚀 SERVER START")

    if main_loop is None:
        print("❌ Engine not loaded")
        print("❌ ENGINE_IMPORT_ERROR =", ENGINE_IMPORT_ERROR)
        return

    try:
        ENGINE_TASK = asyncio.create_task(main_loop(), name="pump_engine_main_loop")
        print("🔥 ENGINE TASK STARTED")
    except Exception as e:
        print("❌ ENGINE START ERROR:", e)
        traceback.print_exc()


@app.get("/")
async def root():
    return {
        "ok": True,
        "engine_loaded": main_loop is not None,
        "engine_import_error": ENGINE_IMPORT_ERROR,
        "engine_task_running": engine_task_running(),
    }


@app.get("/health")
async def health():
    return {"ok": True}


@app.get("/debug")
async def debug():
    task_error = None
    state = "none"
    if ENGINE_TASK is not None:
        if ENGINE_TASK.cancelled():
            state = "cancelled"
        elif ENGINE_TASK.done():
            state = "done"
            try:
                exc = ENGINE_TASK.exception()
                if exc:
                    task_error = str(exc)
            except Exception as e:
                task_error = str(e)
        else:
            state = "running"

    return {
        "engine_loaded": main_loop is not None,
        "engine_import_error": ENGINE_IMPORT_ERROR,
        "engine_task_state": state,
        "engine_task_error": task_error,
    }


@app.get("/metrics")
async def metrics():
    try:
        return JSONResponse(content=build_metrics())
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/ui", response_class=HTMLResponse)
async def ui():
    return "<html><body><h1>Pump UI alive</h1><p>Check /debug</p></body></html>"


@app.on_event("shutdown")
async def shutdown():
    global ENGINE_TASK
    if ENGINE_TASK is not None:
        ENGINE_TASK.cancel()
        try:
            await ENGINE_TASK
        except Exception:
            pass
        ENGINE_TASK = None
