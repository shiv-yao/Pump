from collections import defaultdict
from typing import Dict, List, Any


WALLET_DB = defaultdict(lambda: {
    "score": 0.0,
    "wins": 0,
    "losses": 0,
    "tokens": 0,
})


def update_wallet_rank(wallets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ranked = []
    for w in wallets:
        addr = w.get("wallet") or w.get("address")
        if not addr:
            continue

        row = WALLET_DB[addr]
        row["tokens"] += 1

        pnl = float(w.get("pnl", 0.0))
        if pnl > 0:
            row["wins"] += 1
            row["score"] += min(pnl, 0.2) * 2.0
        else:
            row["losses"] += 1
            row["score"] += max(pnl, -0.2)

        ranked.append({
            "wallet": addr,
            "score": row["score"],
            "wins": row["wins"],
            "losses": row["losses"],
            "tokens": row["tokens"],
        })

    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked


def smart_wallet_score(wallets: List[Dict[str, Any]]) -> float:
    ranked = update_wallet_rank(wallets)
    if not ranked:
        return 0.0
    top = ranked[:5]
    return min(sum(x["score"] for x in top) / max(len(top), 1), 1.0)
