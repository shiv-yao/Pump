from fastapi import FastAPI
import asyncio
from app.engine.main import main_loop

app = FastAPI()

@app.on_event("startup")
async def startup():
    asyncio.create_task(main_loop())

@app.get("/")
def root():
    return {"status": "running"}
