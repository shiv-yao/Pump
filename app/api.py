import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Starting minimal hardened API")
    yield
    log.info("Stopping minimal hardened API")


app = FastAPI(title="AI Trading System", version="5.0.1", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_class=HTMLResponse)
async def frontend():
    return "<h1>API OK</h1><p><a href='/health'>/health</a> | <a href='/docs'>/docs</a> | <a href='/debug'>/debug</a></p>"


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/debug")
async def debug():
    return {
        "status": "ok",
        "port": os.getenv("PORT"),
        "cwd": str(Path.cwd()),
    }


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log.error(f"Unhandled error on {request.url.path}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": str(exc), "path": str(request.url.path)},
    )


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)
