import os
import sys
from fastapi import FastAPI
from fastapi.responses import JSONResponse, HTMLResponse

sys.path.append(os.getcwd())

app = FastAPI(title="Pump Minimal", version="1.0")

@app.get("/")
async def root():
    return {"ok": True, "msg": "root alive"}

@app.get("/health")
async def health():
    return {"ok": True}

@app.get("/metrics")
async def metrics():
    return JSONResponse({
        "summary": {
            "capital": 5.0,
            "equity": 5.0,
            "drawdown": 0.0,
            "positions": 0,
        },
        "stats": {},
        "equity_curve": [],
    })

@app.get("/ui", response_class=HTMLResponse)
async def ui():
    return "<html><body><h1>UI alive</h1></body></html>"
