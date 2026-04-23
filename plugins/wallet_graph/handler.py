GRAPH = {}


def record_transfer(src, dst, amount):
    if src not in GRAPH:
        GRAPH[src] = {}

    GRAPH[src][dst] = GRAPH[src].get(dst, 0) + amount


def get_wallet_score(wallet):
    if wallet not in GRAPH:
        return 0.0

    edges = GRAPH[wallet]

    score = sum(edges.values())

    return min(score / 1000, 1.0)
