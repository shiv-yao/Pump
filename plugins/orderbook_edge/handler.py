def get_limit_price(bid, ask, side):
    bid = float(bid)
    ask = float(ask)
    spread = ask - bid

    if spread < 0.01:
        return None

    s = side.lower().strip()

    if s == "buy":
        return bid + spread * 0.2
    elif s == "sell":
        return ask - spread * 0.2

    return None
