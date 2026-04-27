import os
from fastapi import APIRouter
from app.state import state

router = APIRouter()


def env_bool(name, default="false"):
    return os.getenv(name, default).lower() in {"1", "true", "yes", "on"}


@router.get("/api/diagnostics/why-no-trade")
async def why_no_trade():
    logs = list(state.get("logs", []) or [])
    trades = list(state.get("trade_history", []) or [])
    positions = list(state.get("positions", []) or [])

    reasons = []
    fixes = []

    if not env_bool("AUTO_TRADING"):
        reasons.append("AUTO_TRADING 沒開，主引擎不會跑。")
        fixes.append("Railway Variables 設 AUTO_TRADING=true")

    if not state.get("running", False):
        reasons.append("state.running=false，runtime 目前沒啟動。")
        fixes.append("到 /docs 執行 POST /api/trading/start，或重新部署。")

    if env_bool("ENABLE_DEX_SNIPER", "true"):
        if any("HTTP 451" in str(x) for x in logs):
            reasons.append("DEX scanner 被擋，出現 HTTP 451。")
            fixes.append("設 ENABLE_DEX_SNIPER=false，改用 ENABLE_ONCHAIN_SNIPER=true。")

    if not env_bool("ENABLE_ONCHAIN_SNIPER"):
        reasons.append("ENABLE_ONCHAIN_SNIPER=false，鏈上 sniper 沒有啟動。")
        fixes.append("Railway Variables 設 ENABLE_ONCHAIN_SNIPER=true")

    if not os.getenv("SOLANA_WS", "").strip():
        reasons.append("SOLANA_WS 是空的，鏈上 WebSocket 沒資料。")
        fixes.append("設 SOLANA_WS=wss://api.mainnet-beta.solana.com")

    if env_bool("ENABLE_PUMP_SNIPER"):
        if any("530" in str(x) or "pump.fun" in str(x) for x in logs):
            reasons.append("Pump API 被擋或 530，不能當主要資料源。")
            fixes.append("設 ENABLE_PUMP_SNIPER=false")

    if any("[LIQ] low out" in str(x) for x in logs):
        reasons.append("Jupiter quote 流動性不足，候選幣被過濾。")
        fixes.append("測試期可設 MIN_OUT_AMOUNT=50、MAX_PRICE_IMPACT=0.25")

    if env_bool("MANUAL_CONFIRM", "true"):
        reasons.append("MANUAL_CONFIRM=true，即使有訊號也可能等人工確認。")
        fixes.append("測試自動流程可設 MANUAL_CONFIRM=false")

    if not env_bool("REAL_TRADING"):
        reasons.append("REAL_TRADING=false，目前是 PAPER，不會真實下單。")
        fixes.append("確認全部正常後才改 REAL_TRADING=true")

    if not trades:
        reasons.append("trade_history 是空的，表示沒有成功進入交易結果記錄。")

    return {
        "success": True,
        "status": "NO_TRADE_DIAGNOSIS",
        "summary": {
            "running": bool(state.get("running", False)),
            "mode": state.get("mode", "PAPER"),
            "positions_count": len(positions),
            "trades_count": len(trades),
            "logs_count": len(logs),
        },
        "env": {
            "AUTO_TRADING": os.getenv("AUTO_TRADING", ""),
            "ENABLE_ONCHAIN_SNIPER": os.getenv("ENABLE_ONCHAIN_SNIPER", ""),
            "ENABLE_DEX_SNIPER": os.getenv("ENABLE_DEX_SNIPER", ""),
            "ENABLE_PUMP_SNIPER": os.getenv("ENABLE_PUMP_SNIPER", ""),
            "SOLANA_WS": os.getenv("SOLANA_WS", ""),
            "REAL_TRADING": os.getenv("REAL_TRADING", ""),
            "MANUAL_CONFIRM": os.getenv("MANUAL_CONFIRM", ""),
            "MIN_OUT_AMOUNT": os.getenv("MIN_OUT_AMOUNT", ""),
            "MAX_PRICE_IMPACT": os.getenv("MAX_PRICE_IMPACT", ""),
        },
        "reasons": reasons or ["目前沒有明顯錯誤，可能只是還沒等到可交易訊號。"],
        "fixes": fixes,
        "last_logs": logs[-30:],
    }
