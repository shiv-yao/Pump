import asyncio
import json
import logging
from typing import Dict, Any

import httpx
import websockets

log = logging.getLogger(__name__)

WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
REST_BOOK_URL = "https://clob.polymarket.com/book"

# in-memory cache
BOOK_CACHE: Dict[str, Dict[str, Any]] = {}
WS_TASK = None
WS_RUNNING = False


def _normalize_book(asset_id: str, payload: dict) -> dict:
    """
    Normalize WS/REST book into a shared shape:
    {
      "asset_id": str,
      "bids": [{"price": float, "size": float}],
      "asks": [{"price": float, "size": float}],
      "best_bid": float|None,
      "best_ask": float|None,
      "mid": float|None,
      "last_trade_price": float|None
    }
    """
    bids_raw = payload.get("bids", []) or []
    asks_raw = payload.get("asks", []) or []

    def parse_side(rows):
        parsed = []
        for x in rows:
            try:
                # official docs show book objects with price/size fields on orderbook endpoints
                p = float(x["price"])
                s = float(x.get("size", x.get("amount", 0)))
                parsed.append({"price": p, "size": s})
            except Exception:
                continue
        return parsed

    bids = parse_side(bids_raw)
    asks = parse_side(asks_raw)

    best_bid = bids[0]["price"] if bids else None
    best_ask = asks[0]["price"] if asks else None
    mid = (best_bid + best_ask) / 2 if (best_bid is not None and best_ask is not None) else None

    last_trade = payload.get("last_trade_price")
    try:
        last_trade = float(last_trade) if last_trade is not None else None
    except Exception:
        last_trade = None

    return {
        "asset_id": asset_id,
        "bids": bids,
        "asks": asks,
        "best_bid": best_bid,
        "best_ask": best_ask,
        "mid": mid,
        "last_trade_price": last_trade,
    }


async def _fetch_book_rest(asset_id: str) -> dict | None:
    """
    REST fallback.
    Official docs expose GET /book on clob.polymarket.com. The exact query/body format may vary by SDK wrapper,
    so this implementation first tries query param token_id, then asset_id.
    """
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            # try token_id style
            r = await client.get(REST_BOOK_URL, params={"token_id": asset_id})
            if r.status_code != 200:
                r = await client.get(REST_BOOK_URL, params={"asset_id": asset_id})
            if r.status_code != 200:
                return None
            data = r.json()
            return _normalize_book(asset_id, data)
    except Exception as e:
        log.warning(f"REST book fetch failed for {asset_id}: {e}")
        return None


async def _book_stream(asset_ids: list[str]):
    global WS_RUNNING
    WS_RUNNING = True

    while WS_RUNNING:
        try:
            async with websockets.connect(WS_URL, ping_interval=20, ping_timeout=20) as ws:
                # market channel uses asset ids for subscription per official docs
                sub = {
                    "type": "subscribe",
                    "assets_ids": asset_ids
                }
                # Some websocket servers expect "asset_ids"; send both defensively.
                await ws.send(json.dumps(sub))
                await ws.send(json.dumps({
                    "type": "subscribe",
                    "asset_ids": asset_ids
                }))

                while WS_RUNNING:
                    raw = await ws.recv()
                    msg = json.loads(raw)

                    # Market channel emits message types like:
                    # book / price_change / best_bid_ask / last_trade_price / market events
                    # We'll update cache conservatively.
                    event_type = msg.get("event_type") or msg.get("type") or msg.get("event")
                    asset_id = msg.get("asset_id") or msg.get("assetId") or msg.get("token_id")

                    if not asset_id:
                        # some payloads may nest data
                        data = msg.get("data", {})
                        asset_id = data.get("asset_id") or data.get("assetId") or data.get("token_id")
                    else:
                        data = msg.get("data", msg)

                    if not asset_id:
                        continue

                    current = BOOK_CACHE.get(asset_id, {
                        "asset_id": asset_id,
                        "bids": [],
                        "asks": [],
                        "best_bid": None,
                        "best_ask": None,
                        "mid": None,
                        "last_trade_price": None,
                    })

                    if event_type == "book":
                        BOOK_CACHE[asset_id] = _normalize_book(asset_id, data)

                    elif event_type == "best_bid_ask":
                        try:
                            bb = float(data.get("best_bid"))
                        except Exception:
                            bb = current["best_bid"]
                        try:
                            ba = float(data.get("best_ask"))
                        except Exception:
                            ba = current["best_ask"]

                        current["best_bid"] = bb
                        current["best_ask"] = ba
                        current["mid"] = (bb + ba) / 2 if (bb is not None and ba is not None) else current["mid"]
                        BOOK_CACHE[asset_id] = current

                    elif event_type == "last_trade_price":
                        try:
                            current["last_trade_price"] = float(data.get("price"))
                        except Exception:
                            pass
                        BOOK_CACHE[asset_id] = current

                    elif event_type == "price_change":
                        # no direct book mutation needed, but preserve cache
                        BOOK_CACHE[asset_id] = current

        except Exception as e:
            log.warning(f"Polymarket WS reconnecting: {e}")
            await asyncio.sleep(2)


async def start_polymarket_book(asset_ids: list[str]) -> str:
    global WS_TASK, WS_RUNNING

    if WS_TASK and not WS_TASK.done():
        return "Polymarket book stream already running"

    WS_RUNNING = True
    WS_TASK = asyncio.create_task(_book_stream(asset_ids))
    return f"Started Polymarket market-channel stream for {len(asset_ids)} asset(s)"


async def stop_polymarket_book() -> str:
    global WS_RUNNING, WS_TASK
    WS_RUNNING = False
    if WS_TASK:
        WS_TASK.cancel()
        WS_TASK = None
    return "Stopped Polymarket book stream"


async def _external_prob(symbol: str) -> float:
    """
    Very simple external proxy:
    Use Binance 24h price change to nudge 0.5 into a probability band.
    Replace this with your real forecast model later.
    """
    clean = symbol.upper().replace("/", "")
    async with httpx.AsyncClient(timeout=6) as client:
        r = await client.get(f"https://api.binance.com/api/v3/ticker/24hr?symbol={clean}")
        r.raise_for_status()
        data = r.json()

    change = float(data["priceChangePercent"]) / 100.0
    # clamp into [0.05, 0.95]
    prob = 0.5 + change
    if prob < 0.05:
        prob = 0.05
    if prob > 0.95:
        prob = 0.95
    return prob


def _book_imbalance(book: dict) -> float:
    """
    Top-3 level imbalance in [-1, 1]
    """
    bids = book.get("bids", [])[:3]
    asks = book.get("asks", [])[:3]

    bid_sz = sum(x["size"] for x in bids)
    ask_sz = sum(x["size"] for x in asks)

    total = bid_sz + ask_sz
    if total <= 0:
        return 0.0
    return (bid_sz - ask_sz) / total


async def get_polymarket_signal(asset_id: str, symbol: str) -> dict:
    """
    Reads cached WS orderbook first, REST fallback second, then outputs:
    {
      "mid_price": ...,
      "external_prob": ...,
      "edge": ...,
      "imbalance": ...,
      "action": "buy_yes"|"buy_no"|"hold",
      "confidence": ...
    }
    """
    book = BOOK_CACHE.get(asset_id)

    if not book or book.get("mid") is None:
        book = await _fetch_book_rest(asset_id)

    if not book:
        return {"error": "orderbook failed"}

    mid = book.get("mid")
    if mid is None:
        return {"error": "no liquidity"}

    ext = await _external_prob(symbol)
    edge = ext - mid
    imb = _book_imbalance(book)

    # combine edge + imbalance
    combined = edge + (imb * 0.01)

    if combined > 0.02:
        action = "buy_yes"
    elif combined < -0.02:
        action = "buy_no"
    else:
        action = "hold"

    confidence = min(abs(combined) / 0.05, 1.0)

    return {
        "asset_id": asset_id,
        "mid_price": mid,
        "external_prob": ext,
        "edge": edge,
        "imbalance": imb,
        "action": action,
        "confidence": confidence,
        "best_bid": book.get("best_bid"),
        "best_ask": book.get("best_ask"),
        "last_trade_price": book.get("last_trade_price"),
    }
