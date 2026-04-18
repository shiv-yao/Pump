import json

from app.settings import PLUGINS_DIR, REGISTRY_FILE


async def ensure_builtin_plugins():
    builtins = {
        "calculator": {
            "plugin_json": {
                "id": "calculator",
                "name": "calculator",
                "description": "數學計算工具",
                "version": "1.0.0",
                "enabled": True,
                "category": "utility",
                "price": 0,
                "author": "system",
                "tools": [{
                    "name": "calculate",
                    "description": "執行數學運算",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "expression": {"type": "string"}
                        },
                        "required": ["expression"]
                    }
                }]
            },
            "handler": '''import ast
import operator

def calculate(expression: str) -> str:
    ops = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
        ast.Mod: operator.mod,
    }

    def eval_node(node):
        if isinstance(node, ast.Num):
            return node.n
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp):
            return ops[type(node.op)](eval_node(node.left), eval_node(node.right))
        if isinstance(node, ast.UnaryOp):
            return ops[type(node.op)](eval_node(node.operand))
        raise ValueError(f"Unsupported expression: {node}")

    try:
        tree = ast.parse(expression, mode="eval")
        result = eval_node(tree.body)
        return f"{expression} = {result}"
    except Exception as e:
        return f"計算錯誤: {e}"
'''
        },

        "trading_signals": {
            "plugin_json": {
                "id": "trading_signals",
                "name": "trading_signals",
                "description": "加密貨幣交易信號分析",
                "version": "1.0.0",
                "enabled": True,
                "category": "trading",
                "price": 0,
                "author": "system",
                "tools": [{
                    "name": "get_trading_signal",
                    "description": "取得指定幣種的交易信號",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "symbol": {"type": "string"},
                            "timeframe": {"type": "string", "default": "1h"}
                        },
                        "required": ["symbol"]
                    }
                }]
            },
            "handler": '''import httpx

async def get_trading_signal(symbol: str, timeframe: str = "1h") -> str:
    try:
        clean_symbol = symbol.upper().replace("/", "")
        url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={clean_symbol}"

        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url)
            if r.status_code != 200:
                return f"無法取得 {symbol} 數據，HTTP {r.status_code}"

            data = r.json()
            price = float(data["lastPrice"])
            change = float(data["priceChangePercent"])
            volume = float(data["quoteVolume"])

            if change > 2:
                signal = "🟢 做多"
            elif change < -2:
                signal = "🔴 做空"
            else:
                signal = "⚪ 觀望"

            return (
                f"📊 {symbol} 信號分析\\n"
                f"時間框架: {timeframe}\\n"
                f"現價: {price:,.4f}\\n"
                f"24h漲跌: {change:+.2f}%\\n"
                f"24h成交量: {volume:,.0f} USDT\\n"
                f"信號: {signal}"
            )
    except Exception as e:
        return f"無法取得 {symbol} 數據: {e}"
'''
        },

        "market_data": {
            "plugin_json": {
                "id": "market_data",
                "name": "market_data",
                "description": "市場現價與 24h 行情資料",
                "version": "1.0.0",
                "enabled": True,
                "category": "market_data",
                "price": 0,
                "author": "system",
                "tools": [
                    {
                        "name": "get_spot_price",
                        "description": "取得現價",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "symbol": {"type": "string"}
                            },
                            "required": ["symbol"]
                        }
                    },
                    {
                        "name": "get_ticker_24h",
                        "description": "取得 24h ticker",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "symbol": {"type": "string"}
                            },
                            "required": ["symbol"]
                        }
                    }
                ]
            },
            "handler": '''import httpx
import json

def _clean(symbol: str) -> str:
    return symbol.upper().replace("/", "")

async def get_spot_price(symbol: str) -> str:
    try:
        s = _clean(symbol)
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={s}"
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url)
            if r.status_code != 200:
                return f"price error {r.status_code}: {r.text}"
            data = r.json()
            return f"{s} spot = {data.get('price')}"
    except Exception as e:
        return f"get_spot_price error: {e}"

async def get_ticker_24h(symbol: str) -> str:
    try:
        s = _clean(symbol)
        url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={s}"
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url)
            if r.status_code != 200:
                return f"ticker error {r.status_code}: {r.text}"
            data = r.json()
            out = {
                "symbol": s,
                "lastPrice": data.get("lastPrice"),
                "priceChangePercent": data.get("priceChangePercent"),
                "quoteVolume": data.get("quoteVolume"),
                "highPrice": data.get("highPrice"),
                "lowPrice": data.get("lowPrice"),
            }
            return json.dumps(out, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"get_ticker_24h error: {e}"
'''
        },

        "alpha_scanner": {
            "plugin_json": {
                "id": "alpha_scanner",
                "name": "alpha_scanner",
                "description": "簡易多幣種 alpha 掃描器",
                "version": "1.0.0",
                "enabled": True,
                "category": "scanner",
                "price": 0,
                "author": "system",
                "tools": [{
                    "name": "scan_market",
                    "description": "掃描多個交易對並排序",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "symbols": {
                                "type": "array",
                                "items": {"type": "string"}
                            }
                        },
                        "required": ["symbols"]
                    }
                }]
            },
            "handler": '''import httpx
import json

def _clean(symbol: str) -> str:
    return symbol.upper().replace("/", "")

async def scan_market(symbols: list[str]) -> str:
    results = []
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            for symbol in symbols:
                s = _clean(symbol)
                url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={s}"
                r = await client.get(url)

                if r.status_code != 200:
                    results.append({
                        "symbol": s,
                        "score": -999,
                        "status": f"HTTP {r.status_code}"
                    })
                    continue

                data = r.json()
                change = float(data["priceChangePercent"])
                quote_volume = float(data["quoteVolume"])

                # 簡易 alpha score：漲幅 + 成交量權重
                score = change + min(quote_volume / 10000000.0, 10.0)

                if score >= 8:
                    action = "BUY"
                elif score >= 3:
                    action = "WATCH"
                else:
                    action = "SKIP"

                results.append({
                    "symbol": s,
                    "price": data.get("lastPrice"),
                    "change_pct": change,
                    "quote_volume": quote_volume,
                    "score": round(score, 4),
                    "action": action
                })

        results.sort(key=lambda x: x.get("score", -999), reverse=True)
        return json.dumps(results, ensure_ascii=False, indent=2)

    except Exception as e:
        return f"scan_market error: {e}"
'''
        },
    }

    for plugin_id, data in builtins.items():
        pdir = PLUGINS_DIR / plugin_id
        pdir.mkdir(parents=True, exist_ok=True)

        plugin_json_path = pdir / "plugin.json"
        handler_path = pdir / "handler.py"

        # 每次啟動都保證內建插件存在
        with open(plugin_json_path, "w", encoding="utf-8") as f:
            json.dump(data["plugin_json"], f, ensure_ascii=False, indent=2)

        with open(handler_path, "w", encoding="utf-8") as f:
            f.write(data["handler"])

    if not REGISTRY_FILE.exists():
        with open(REGISTRY_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)
