import sys
import os
import asyncio

from fastapi import FastAPI
from fastapi.responses import JSONResponse, HTMLResponse

sys.path.append(os.getcwd())

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


app = FastAPI(
    title="Pump Fusion V82",
    version="82.0",
)

ENGINE_TASK = None


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


@app.get("/")
async def root():
    return {
        "status": "running",
        "engine": "alive" if engine_task_running() else "not_started_or_stopped",
        "engine_loaded": main_loop is not None,
        "engine_import_error": ENGINE_IMPORT_ERROR,
    }


@app.get("/health")
async def health():
    return {
        "ok": True,
        "engine_loaded": main_loop is not None,
        "engine_task_running": engine_task_running(),
    }


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


@app.get("/metrics")
async def metrics():
    try:
        data = get_metrics()
        return JSONResponse(
            content=data,
            headers={"Cache-Control": "no-store"},
        )
    except Exception as e:
        return JSONResponse(
            content={"error": str(e)},
            status_code=500,
        )


@app.get("/engine")
async def engine_info():
    return safe_engine_summary()


@app.get("/ui", response_class=HTMLResponse)
async def dashboard():
    return """
<!DOCTYPE html>
<html>
<head>
    <title>Pump Fund PRO</title>
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body style="background:#0b0f1a;color:#fff;font-family:sans-serif;padding:20px">

<h2>🔥 Pump Fund PRO Dashboard</h2>

<div style="display:flex;gap:30px;flex-wrap:wrap">
    <div>💰 Capital: <b id="capital">-</b></div>
    <div>📈 Equity: <b id="equity">-</b></div>
    <div>📉 Drawdown: <b id="dd">-</b></div>
    <div>📊 Positions: <b id="pos">-</b></div>
    <div>🔁 Trades: <b id="trades">-</b></div>
</div>

<br>
<canvas id="chart" height="120"></canvas>

<br>
<h3>🧠 Strategy Allocation</h3>
<canvas id="strategyChart" height="120"></canvas>

<br>
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
    <th>AI</th>
</tr>
</thead>
<tbody id="positions"></tbody>
</table>

<br>
<h3>🧾 Recent Trades</h3>
<pre id="trades_log" style="max-height:220px;overflow:auto;background:#111;padding:10px"></pre>

<br>
<h3>📡 Logs</h3>
<pre id="logs" style="max-height:220px;overflow:auto;background:#111;padding:10px"></pre>

<script>
let equityChart = null;
let stratChart = null;

function safe(v, d = 0) {
    return (typeof v === "number" && !isNaN(v)) ? v : d;
}

async function load() {
    try {
        const res = await fetch("/metrics?ts=" + Date.now(), { cache: "no-store" });
        const data = await res.json();

        if (!data || !data.summary) {
            document.getElementById("logs").innerText = JSON.stringify(data, null, 2);
            return;
        }

        const s = data.summary || {};
        const stats = data.trading || data.stats || {};
        const curve = Array.isArray(data.equity_curve) ? data.equity_curve : [];
        const rows = Array.isArray(data.positions_detail) ? data.positions_detail : [];
        const recentTrades = Array.isArray(data.recent_trades) ? data.recent_trades : [];
        const logRows = Array.isArray(data.logs) ? data.logs : [];
        const alpha = data.alpha || {};

        document.getElementById("capital").innerText = safe(s.capital).toFixed(4);
        document.getElementById("equity").innerText = safe(s.equity).toFixed(4);
        document.getElementById("dd").innerText = (safe(s.drawdown) * 100).toFixed(2) + "%";
        document.getElementById("pos").innerText = safe(s.positions, rows.length);
        document.getElementById("trades").innerText = safe(stats.trades, recentTrades.length);

        const labels = curve.map(x => new Date((x.t || 0) * 1000).toLocaleTimeString());
        const values = curve.map(x => safe(x.equity));

        if (!equityChart) {
            const ctx = document.getElementById("chart").getContext("2d");
            equityChart = new Chart(ctx, {
                type: "line",
                data: {
                    labels,
                    datasets: [{
                        label: "Equity",
                        data: values,
                        borderColor: "#00ffcc",
                        fill: false,
                        tension: 0.2
                    }]
                },
                options: { animation: false, responsive: true }
            });
        } else {
            equityChart.data.labels = labels;
            equityChart.data.datasets[0].data = values;
            equityChart.update();
        }

        const stratLabels = Object.keys(alpha);
        const stratValues = stratLabels.map(k => safe((alpha[k] || {}).pnl_sol));

        if (!stratChart) {
            const ctx2 = document.getElementById("strategyChart").getContext("2d");
            stratChart = new Chart(ctx2, {
                type: "bar",
                data: {
                    labels: stratLabels,
                    datasets: [{
                        label: "PnL SOL",
                        data: stratValues
                    }]
                },
                options: { animation: false, responsive: true }
            });
        } else {
            stratChart.data.labels = stratLabels;
            stratChart.data.datasets[0].data = stratValues;
            stratChart.update();
        }

        const tbody = document.getElementById("positions");
        tbody.innerHTML = "";

        rows.forEach(p => {
            const tr = document.createElement("tr");
            const pnlPct = safe(p.unrealized_pnl_pct);
            const aiProb = safe(p.ai_win_prob);
            tr.innerHTML = `
                <td>${(p.mint || "").slice(0, 6)}</td>
                <td>${p.mode || ""}</td>
                <td>${safe(p.entry_price).toFixed(6)}</td>
                <td>${safe(p.mark_price).toFixed(6)}</td>
                <td style="color:${pnlPct > 0 ? '#0f0' : '#f55'}">
                    ${(pnlPct * 100).toFixed(2)}%
                </td>
                <td>${safe(p.market_value).toFixed(4)}</td>
                <td>${(aiProb * 100).toFixed(1)}%</td>
            `;
            tbody.appendChild(tr);
        });

        document.getElementById("trades_log").innerText = JSON.stringify(recentTrades, null, 2);
        document.getElementById("logs").innerText = logRows.slice(-50).join("\\n");

    } catch (err) {
        document.getElementById("logs").innerText = "UI ERROR: " + err;
    }
}

setInterval(load, 2000);
load();
</script>

</body>
</html>
"""


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
