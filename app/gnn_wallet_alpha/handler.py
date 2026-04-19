from collections import defaultdict
class WalletGraph:
    def __init__(self):
        self.edges = defaultdict(list); self.weights = defaultdict(float)
    def add_tx(self, from_w, to_w, amount):
        self.edges[from_w].append((to_w, amount)); self.weights[to_w] += amount
    def rank_wallets(self):
        return sorted(self.weights.items(), key=lambda x: x[1], reverse=True)
def detect_smart_money(graph):
    ranked = graph.rank_wallets()
    if not ranked: return None
    top_wallet, score = ranked[0]
    if score > 50000: return {"wallet": top_wallet, "signal": "BUY", "score": min(score / 100000, 1.0)}
    if score > 10000: return {"wallet": top_wallet, "signal": "WATCH", "score": 0.5}
    return {"wallet": top_wallet, "signal": "SKIP", "score": 0.1}
def analyze_wallet_graph(transactions):
    graph = WalletGraph()
    for tx in transactions:
        try: graph.add_tx(tx["from"], tx["to"], float(tx["amount"]))
        except Exception: continue
    result = detect_smart_money(graph)
    if not result: return "No signal"
    return f"🔥 Smart Money Detected\nWallet: {result['wallet']}\nSignal: {result['signal']}\nScore: {result['score']:.2f}"
