from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from app.config import settings
from app.api.routes import router


app = FastAPI(title=settings.app_name)
app.include_router(router, prefix=settings.api_prefix)


@app.get("/api-info")
def api_info() -> dict:
    return {
        "name": settings.app_name,
        "docs": "/docs",
        "api_prefix": settings.api_prefix,
        "real_trading": settings.real_trading,
    }


@app.get("/", response_class=HTMLResponse)
def root() -> str:
    return Path(__file__).with_name("web").joinpath("index.html").read_text(encoding="utf-8")
