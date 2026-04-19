INVENTORY = {}

MAX_ABS_POSITION = 10.0


def adjust_position(asset_id: str, size: float, side: str):
    pos = float(INVENTORY.get(asset_id, 0.0))
    qty = float(size)

    s = side.lower().strip()

    if s == "buy":
        pos += qty
    elif s == "sell":
        pos -= qty
    else:
        return {"error": f"invalid side: {side}"}

    INVENTORY[asset_id] = pos
    return {
        "asset_id": asset_id,
        "position": pos
    }


def should_reduce(asset_id: str):
    pos = float(INVENTORY.get(asset_id, 0.0))
    return abs(pos) > MAX_ABS_POSITION


def get_inventory_state():
    return INVENTORY


def reset_inventory_state():
    INVENTORY.clear()
    return {"ok": True}
