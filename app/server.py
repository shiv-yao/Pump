import sys
import os
import asyncio
import json
from pathlib import Path
from fastapi.responses import HTMLResponse
from fastapi import FastAPI
from fastapi.responses import JSONResponse

# =========================
# 🔥 FIX: 確保 module 不爆
# =========================
sys.path.append(os.getcwd())

# =========================
# IMPORT ENGINE
# =========================
ENGINE_IMPORT_ERROR = None

try:
    from app.engine.main import main_loop
except Exception as e:
    print("❌ ENGINE IMPORT ERROR:", e)
    ENGINE_IMPORT_ERROR = str(e)
    main_loop = None

try:
    from app.state import engine
except Exception as e:
    print("❌ ENGINE STATE IMPORT ERROR:", e)
    engine = None

# =========================
# APP INIT
# =========================
app = FastAPI(
    title="Pump Fusion V74",
    version="74.1",
)

ENGINE_TASK = None


# =========================
# HELPERS
# =========================
def engine_task_running() -> bool:
    global ENGINE_TASK
    return ENGINE_TASK is not None and not ENGINE_TASK.done()


def safe_engine_summary():
    if engine is None:
        return {
            "loaded": False,
            "reason": "engine_state_import_failed",
        }

    try:
        return {
            "loaded": True,
            "running": bool(getattr(engine, "running", False)),
            "capital": float(getattr(engine, "capital", 0.0)),
            "positions": len(getattr(engine, "positions", []) or []),
            "last_signal": getattr(engine, "last_signal", ""),
            "last_trade": getattr(engine, "last_trade", ""),
            "no_trade_cycles": int(getattr(engine, "no_trade_cycles", 0)),
            "stats": getattr(engine, "stats", {}),
        }
    except Exception as e:
        return {
            "loaded": False,
            "reason": f"engine_summary_error: {e}",
        }


def safe_read_metrics():
    path = Path("metrics.json")
    if not path.exists():
        return {"error": "metrics_not_found"}

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"error": f"metrics_read_error: {e}"}


# =========================
# STARTUP
# =========================
@app.on_event("startup")
async def startup():
    global ENGINE_TASK

    print("🚀 SERVER START")

    if main_loop is None:
        print("❌ Engine not loaded")
        return

    if engine_task_running():
        print("⚠️ ENGINE TASK ALREADY RUNNING")
        return

    try:
        ENGINE_TASK = asyncio.create_task(main_loop(), name="pump_engine_main_loop")
        print("🔥 ENGINE TASK STARTED")
    except Exception as e:
        print("❌ ENGINE START ERROR:", e)
        ENGINE_TASK = None


# =========================
# ROOT
# =========================
@app.get("/")
async def root():
    return {
        "status": "running",
        "engine": "alive" if engine_task_running() else "not_started_or_stopped",
        "engine_loaded": main_loop is not None,
    }


# =========================
# HEALTH CHECK（Railway會用）
# =========================
@app.get("/health")
async def health():
    return {
        "ok": True,
        "engine_loaded": main_loop is not None,
        "engine_task_running": engine_task_running(),
    }


# =========================
# DEBUG（看 engine 有沒有跑）
# =========================
@app.get("/debug")
async def debug():
    task_state = None
    task_error = None

    if ENGINE_TASK is None:
        task_state = "none"
    elif ENGINE_TASK.cancelled():
        task_state = "cancelled"
    elif ENGINE_TASK.done():
        task_state = "done"
        try:
            exc = ENGINE_TASK.exception()
            if exc:
                task_error = str(exc)
        except Exception as e:
            task_error = f"exception_read_error: {e}"
    else:
        task_state = "running"

    return {
        "engine_loaded": main_loop is not None,
        "engine_import_error": ENGINE_IMPORT_ERROR,
        "engine_task_state": task_state,
        "engine_task_error": task_error,
        "engine_summary": safe_engine_summary(),
    }


# =========================
# METRICS
# =========================
@app.get("/metrics")
async def metrics():
    data = safe_read_metrics()
    return JSONResponse(content=data)


# =========================
# LIVE ENGINE SNAPSHOT
# =========================
@app.get("/engine")
async def engine_info():
    return safe_engine_summary()


# =========================
# SAFE SHUTDOWN（避免殭屍）
# =========================
@app.on_event("shutdown")
async def shutdown():
    global ENGINE_TASK

    print("🛑 SERVER SHUTDOWN")

    if ENGINE_TASK is not None:
        ENGINE_TASK.cancel()
        try:
            await ENGINE_TASK
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print("⚠️ ENGINE TASK SHUTDOWN ERROR:", e)

        ENGINE_TASK = None
        print("🧹 ENGINE TASK CLEANED")

@app.get("/ui", response_class=HTMLResponse)
async def dashboard():
    return """
<!DOCTYPE html>
<html>
<head>
    <title>Pump Fund Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>

<body style="background:#0b0f1a;color:#fff;font-family:sans-serif;padding:20px">

<h2>🔥 Pump Fund Dashboard</h2>

<div>
    <b>Capital:</b> <span id="capital"></span><br>
    <b>Equity:</b> <span id="equity"></span><br>
    <b>Drawdown:</b> <span id="dd"></span><br>
    <b>Positions:</b> <span id="pos"></span>
</div>

<br>

<canvas id="chart" width="800" height="300"></canvas>

<br>

<h3>📊 Stats</h3>
<pre id="stats"></pre>

<script>
let chart;

async function load() {
    const res = await fetch("/metrics");
    const data = await res.json();

    if (!data.summary) return;

    document.getElementById("capital").innerText = data.summary.capital.toFixed(4);
    document.getElementById("equity").innerText = data.summary.equity.toFixed(4);
    document.getElementById("dd").innerText = (data.summary.drawdown * 100).toFixed(2) + "%";
    document.getElementById("pos").innerText = data.summary.positions;

    document.getElementById("stats").innerText = JSON.stringify(data.stats, null, 2);

    const labels = data.equity_curve.map(x => new Date(x.t * 1000).toLocaleTimeString());
    const values = data.equity_curve.map(x => x.equity);

    if (!chart) {
        const ctx = document.getElementById("chart").getContext("2d");
        chart = new Chart(ctx, {
            type: "line",
            data: {
                labels: labels,
                datasets: [{
                    label: "Equity",
                    data: values,
                    borderColor: "#00ffcc",
                    fill: false
                }]
            }
        });
    } else {
        chart.data.labels = labels;
        chart.data.datasets[0].data = values;
        chart.update();
    }
}

setInterval(load, 2000);
load();
</script>

</body>
</html>
"""
