import asyncio
import json
import time
import importlib.util
import inspect
from pathlib import Path

RUNNING = False

PORTFOLIO = {}
EQUITY = []
TOTAL_CAPITAL = 0


# ========= loader =========

def _find_plugins_root():
    for p in Path(__file__).resolve().parents:
        if (p / "plugins").exists():
            return p / "plugins"
    return Path(__file__).resolve().parent.parent


def _load(tool):
    root = _find_plugins_root()

    for d in root.iterdir():
        m = d / "plugin.json"
        h = d / "handler.py"

        if not m.exists() or not h.exists():
            continue

        try:
            manifest = json.loads(m.read_text())
        except:
            continue

        if not any(t["name"] == tool for t in manifest.get("tools", [])):
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


# ========= 核心 =========

async def run_portfolio(markets, capital=100):

    global RUNNING, TOTAL_CAPITAL
    RUNNING = True
    TOTAL_CAPITAL = capital

    # 啟動 WS
    asset_ids = [m["asset_id"] for m in markets]
    await call("start_polymarket_book", {"asset_ids": asset_ids})

    while RUNNING:

        signals = []

        # ===== 1. 掃描市場 =====
        for m in markets:
            s = await call("get_polymarket_signal_ws", {
                "asset_id": m["asset_id"],
                "symbol": m["symbol"]
            })

            if "error" in s:
                continue

            s["asset_id"] = m["asset_id"]
            signals.append(s)

        # ===== 2. 排名 alpha =====
        signals.sort(key=lambda x: abs(x["combined_score"]), reverse=True)

        top = signals[:3]  # 只挑前3個

        # ===== 3. allocation =====
        allocation = TOTAL_CAPITAL / max(len(top), 1)

        for s in top:

            asset_id = s["asset_id"]
            action = s["action"]
            score = s["combined_score"]

            if action == "hold":
                continue

            # ===== 風控 =====
            can = await call("can_trade", {})
            if not can:
                continue

            # ===== 倉位管理 =====
            pos = PORTFOLIO.get(asset_id, 0)

            if action == "buy_yes":
                side = "buy"
            elif action == "buy_no":
                side = "sell"
            else:
                continue

            # ===== 下單 =====
            result = await call("route_order", {
                "target": "polymarket",
                "side": side,
                "symbol": asset_id,
                "amount": allocation
            })

            PORTFOLIO[asset_id] = pos + allocation

        # ===== 4. 更新資金曲線 =====
        equity = sum(PORTFOLIO.values())
        EQUITY.append({
            "time": time.time(),
            "equity": equity
        })

        await asyncio.sleep(2)

    return "stopped"


# ========= 查詢 =========

def get_equity_curve():
    return EQUITY


def stop_portfolio():
    global RUNNING
    RUNNING = False
    return "stopped"
