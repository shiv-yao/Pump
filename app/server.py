# app/server.py

import sys
import os
import asyncio
from fastapi import FastAPI
from fastapi.responses import JSONResponse

# =========================
# 🔥 FIX: 確保 module 不爆
# =========================
sys.path.append(os.getcwd())

# =========================
# IMPORT ENGINE
# =========================
try:
    from app.engine.main import main_loop
except Exception as e:
    print("❌ ENGINE IMPORT ERROR:", e)
    main_loop = None

# =========================
# APP INIT
# =========================
app = FastAPI(
    title="Pump Fusion V74",
    version="74.0",
)

ENGINE_TASK = None


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

    try:
        ENGINE_TASK = asyncio.create_task(main_loop())
        print("🔥 ENGINE TASK STARTED")
    except Exception as e:
        print("❌ ENGINE START ERROR:", e)


# =========================
# ROOT
# =========================
@app.get("/")
async def root():
    return {
        "status": "running",
        "engine": "alive" if ENGINE_TASK else "not_started"
    }


# =========================
# HEALTH CHECK（Railway會用）
# =========================
@app.get("/health")
async def health():
    return {"ok": True}


# =========================
# DEBUG（看 engine 有沒有跑）
# =========================
@app.get("/debug")
async def debug():
    return {
        "engine_loaded": main_loop is not None,
        "engine_task": str(ENGINE_TASK),
    }


# =========================
# SAFE SHUTDOWN（避免殭屍）
# =========================
@app.on_event("shutdown")
async def shutdown():
    global ENGINE_TASK

    print("🛑 SERVER SHUTDOWN")

    if ENGINE_TASK:
        ENGINE_TASK.cancel()
        try:
            await ENGINE_TASK
        except:
            pass

        print("🧹 ENGINE TASK CLEANED")
