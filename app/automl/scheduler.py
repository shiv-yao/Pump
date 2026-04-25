import asyncio
import time
import os
from app.utils.loader import call

RUNNING = False
TASK = None
LAST = {}


def interval():
    return int(os.getenv("OPTIMIZER_INTERVAL", "600"))


async def loop():
    global RUNNING

    RUNNING = True

    while RUNNING:
        try:
            result = await call("run_automl", {})

            LAST["ts"] = int(time.time())
            LAST["result"] = result

        except Exception as e:
            LAST["error"] = str(e)

        await asyncio.sleep(interval())


async def start_automl_scheduler():
    global TASK, RUNNING

    if RUNNING:
        return {"status": "already_running"}

    TASK = asyncio.create_task(loop())

    return {"status": "started"}


async def stop_automl_scheduler():
    global RUNNING

    RUNNING = False

    if TASK:
        TASK.cancel()

    return {"status": "stopped"}


async def get_automl_status():
    return {
        "running": RUNNING,
        "last": LAST,
        "interval": interval()
    }
