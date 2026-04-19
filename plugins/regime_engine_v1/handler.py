def detect_regime(orderbook=None, trades=None):
    if not orderbook:
        return {"regime": "unknown", "confidence": 0.0}

    spread = orderbook.get("spread", 0)
    imbalance = abs(orderbook.get("imbalance", 0))

    if spread < 0.01 and imbalance > 0.3:
        return {"regime": "trend", "confidence": 0.7}

    if spread > 0.02:
        return {"regime": "chop", "confidence": 0.6}

    return {"regime": "neutral", "confidence": 0.5}
