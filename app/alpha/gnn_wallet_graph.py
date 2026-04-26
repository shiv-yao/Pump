from collections import defaultdict
from app.utils.loader import call

wallet_graph = defaultdict(lambda: {"score": 0, "edges": set()})

DECAY = 0.9
BOOST = 1.2


async def update_wallet_graph(tx):
    wallets = tx.get("wallets", [])
    token = tx.get("token")

    for w in wallets:
        wallet_graph[w]["score"] *= DECAY
        wallet_graph[w]["edges"].update(wallets)

        # 早期進場加分
        if tx.get("early"):
            wallet_graph[w]["score"] += BOOST


async def get_wallet_score(token):
    data = await call("get_recent_transactions", {"token": token})

    for tx in data.get("txs", []):
        await update_wallet_graph(tx)

    # 找 leader
    leaders = sorted(
        wallet_graph.items(),
        key=lambda x: x[1]["score"],
        reverse=True
    )[:5]

    return {
        "leaders": [w for w, _ in leaders],
        "score": sum(v["score"] for _, v in leaders) / (len(leaders) + 1)
    }
