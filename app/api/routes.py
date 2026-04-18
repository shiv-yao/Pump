from __future__ import annotations

from fastapi import APIRouter, HTTPException
from app.models.schemas import RunRequest
from app.core.router import run_pipeline
from app.core.plugin_marketplace import list_plugins, enable_plugin, disable_plugin
from app.core.state import engine


router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"ok": True, "running": engine.running}


@router.post("/run")
async def run(payload: RunRequest):
    return await run_pipeline(payload)


@router.get("/plugins")
def plugins():
    return list_plugins()


@router.post("/plugins/{slug}/enable")
def plugins_enable(slug: str):
    plugin = enable_plugin(slug)
    if not plugin:
        raise HTTPException(status_code=404, detail="Plugin not found")
    return plugin


@router.post("/plugins/{slug}/disable")
def plugins_disable(slug: str):
    plugin = disable_plugin(slug)
    if not plugin:
        raise HTTPException(status_code=404, detail="Plugin not found")
    return plugin


@router.get("/engine/logs")
def logs():
    return {"logs": list(engine.logs)}


@router.get("/engine/trades")
def trades():
    return {"trades": engine.trades[-50:]}
