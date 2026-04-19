import asyncio
import importlib.util
import inspect
import json
from pathlib import Path

RUNNING = False


# ========= 通用工具 loader =========

def _find_plugins_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        candidate = parent / "plugins"
        if candidate.exists():
            return candidate
    return Path(__file__).resolve().parent.parent


def _load_tool(tool_name: str):
    plugins_root = _find_plugins_root()

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

        spec = importlib.util.spec_from_file_location(
            f"plugin_{plugin_dir.name}", handler_path
        )
        if not spec or not spec.loader:
            continue

        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        if hasattr(mod, tool_name):
            return getattr(mod, tool_name)

    return None


async def _call(tool, payload):
    fn = _load_tool(tool)
    if not fn:
        return {"error": f"{tool} not found"}

    if inspect.iscoroutinefunction(fn):
        return await fn(**payload)
    return fn(**payload)


# ========= 核心：Polymarket 自動交易 =========

async def run_polymarket_fund(
    asset_id: str,
    symbol: str,
    capital: float = 10.0,
    loops: int = 999,
):
    """
    asset_id: Polymarket token id
    symbol: 外部對應 (BTCUSDT)
    """

    global RUNNING
    RUNNING = True

    logs = []

    # 啟動 WS（如果還沒）
    await _call("start_polymarket_book", {"asset_ids": [asset_id]})

    for i in range(int(loops)):
        if not RUNNING:
            break

        try:
            # ===== 1. 取得 alpha =====
            alpha = await _call("get_polymarket_signal_ws", {
                "asset_id": asset_id,
                "symbol": symbol
            })

            if isinstance(alpha, str):
                try:
                    alpha = json.loads(alpha)
                except:
                    alpha = {"error": alpha}

            if "error" in alpha:
                logs.append(f"[{i}] alpha error: {alpha}")
                await asyncio.sleep(1)
                continue

            score = float(alpha.get("combined_score", 0))
            action = alpha.get("action", "hold")

            # ===== 2. 風控 =====
            can = await _call("can_trade", {})
            if can is not True:
                logs.append(f"[{i}] blocked by risk")
                await asyncio.sleep(1)
                continue

            # ===== 3. 倉位 =====
            size = await _call("position_size", {
                "score": abs(score),
                "capital": capital
            })

            try:
                size = float(size)
            except:
                size = capital * 0.1

            # ===== 4. 決策 =====
            if action == "hold":
                logs.append(f"[{i}] HOLD {score:.4f}")
                await asyncio.sleep(1)
                continue

            # YES / NO mapping
            if action == "buy_yes":
                side = "buy"
                market_symbol = asset_id  # YES token
            elif action == "buy_no":
                side = "sell"
                market_symbol = asset_id
            else:
                await asyncio.sleep(1)
                continue

            # ===== 5. 下單 =====
            result = await _call("route_order", {
                "target": "polymarket",
                "side": side,
                "symbol": market_symbol,
                "amount": size
            })

            logs.append({
                "loop": i,
                "score": score,
                "action": action,
                "size": size,
                "result": result
            })

            # ===== 6. 更新風控 =====
            await _call("check_risk", {"pnl": 0})

        except Exception as e:
            logs.append(f"[{i}] ERROR {e}")

        await asyncio.sleep(1)

    return logs


# ========= 停止 =========

async def stop_fund():
    global RUNNING
    RUNNING = False
    return "stopped"
