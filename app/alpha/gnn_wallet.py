from collections import defaultdict

wallet_graph = defaultdict(dict)


def update_graph(tx):
    sender = tx.get("from")
    receiver = tx.get("to")
    amount = tx.get("amount", 0)

    if sender and receiver:
        wallet_graph[sender][receiver] = wallet_graph[sender].get(receiver, 0) + amount


def compute_score(wallet):
    edges = wallet_graph.get(wallet, {})
    volume = sum(edges.values())
    connections = len(edges)

    return min(1.0, (volume * 0.00001) + (connections * 0.05))


async def gnn_wallet_signal(symbol):
    # 假設你有 wallet feed
    wallets = ["wallet1", "wallet2", "wallet3"]

    score = 0
    for w in wallets:
        score += compute_score(w)

    score /= max(len(wallets), 1)

    if score > 0.7:
        return {
            "action": "buy",
            "score": score,
            "source": "gnn_wallet"
        }

    return {"action": "hold", "score": score}
