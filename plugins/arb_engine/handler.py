import asyncio
import json
import importlib.util
import inspect
from pathlib import Path

RUNNING = False


# ========= loader =========
def _root():
    for p in Path(__file__).resolve().parents:
        if (p / "plugins").exists():
            return p / "plugins"
    return Path(__file__).resolve().parent.parent


def _load(tool):
    for d in _root().iterdir():
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
    fn = _load(tool)
    if not fn:
        return {"error": f"{tool} not found"}

    if inspect.iscoroutinefunction(fn):
        return await fn(**payload)
    return fn(**payload)


# ========= 核心套利 =========

async def run_arb(asset_id, symbol, capital=10, loops=999, edge_threshold=0.02):

    global RUNNING
    RUNNING = True

    logs = []

    # 啟動 WS
    await call("start_polymarket_book", {"asset_ids": [asset_id]})

    for i in range(int(loops)):

        if not RUNNING:
            break

        try:
            # ===== 1️⃣ Polymarket alpha =====
            pm = await call("get_polymarket_signal_ws", {
                "asset_id": asset_id,
                "symbol": symbol
            })

            if "error" in pm:
                await asyncio.sleep(1)
                continue

            pm_mid = pm["mid_price"]
            ext = pm["external_prob"]
            edge = ext - pm_mid
            imbalance = pm["imbalance"]

            # ===== 2️⃣ edge 過濾 =====
            if abs(edge) < edge_threshold:
                logs.append(f"[{i}] no edge {edge:.4f}")
                await asyncio.sleep(0.5)
                continue

            # ===== 3️⃣ orderbook 過濾 =====
            if abs(imbalance) < 0.1:
                logs.append(f"[{i}] weak flow")
                await asyncio.sleep(0.5)
                continue

            # ===== 4️⃣ 風控 =====
            can = await call("can_trade", {})
            if not can:
                logs.append(f"[{i}] blocked")
                await asyncio.sleep(1)
                continue

            # ===== 5️⃣ 倉位 =====
            size = await call("position_size", {
                "score": abs(edge),
                "capital": capital
            })

            try:
                size = float(size)
            except:
                size = capital * 0.1

            # ===== 6️⃣ 決策 =====
            if edge > 0:
                side = "buy"   # long YES
                action = "LONG YES"
            else:
                side = "sell"  # short YES
                action = "SHORT YES"

            # ===== 7️⃣ 下單 =====
            res = await call("route_order", {
                "target": "polymarket",
                "side": side,
                "symbol": asset_id,
                "amount": size
            })

            logs.append({
                "loop": i,
                "edge": edge,
                "imbalance": imbalance,
                "action": action,
                "size": size,
                "res": res
            })

            # ===== 8️⃣ 風控更新 =====
            await call("check_risk", {"pnl": 0})

        except Exception as e:
            logs.append(str(e))

        await asyncio.sleep(0.5)

    return logs


def stop_arb():
    global RUNNING
    RUNNING = False
    return "stopped"
