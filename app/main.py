from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from app.api.routes.health import router as health_router
from app.api.routes.state import router as state_router
from app.api.routes.positions import router as positions_router

app = FastAPI(title="KRONOS OMEGA ADVANCED")

app.include_router(health_router)
app.include_router(state_router)
app.include_router(positions_router)


@app.get("/", response_class=HTMLResponse)
async def root():
    return """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>KRONOS OMEGA</title>

  <style>
    body {
      margin: 0;
      background: #070b14;
      color: white;
      font-family: -apple-system, BlinkMacSystemFont, sans-serif;
    }

    .container {
      max-width: 1000px;
      margin: auto;
      padding: 24px;
    }

    h1 {
      font-size: 42px;
      margin-bottom: 10px;
    }

    .subtitle {
      color: #94a3b8;
      margin-bottom: 30px;
    }

    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px;
    }

    .card {
      background: #111827;
      border: 1px solid #1e293b;
      border-radius: 18px;
      padding: 20px;
    }

    .label {
      color: #94a3b8;
      font-size: 14px;
    }

    .value {
      margin-top: 10px;
      font-size: 26px;
      font-weight: bold;
    }

    button {
      width: 100%;
      border: none;
      border-radius: 14px;
      padding: 16px;
      margin-top: 18px;
      font-size: 18px;
      font-weight: bold;
      cursor: pointer;
    }

    .green {
      background: #16a34a;
      color: white;
    }

    .red {
      background: #dc2626;
      color: white;
    }

    pre {
      background: #020617;
      border-radius: 16px;
      padding: 18px;
      overflow: auto;
      max-height: 320px;
      margin-top: 20px;
    }

    a {
      color: #60a5fa;
      text-decoration: none;
    }

    .links {
      margin-top: 25px;
    }
  </style>
</head>

<body>

<div class="container">

  <h1>KRONOS OMEGA</h1>
  <div class="subtitle">
    Advanced AI Trading System
  </div>

  <div class="grid">

    <div class="card">
      <div class="label">System</div>
      <div class="value" id="system_status">Loading...</div>
    </div>

    <div class="card">
      <div class="label">Mode</div>
      <div class="value" id="mode">-</div>
    </div>

    <div class="card">
      <div class="label">Running</div>
      <div class="value" id="running">-</div>
    </div>

    <div class="card">
      <div class="label">Positions</div>
      <div class="value" id="positions">0</div>
    </div>

  </div>

  <button class="green" onclick="refreshSystem()">
    Refresh System
  </button>

  <button class="red" onclick="alert('Kill Switch 尚未接上 API')">
    Kill Switch
  </button>

  <h2>Live State</h2>

  <pre id="state_box">
Loading...
  </pre>

  <div class="links">
    <a href="/docs">Swagger Docs</a>
    |
    <a href="/health">Health</a>
    |
    <a href="/api/state">State</a>
    |
    <a href="/api/positions">Positions</a>
  </div>

</div>

<script>

async function refreshSystem() {

  try {

    const health = await fetch('/health');
    const healthData = await health.json();

    document.getElementById('system_status').innerText =
      healthData.status || 'online';

  } catch (e) {

    document.getElementById('system_status').innerText = 'offline';

  }

  try {

    const state = await fetch('/api/state');
    const stateData = await state.json();

    document.getElementById('state_box').innerText =
      JSON.stringify(stateData, null, 2);

    document.getElementById('mode').innerText =
      stateData.mode || 'UNKNOWN';

    document.getElementById('running').innerText =
      String(stateData.running ?? '-');

  } catch (e) {

    document.getElementById('state_box').innerText =
      'Cannot load /api/state';

  }

  try {

    const positions = await fetch('/api/positions');
    const posData = await positions.json();

    let count = 0;

    if (Array.isArray(posData)) {
      count = posData.length;
    } else if (Array.isArray(posData.positions)) {
      count = posData.positions.length;
    }

    document.getElementById('positions').innerText = count;

  } catch (e) {

    document.getElementById('positions').innerText = '0';

  }

}

refreshSystem();

</script>

</body>
</html>
"""
