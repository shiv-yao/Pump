import os, json, httpx
BASE_URL = os.getenv("TRADING_API_BASE", "").strip()
API_KEY = os.getenv("TRADING_API_KEY", "").strip()
def _headers():
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
        headers["X-API-KEY"] = API_KEY
    return headers
def _base_check():
    if not BASE_URL: return "TRADING_API_BASE 未設定"
    return None
async def _get(path: str):
    err = _base_check()
    if err: return err
    url = f"{BASE_URL.rstrip('/')}/{path.lstrip('/')}"
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(url, headers=_headers())
            if r.status_code >= 400: return f"HTTP {r.status_code}: {r.text}"
            try: return json.dumps(r.json(), ensure_ascii=False, indent=2)
            except Exception: return r.text
    except Exception as e:
        return f"GET {path} error: {e}"
async def _post(path: str, payload: dict):
    err = _base_check()
    if err: return err
    url = f"{BASE_URL.rstrip('/')}/{path.lstrip('/')}"
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(url, headers=_headers(), json=payload)
            if r.status_code >= 400: return f"HTTP {r.status_code}: {r.text}"
            try: return json.dumps(r.json(), ensure_ascii=False, indent=2)
            except Exception: return r.text
    except Exception as e:
        return f"POST {path} error: {e}"
async def get_balance() -> str: return await _get("balance")
async def get_positions() -> str: return await _get("positions")
async def get_orders() -> str: return await _get("orders")
async def buy_token(symbol: str, amount: float) -> str: return await _post("buy", {"symbol": symbol.upper(), "amount": amount})
async def sell_token(symbol: str, amount: float) -> str: return await _post("sell", {"symbol": symbol.upper(), "amount": amount})
async def kill_switch() -> str: return await _post("killswitch", {})
