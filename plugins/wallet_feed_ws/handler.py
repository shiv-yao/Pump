import asyncio
import inspect
import importlib.util
import json
from pathlib import Path

import websockets

WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"

_FEED_TASK = None
_RUNNING = False
_STATE = {
    "running": False,
    "asset_ids": [],
    "last_event_type": None,
    "last_message": None,
    "events": 0,
    "trades_forwarded": 0,
    "errors": 0,
}


def _plugins_root() -> Path:
    cur = Path(__file__).resolve()
    for p in cur.parents:
        if (p / "plugins").exists():
            return p / "plugins"
    return Path(__file__).resolve().parent.parent


def _load_tool(tool_name: str):
    plugins_root = _plugins_root()

    for plugin_dir in plugins_root.iterdir():
        if not plugin_dir.is_dir():
            continue

        manifest_path = plugin_dir / "plugin.json"
        handler_path = plugin_dir / "handler.py"

        if not manifest_path.exists() or not handler_path.exists():
            continue

        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        if not any(t.get("name") == tool_name for t in manifest.get("tools", [])):
            continue

        spec = importlib.util.spec_from_file_location(f"plugin_{plugin_dir.name}", handler_path)
        if not spec or not spec.loader:
            continue

        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        if hasattr(mod, tool_name):
            return getattr(mod, tool_name)

    return None


async def _call_tool(tool_name: str, payload: dict):
    fn = _load_tool(tool_name)
    if not fn:
        return {"error": f"tool not found: {tool_name}"}

    if inspect.iscoroutinefunction(fn):
        return await fn(**payload)
    return fn(**payload)


def _extract_trade_rows(msg: dict):
    """
    Best-effort parsing for market websocket trade-style events.
    Returns normalized rows:
    {
      wallet, asset_id, side, price, size, timestamp
    }
    """
    rows = []

    event_type = msg.get("event_type") or msg.get("type")

    # Case 1: payload list under 'trades'
    trades = msg.get("trades")
    if isinstance(trades, list):
        for t in trades:
            rows.append({
                "wallet": str(t.get("maker") or t.get("taker") or t.get("owner") or "market_wallet"),
                "asset_id": str(t.get("asset_id") or t.get("asset") or msg.get("asset_id") or ""),
                "side": str(t.get("side") or "buy").lower(),
                "price": float(t.get("price", 0.0) or 0.0),
                "size": float(t.get("size", 0.0) or 0.0),
                "timestamp": float(t.get("timestamp", 0.0) or t.get("time", 0.0) or 0.0),
            })

    # Case 2: single trade-like event
    elif event_type in ("trade", "last_trade_price", "price_change"):
        rows.append({
            "wallet": str(msg.get("maker") or msg.get("taker") or msg.get("owner") or "market_wallet"),
            "asset_id": str(msg.get("asset_id") or msg.get("asset") or ""),
            "side": str(msg.get("side") or "buy").lower(),
            "price": float(msg.get("price", 0.0) or msg.get("last_trade_price", 0.0) or 0.0),
            "size": float(msg.get("size", 0.0) or 0.0),
            "timestamp": float(msg.get("timestamp", 0.0) or msg.get("time", 0.0) or 0.0),
        })

    # Clean rows
    out = []
    for r in rows:
        if not r["asset_id"]:
            continue
        if r["price"] <= 0:
            continue
        if r["size"] <= 0:
            continue
        if r["side"] not in ("buy", "sell"):
            r["side"] = "buy"
        out.append(r)

    return out


async def _feed_loop(asset_ids):
    global _RUNNING
    _STATE["running"] = True
    _STATE["asset_ids"] = list(asset_ids)

    subscribe_msg = {
        "assets_ids": list(asset_ids),
        "type": "market",
        "custom_feature_enabled": True
    }

    while _RUNNING:
        try:
            async with websockets.connect(WS_URL, ping_interval=20, ping_timeout=20) as ws:
                await ws.send(json.dumps(subscribe_msg))

                while _RUNNING:
                    raw = await ws.recv()
                    msg = json.loads(raw)

                    _STATE["events"] += 1
                    _STATE["last_message"] = msg
                    _STATE["last_event_type"] = msg.get("event_type") or msg.get("type")

                    rows = _extract_trade_rows(msg)
                    for row in rows:
                        await _call_tool("wa_record_trade", {
                            "wallet": row["wallet"],
                            "asset_id": row["asset_id"],
                            "side": row["side"],
                            "price": row["price"],
                            "size": row["size"],
                            "timestamp": row["timestamp"] or None,
                        })
                        _STATE["trades_forwarded"] += 1

        except asyncio.CancelledError:
            break
        except Exception as e:
            _STATE["errors"] += 1
            _STATE["last_message"] = {"error": str(e)}
            await asyncio.sleep(2)

    _STATE["running"] = False


async def start_wallet_feed_ws(asset_ids):
    global _FEED_TASK, _RUNNING

    if _RUNNING:
        return {"ok": True, "message": "already running", **_STATE}

    _RUNNING = True
    _FEED_TASK = asyncio.create_task(_feed_loop(asset_ids))
    return {"ok": True, "message": "wallet feed started", "asset_ids": asset_ids}


def stop_wallet_feed_ws():
    global _FEED_TASK, _RUNNING
    _RUNNING = False
    if _FEED_TASK:
        _FEED_TASK.cancel()
        _FEED_TASK = None
    _STATE["running"] = False
    return {"ok": True, "message": "wallet feed stopped"}


def get_wallet_feed_state():
    return dict(_STATE)
