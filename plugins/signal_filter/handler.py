LAST = {}

def filter_signal(score, action):
    score = float(score)
    action = str(action).lower().strip()

    if action == "buy" and score < 0.6:
        return "hold"

    if action == "sell" and score > 0.4:
        return "hold"

    prev = LAST.get("last")
    if prev and prev != action:
        if abs(score - 0.5) < 0.1:
            return "hold"

    LAST["last"] = action
    return action
