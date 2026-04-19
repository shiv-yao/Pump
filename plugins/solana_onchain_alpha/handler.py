import re
from collections import defaultdict
MIN_LARGE_TX = 5
EARLY_TX_THRESHOLD = 3
def extract_wallets(logs):
    wallets = []
    for log in logs:
        wallets.extend(re.findall(r"[1-9A-HJ-NP-Za-km-z]{32,44}", log))
    return wallets
def detect_amount(log):
    try:
        nums = re.findall(r"\d+\.\d+", log)
        if nums: return float(nums[0])
    except Exception:
        pass
    return 0
def analyze_onchain(logs):
    wallet_volume = defaultdict(float); wallet_count = defaultdict(int)
    for log in logs:
        wallets = extract_wallets([log]); amount = detect_amount(log)
        for w in wallets:
            wallet_volume[w] += amount; wallet_count[w] += 1
    ranked = sorted(wallet_volume.items(), key=lambda x: x[1], reverse=True)
    if not ranked: return "No activity"
    top_wallet, vol = ranked[0]; tx_count = wallet_count[top_wallet]
    if vol > 20 and tx_count >= EARLY_TX_THRESHOLD:
        return f"🚀 EARLY SMART MONEY\nWallet: {top_wallet}\nVolume: {vol:.2f} SOL\nTxCount: {tx_count}\nSignal: BUY"
    if vol > MIN_LARGE_TX:
        return f"🔥 LARGE FLOW\nWallet: {top_wallet}\nVolume: {vol:.2f} SOL\nSignal: WATCH"
    return f"⚪ Weak signal\nWallet: {top_wallet}\nVolume: {vol:.2f} SOL\nSignal: SKIP"
def scan_onchain_activity(logs):
    return analyze_onchain(logs)
