def get_limit_price(bid, ask, side):

    spread = ask - bid

    # 太窄 → 不下單
    if spread < 0.01:
        return None

    if side == "buy":
        return bid + spread * 0.2   # 插隊
    else:
        return ask - spread * 0.2
