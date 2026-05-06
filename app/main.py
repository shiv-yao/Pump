from fastapi import FastAPI
from app.api.routes.health import router as health_router
from app.api.routes.state import router as state_router
from app.api.routes.positions import router as positions_router

app = FastAPI(title="KRONOS OMEGA ADVANCED")

app.include_router(health_router)
app.include_router(state_router)
app.include_router(positions_router)

@app.get("/")
async def root():
    return {
        "system": "KRONOS OMEGA ADVANCED",
        "status": "running"
    }