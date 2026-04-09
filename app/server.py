from fastapi import FastAPI
import asyncio

from app.engine.loop import main_loop
from app.engine.metrics import get_metrics_async

app = FastAPI()


@app.on_event("startup")
async def startup():
    print("🚀 PRODUCTION SERVER START")
    asyncio.create_task(main_loop())


@app.get("/")
def root():
    return {"status": "running"}


@app.get("/metrics")
async def metrics():
    return await get_metrics_async()
