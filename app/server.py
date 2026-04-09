from fastapi import FastAPI
import asyncio

from app.engine.loop import main_loop

app = FastAPI()

@app.on_event("startup")
async def startup():
    print("🚀 PRODUCTION SERVER START")
    asyncio.create_task(main_loop())
