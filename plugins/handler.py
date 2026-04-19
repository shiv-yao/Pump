import asyncio
import json
import logging
from typing import Any, Dict

import httpx
import websockets

log = logging.getLogger(__name__)

WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
REST_BOOK_URL = "https://clob.polymarket.com/book"

BOOK_CACHE: Dict[str, Dict[str, Any]] = {}
WS_TASK = None
WS_RUNNING = False


def _normalize_book(asset_id: str, payload: dict) -> dict:
    bids_raw = payload.get("bids", []) or []
    asks_raw = payload.get("asks", []) or []

    def parse_side(rows):
        parsed = []
        for row in rows:
            try:
                price = float(row["price"])
                size = float(row.get("size", row.get("amount", 0)))
                parsed.append({"price": price, "size": size})
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
    # 這裡用兩種常見 query key 兼容
    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
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


async def _external_prob(symbol: str) -> float:
    clean = symbol.upper().replace("/", "")
    async with httpx.AsyncClient(timeout=6) as client:
        r = await client.get(f"https://api.binance.com/api/v3/ticker/24hr?symbol={clean}")
        r.raise_for_status()
        data = r.json()

    change = float(data["priceChangePercent"]) / 100.0
    prob = 0.5 + change

    if prob < 0.05:
        prob = 0.05
    if prob > 0.95:
        prob = 0.95

    return prob


def _book_imbalance(book: dict) -> float:
    bids = book.get("bids", [])[:3]
    asks = book.get("asks", [])[:3]

    bid_sz = sum(x["size"] for x in bids)
    ask_sz = sum(x["size"] for x in asks)

    total = bid_sz + ask_sz
    if total <= 0:
        return 0.0

    return (bid_sz - ask_sz) / total


async def _book_stream(asset_ids: list[str]):
    global WS_RUNNING
    WS_RUNNING = True

    while WS_RUNNING:
        try:
            async with websockets.connect(
                WS_URL,
                ping_interval=20,
                ping_timeout=20,
                max_size=2**20
            ) as ws:
                sub = {
                    "type": "market",
                    "assets_ids": asset_ids,
                    "custom_feature_enabled": True
                }
                await ws.send(json.dumps(sub))

                while WS_RUNNING:
                    raw = await ws.recv()
                    msg = json.loads(raw)

                    event_type = msg.get("event_type")
                    asset_id = msg.get("asset_id")

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
                        BOOK_CACHE[asset_id] = _normalize_book(asset_id, msg)

                    elif event_type == "best_bid_ask":
                        try:
                            bb = float(msg.get("best_bid"))
                        except Exception:
                            bb = current["best_bid"]

                        try:
                            ba = float(msg.get("best_ask"))
                        except Exception:
                            ba = current["best_ask"]

                        current["best_bid"] = bb
                        current["best_ask"] = ba
                        current["mid"] = (bb + ba) / 2 if (bb is not None and ba is not None) else current["mid"]
                        BOOK_CACHE[asset_id] = current

                    elif event_type == "last_trade_price":
                        try:
                            current["last_trade_price"] = float(msg.get("price"))
                        except Exception:
                            pass
                        BOOK_CACHE[asset_id] = current

                    elif event_type == "price_change":
                        # price_change 事件內是 price_changes array
                        price_changes = msg.get("price_changes", []) or []
                        bids = current.get("bids", [])
                        asks = current.get("asks", [])

                        bid_map = {x["price"]: x["size"] for x in bids}
                        ask_map = {x["price"]: x["size"] for x in asks}

                        for ch in price_changes:
                            try:
                                price = float(ch["price"])
                                size = float(ch["size"])
                                side = str(ch["side"]).upper()
                            except Exception:
                                continue

                            if side == "BUY":
                                if size <= 0:
                                    bid_map.pop(price, None)
                                else:
                                    bid_map[price] = size
                            elif side == "SELL":
                                if size <= 0:
                                    ask_map.pop(price, None)
                                else:
                                    ask_map[price] = size

                            try:
                                current["best_bid"] = float(ch.get("best_bid")) if ch.get("best_bid") is not None else current["best_bid"]
                            except Exception:
                                pass

                            try:
                                current["best_ask"] = float(ch.get("best_ask")) if ch.get("best_ask") is not None else current["best_ask"]
                            except Exception:
                                pass

                        new_bids = [{"price": p, "size": s} for p, s in bid_map.items()]
                        new_asks = [{"price": p, "size": s} for p, s in ask_map.items()]

                        new_bids.sort(key=lambda x: x["price"], reverse=True)
                        new_asks.sort(key=lambda x: x["price"])

                        current["bids"] = new_bids
                        current["asks"] = new_asks

                        bb = current.get("best_bid")
                        ba = current.get("best_ask")
                        current["mid"] = (bb + ba) / 2 if (bb is not None and ba is not None) else current["mid"]

                        BOOK_CACHE[asset_id] = current

        except asyncio.CancelledError:
            break
        except Exception as e:
            log.warning(f"Polymarket WS reconnecting after error: {e}")
            await asyncio.sleep(2)


async def start_polymarket_book(asset_ids: list[str]) -> str:
    global WS_TASK, WS_RUNNING

    if WS_TASK and not WS_TASK.done():
        return "Polymarket websocket stream already running"

    WS_RUNNING = True
    WS_TASK = asyncio.create_task(_book_stream(asset_ids))
    return f"Started Polymarket websocket stream for {len(asset_ids)} asset(s)"


async def stop_polymarket_book() -> str:
    global WS_RUNNING, WS_TASK
    WS_RUNNING = False

    if WS_TASK:
        WS_TASK.cancel()
        WS_TASK = None

    return "Stopped Polymarket websocket stream"


async def get_polymarket_book_cache(asset_id: str):
    book = BOOK_CACHE.get(asset_id)
    if not book:
        return {"error": "asset not in websocket cache"}
    return book


async def get_polymarket_signal_ws(asset_id: str, symbol: str):
    book = BOOK_CACHE.get(asset_id)

    if not book or book.get("mid") is None:
        book = await _fetch_book_rest(asset_id)

    if not book:
        return {"error": "orderbook failed"}

    mid = book.get("mid")
    if mid is None:
        return {"error": "no liquidity"}

    external = await _external_prob(symbol)
    imbalance = _book_imbalance(book)
    edge = external - mid

    # edge + 小幅度 imbalance 加權
    combined = edge + (imbalance * 0.01)

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
        "external_prob": external,
        "edge": edge,
        "imbalance": imbalance,
        "combined_score": combined,
        "action": action,
        "confidence": confidence,
        "best_bid": book.get("best_bid"),
        "best_ask": book.get("best_ask"),
        "last_trade_price": book.get("last_trade_price"),
    }
