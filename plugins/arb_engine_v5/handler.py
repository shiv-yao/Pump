import asyncio
import json
import importlib.util
import inspect
from pathlib import Path

RUNNING = False


# ========= loader =========
def root():
    for p in Path(__file__).resolve().parents:
        if (p / "plugins").exists():
            return p / "plugins"
    return Path(__file__).resolve().parent.parent


def load(tool):
    for d in root().iterdir():
        m = d / "plugin.json"
        h = d / "handler.py"

        if not m.exists() or not h.exists():
            continue

        try:
            data = json.loads(m.read_text())
        except:
            continue

        if not any(t["name"] == tool for t in data.get("tools", [])):
            continue

        spec = importlib.util.spec_from_file_location("mod", h)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        if hasattr(mod, tool):
            return getattr(mod, tool)

    return None


async def call(tool, payload):
    fn = load(tool)
    if not fn:
        return {"error": f"{tool} not found"}

    if inspect.iscoroutinefunction(fn):
        return await fn(**payload)
    return fn(**payload)


# ========= 核心套利 =========

async def run_arb_v5(markets, capital=50):

    global RUNNING
    RUNNING = True

    logs = []

    asset_ids = [m["asset_id"] for m in markets]

    # 啟動 WS
    await call("start_polymarket_book", {"asset_ids": asset_ids})

    while RUNNING:

        books = []

        # ===== 1️⃣ 收集所有市場 =====
        for m in markets:
            data = await call("get_polymarket_signal_ws", {
                "asset_id": m["asset_id"],
                "symbol": "BTCUSDT"
            })

            if "error" in data:
                continue

            books.append({
                "id": m["asset_id"],
                "mid": data["mid_price"],
                "imbalance": data["imbalance"]
            })

        # ===== 2️⃣ 找套利對 =====
        for i in range(len(books)):
            for j in range(i + 1, len(books)):

                a = books[i]
                b = books[j]

                spread = a["mid"] - b["mid"]

                # ===== 3️⃣ 檢查套利條件 =====
                if abs(spread) < 0.03:
                    continue

                if abs(a["imbalance"]) < 0.1 or abs(b["imbalance"]) < 0.1:
                    continue

                # ===== 4️⃣ 風控 =====
                can = await call("can_trade", {})
                if not can:
                    continue

                size = capital * 0.1

                # ===== 5️⃣ 套利執行 =====
                if spread > 0:
                    # A 貴 → 賣 A 買 B
                    await call("route_order", {
                        "target": "polymarket",
                        "side": "sell",
                        "symbol": a["id"],
                        "amount": size
                    })

                    await call("route_order", {
                        "target": "polymarket",
                        "side": "buy",
                        "symbol": b["id"],
                        "amount": size
                    })

                    logs.append(f"ARB: SELL {a['id']} / BUY {b['id']}")

                else:
                    await call("route_order", {
                        "target": "polymarket",
                        "side": "buy",
                        "symbol": a["id"],
                        "amount": size
                    })

                    await call("route_order", {
                        "target": "polymarket",
                        "side": "sell",
                        "symbol": b["id"],
                        "amount": size
                    })

                    logs.append(f"ARB: BUY {a['id']} / SELL {b['id']}")

        await asyncio.sleep(0.5)

    return logs


def stop_arb_v5():
    global RUNNING
    RUNNING = False
    return "stopped"
