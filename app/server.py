import sys
import os
import asyncio

from fastapi import FastAPI
from fastapi.responses import JSONResponse, HTMLResponse

# =========================
# FIX: 確保 module 不爆
# =========================
sys.path.append(os.getcwd())

# =========================
# IMPORT ENGINE
# =========================
ENGINE_IMPORT_ERROR = None
main_loop = None
engine = None

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
    if ENGINE_IMPORT_ERROR:
        ENGINE_IMPORT_ERROR += f" | state_error={e}"
    else:
        ENGINE_IMPORT_ERROR = f"state_error={e}"
    engine = None

try:
    from app.engine.metrics_runtime import get_metrics
except Exception as e:
    _metrics_import_error = str(e)
    print("❌ METRICS IMPORT ERROR:", _metrics_import_error)

    def get_metrics():
        return {
            "status": "metrics_not_loaded",
            "error": _metrics_import_error,
        }


# =========================
# APP INIT
# =========================
app = FastAPI(
    title="Pump Fusion V74",
    version="74.3",
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


# =========================
# STARTUP
# =========================
@app.on_event("startup")
async def startup():
    print("🚀 SERVER START")

    async def delayed_start():
        global ENGINE_TASK

        await asyncio.sleep(0.5)

        if main_loop is None:
            print("❌ Engine not loaded")
            return

        if engine_task_running():
            print("⚠️ ENGINE TASK ALREADY RUNNING")
            return

        try:
            ENGINE_TASK = asyncio.create_task(
                main_loop(),
                name="pump_engine_main_loop",
            )
            print("🔥 ENGINE TASK STARTED (DELAYED)")
        except Exception as e:
            print("❌ ENGINE START ERROR:", e)
            ENGINE_TASK = None

    asyncio.create_task(delayed_start())


# =========================
# ROOT
# =========================
@app.get("/")
async def root():
    return {
        "status": "running",
        "engine": "alive" if engine_task_running() else "not_started_or_stopped",
        "engine_loaded": main_loop is not None,
        "engine_import_error": ENGINE_IMPORT_ERROR,
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
# METRICS（memory版）
# =========================
@app.get("/metrics")
async def metrics():
    try:
        data = get_metrics()
        return JSONResponse(
            content=data,
            headers={"Cache-Control": "no-store"}
        )
    except Exception as e:
        return JSONResponse(
            content={"error": str(e)},
            status_code=500
        )


# =========================
# LIVE ENGINE SNAPSHOT
# =========================
@app.get("/engine")
async def engine_info():
    return safe_engine_summary()


# =========================
# UI DASHBOARD
# =========================
@app.get("/ui", response_class=HTMLResponse)
async def dashboard():
    return """
<!DOCTYPE html>
<html>
<head>
    <title>Pump Fund PRO</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>

<body style="background:#0b0f1a;color:#fff;font-family:sans-serif;padding:20px">

<h2>🔥 Pump Fund PRO Dashboard</h2>

<!-- ================= SUMMARY ================= -->
<div style="display:flex;gap:30px">
    <div>💰 Capital: <b id="capital">-</b></div>
    <div>📈 Equity: <b id="equity">-</b></div>
    <div>📉 Drawdown: <b id="dd">-</b></div>
    <div>📊 Positions: <b id="pos">-</b></div>
    <div>🔁 Trades: <b id="trades">-</b></div>
</div>

<br>

<!-- ================= CHART ================= -->
<canvas id="chart" height="120"></canvas>

<br>

<!-- ================= STRATEGY ================= -->
<h3>🧠 Strategy Allocation</h3>
<canvas id="strategyChart" height="120"></canvas>

<br>

<!-- ================= POSITIONS ================= -->
<h3>📦 Positions</h3>
<table border="1" cellpadding="6" style="border-collapse:collapse;width:100%">
<thead>
<tr>
    <th>Mint</th>
    <th>Mode</th>
    <th>Entry</th>
    <th>Price</th>
    <th>PnL%</th>
    <th>Value</th>
</tr>
</thead>
<tbody id="positions"></tbody>
</table>

<br>

<!-- ================= TRADES ================= -->
<h3>🧾 Recent Trades</h3>
<pre id="trades_log" style="max-height:200px;overflow:auto;background:#111;padding:10px"></pre>

<br>

<!-- ================= LOG ================= -->
<h3>📡 Logs</h3>
<pre id="logs" style="max-height:200px;overflow:auto;background:#111;padding:10px"></pre>

<script>
let equityChart, stratChart;

function safe(v,d=0){ return (typeof v==="number"&&!isNaN(v))?v:d }

async function load() {
    try {
        const res = await fetch("/metrics?ts=" + Date.now(), {
            cache: "no-store"
        });

        const data = await res.json();

        // 🔥 防爆（超重要）
        if (!data || !data.summary) {
            document.getElementById("stats").innerText =
                JSON.stringify(data, null, 2);
            return;
        }

        const summary = data.summary || {};
        const stats = data.stats || {};
        const equityCurve = Array.isArray(data.equity_curve)
            ? data.equity_curve
            : [];

        document.getElementById("capital").innerText =
            (summary.capital || 0).toFixed(4);

        document.getElementById("equity").innerText =
            (summary.equity || 0).toFixed(4);

        document.getElementById("dd").innerText =
            ((summary.drawdown || 0) * 100).toFixed(2) + "%";

        document.getElementById("pos").innerText =
            summary.positions || 0;

        document.getElementById("stats").innerText =
            JSON.stringify(stats, null, 2);

        const labels = equityCurve.map(x =>
            new Date((x.t || 0) * 1000).toLocaleTimeString()
        );

        const values = equityCurve.map(x => x.equity || 0);

        if (!chart) {
            const ctx = document.getElementById("chart").getContext("2d");
            chart = new Chart(ctx, {
                type: "line",
                data: {
                    labels,
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

    } catch (err) {
        document.getElementById("stats").innerText =
            "UI ERROR: " + err;
    }
}

    // ===== summary =====
    capital.innerText = safe(s.capital).toFixed(4)
    equity.innerText = safe(s.equity).toFixed(4)
    dd.innerText = (safe(s.drawdown)*100).toFixed(2)+"%"
    pos.innerText = safe(s.positions)
    trades.innerText = safe(stats.trades)

    // ===== equity chart =====
    const labels = curve.map(x=>new Date(x.t*1000).toLocaleTimeString())
    const values = curve.map(x=>safe(x.equity))

    if(!equityChart){
        const ctx = document.getElementById("chart").getContext("2d")
        equityChart = new Chart(ctx,{
            type:"line",
            data:{
                labels,
                datasets:[{
                    label:"Equity",
                    data:values,
                    borderColor:"#00ffcc",
                    tension:0.2
                }]
            },
            options:{animation:false}
        })
    }else{
        equityChart.data.labels = labels
        equityChart.data.datasets[0].data = values
        equityChart.update()
    }

    // ===== strategy chart =====
    const strat = data.alpha || {}
    const stratLabels = Object.keys(strat)
    const stratValues = stratLabels.map(k=>safe(strat[k].pnl_sol))

    if(!stratChart){
        const ctx = document.getElementById("strategyChart").getContext("2d")
        stratChart = new Chart(ctx,{
            type:"bar",
            data:{
                labels:stratLabels,
                datasets:[{
                    label:"PnL SOL",
                    data:stratValues
                }]
            }
        })
    }else{
        stratChart.data.labels = stratLabels
        stratChart.data.datasets[0].data = stratValues
        stratChart.update()
    }

    // ===== positions =====
    const rows = data.positions_detail || []
    const tbody = document.getElementById("positions")
    tbody.innerHTML = ""

    rows.forEach(p=>{
        const tr = document.createElement("tr")
        tr.innerHTML = `
        <td>${p.mint?.slice(0,6)}</td>
        <td>${p.mode}</td>
        <td>${safe(p.entry_price).toFixed(6)}</td>
        <td>${safe(p.mark_price).toFixed(6)}</td>
        <td style="color:${p.unrealized_pnl_pct>0?'#0f0':'#f55'}">
            ${(safe(p.unrealized_pnl_pct)*100).toFixed(2)}%
        </td>
        <td>${safe(p.market_value).toFixed(4)}</td>
        `
        tbody.appendChild(tr)
    })

    // ===== trades =====
    trades_log.innerText = JSON.stringify(data.recent_trades||[],null,2)

    // ===== logs =====
    logs.innerText = (data.logs||[]).slice(-50).join("\\n")
}

setInterval(load,2000)
load()

</script>

</body>
</html>
"""


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
