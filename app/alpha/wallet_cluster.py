from collections import defaultdict

# 假設你已有 wallet graph
wallet_graph = defaultdict(list)


def add_edge(w1, w2):
    wallet_graph[w1].append(w2)
    wallet_graph[w2].append(w1)


def get_cluster(wallet: str):
    visited = set()
    stack = [wallet]
    cluster = []

    while stack:
        w = stack.pop()
        if w in visited:
            continue

        visited.add(w)
        cluster.append(w)

        for n in wallet_graph.get(w, []):
            if n not in visited:
                stack.append(n)

    return cluster


def cluster_score(wallet: str, wallet_scores: dict):
    cluster = get_cluster(wallet)

    if not cluster:
        return 0.0

    total = 0
    for w in cluster:
        total += wallet_scores.get(w, 0)

    return total / len(cluster)
