from __future__ import annotations

from fastapi import FastAPI
from app.config import settings
from app.api.routes import router


app = FastAPI(title=settings.app_name)
app.include_router(router, prefix=settings.api_prefix)


@app.get("/")
def root() -> dict:
    return {
        "name": settings.app_name,
        "docs": "/docs",
        "api_prefix": settings.api_prefix,
        "real_trading": settings.real_trading,
    }
