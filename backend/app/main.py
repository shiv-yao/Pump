from contextlib import asynccontextmanager
import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_auth import router as auth_router
from app.api.routes_billing import router as billing_router
from app.api.routes_dashboard import router as dashboard_router
from app.api.routes_trading import router as trading_router
from app.core.trading_loop import background_trading_loop
from app.db.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    task = asyncio.create_task(background_trading_loop())
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(title="AI Fund Integrated Product API", version="0.3.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api")
app.include_router(billing_router, prefix="/api")
app.include_router(dashboard_router, prefix="/api")
app.include_router(trading_router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok"}\n