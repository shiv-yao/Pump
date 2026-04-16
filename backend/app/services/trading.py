from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.ai_fund.fund_brain import decide_trade
from app.db.database import db
from app.execution_ai.service import execute, predict_fill_probability, predict_slippage, realized_pnl
from app.rl_engine.policy import policy_score
from app.sim2real.service import shadow_validation


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_status(user_id: str) -> dict:
    with db() as conn:
        state = conn.execute(
            '''
            SELECT running, daily_pnl_usd, total_pnl_usd, trades_today, win_rate_pct,
                   max_drawdown_pct, last_signal
            FROM trading_state WHERE user_id = ?
            ''',
            (user_id,),
        ).fetchone()
        settings = conn.execute(
            '''
            SELECT paper_mode, strategy_mode, execution_provider, max_position_usd,
                   daily_loss_limit_usd, auto_trading_enabled, integration_unlocked
            FROM trading_settings WHERE user_id = ?
            ''',
            (user_id,),
        ).fetchone()

    return {
        "running": bool(state["running"]),
        "daily_pnl_usd": float(state["daily_pnl_usd"]),
        "total_pnl_usd": float(state["total_pnl_usd"]),
        "trades_today": int(state["trades_today"]),
        "win_rate_pct": float(state["win_rate_pct"]),
        "max_drawdown_pct": float(state["max_drawdown_pct"]),
        "last_signal": state["last_signal"],
        "paper_mode": bool(settings["paper_mode"]),
        "strategy_mode": settings["strategy_mode"],
        "execution_provider": settings["execution_provider"],
        "max_position_usd": float(settings["max_position_usd"]),
        "daily_loss_limit_usd": float(settings["daily_loss_limit_usd"]),
        "auto_trading_enabled": bool(settings["auto_trading_enabled"]),
        "integration_unlocked": bool(settings["integration_unlocked"]),
    }


def update_config(user_id: str, payload: dict) -> dict:
    with db() as conn:
        conn.execute(
            '''
            UPDATE trading_settings
            SET paper_mode = ?, strategy_mode = ?, execution_provider = ?, max_position_usd = ?,
                daily_loss_limit_usd = ?, auto_trading_enabled = ?, updated_at = ?
            WHERE user_id = ?
            ''',
            (
                int(payload["paper_mode"]),
                payload["strategy_mode"],
                payload["execution_provider"],
                payload["max_position_usd"],
                payload["daily_loss_limit_usd"],
                int(payload["auto_trading_enabled"]),
                _now(),
                user_id,
            ),
        )
    return get_status(user_id)


def unlock_integration(user_id: str, confirm_text: str) -> dict:
    if confirm_text.strip() != "I understand the risk":
        raise ValueError("Unlock phrase mismatch")
    with db() as conn:
        conn.execute(
            "UPDATE trading_settings SET integration_unlocked = 1, updated_at = ? WHERE user_id = ?",
            (_now(), user_id),
        )
    return get_status(user_id)


def start_trading(user_id: str) -> dict:
    with db() as conn:
        conn.execute(
            "UPDATE trading_state SET running = 1, last_signal = ?, updated_at = ? WHERE user_id = ?",
            ("System started", _now(), user_id),
        )
    return get_status(user_id)


def stop_trading(user_id: str) -> dict:
    with db() as conn:
        conn.execute(
            "UPDATE trading_state SET running = 0, last_signal = ?, updated_at = ? WHERE user_id = ?",
            ("System stopped", _now(), user_id),
        )
    return get_status(user_id)


def _record_trade(user_id: str, trade: dict, pnl: float, slippage_bps: float, fill_prob: float, mode: str, provider_label: str, rl_score: float) -> dict:
    with db() as conn:
        conn.execute(
            '''
            INSERT INTO trades (
                id, user_id, symbol, side, pnl_usd, size_usd, slippage_bps, fill_prob,
                strategy_name, regime, mode, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                uuid.uuid4().hex,
                user_id,
                trade["symbol"],
                trade["side"],
                pnl,
                trade["size_usd"],
                slippage_bps,
                fill_prob,
                trade["strategy_name"],
                trade["regime"],
                mode,
                _now(),
            ),
        )

        state = conn.execute(
            "SELECT daily_pnl_usd, total_pnl_usd, trades_today, max_drawdown_pct FROM trading_state WHERE user_id = ?",
            (user_id,),
        ).fetchone()

        daily = float(state["daily_pnl_usd"]) + pnl
        total = float(state["total_pnl_usd"]) + pnl
        trades_today = int(state["trades_today"]) + 1

        wins = conn.execute("SELECT COUNT(*) AS c FROM trades WHERE user_id = ? AND pnl_usd > 0", (user_id,)).fetchone()["c"]
        total_trades = conn.execute("SELECT COUNT(*) AS c FROM trades WHERE user_id = ?", (user_id,)).fetchone()["c"]
        win_rate = round((wins / total_trades) * 100, 2) if total_trades else 0.0
        max_drawdown = round(max(abs(min(0.0, daily)), float(state["max_drawdown_pct"])), 2)

        conn.execute(
            '''
            UPDATE trading_state
            SET daily_pnl_usd = ?, total_pnl_usd = ?, trades_today = ?, win_rate_pct = ?,
                max_drawdown_pct = ?, last_signal = ?, updated_at = ?
            WHERE user_id = ?
            ''',
            (
                daily,
                total,
                trades_today,
                win_rate,
                max_drawdown,
                f"{trade['strategy_name']} | regime={trade['regime']} | rl={rl_score} | provider={provider_label}",
                _now(),
                user_id,
            ),
        )

    return get_status(user_id)


def simulate_trade(user_id: str) -> dict:
    status = get_status(user_id)
    settings = {
        "paper_mode": status["paper_mode"],
        "strategy_mode": status["strategy_mode"],
        "execution_provider": status["execution_provider"],
        "max_position_usd": status["max_position_usd"],
        "daily_loss_limit_usd": status["daily_loss_limit_usd"],
    }

    validation = shadow_validation(status["strategy_mode"], status["execution_provider"])
    if not validation["approved"] and not status["paper_mode"]:
        return {"ok": False, "detail": "Sim2Real gate rejected non-paper deployment", "status": status}

    trade = decide_trade(status, settings)
    slippage_bps = predict_slippage(trade["size_usd"], trade["regime"])
    fill_prob = predict_fill_probability(trade["regime"])
    rl_score = policy_score(status["strategy_mode"], trade["regime"])
    exec_result = execute(trade["symbol"], trade["size_usd"], status["execution_provider"], status["paper_mode"], allow_live=False)
    pnl = realized_pnl(trade["regime"], trade["strategy_name"])

    updated_status = _record_trade(
        user_id=user_id,
        trade=trade,
        pnl=pnl,
        slippage_bps=slippage_bps,
        fill_prob=fill_prob,
        mode="paper" if status["paper_mode"] else "integration_shadow",
        provider_label=exec_result["provider"],
        rl_score=rl_score,
    )

    return {
        "ok": True,
        "pnl_usd": pnl,
        "slippage_bps": slippage_bps,
        "fill_prob": fill_prob,
        "rl_score": rl_score,
        "sim2real": validation,
        "status": updated_status,
    }


def manual_confirm_trade(user_id: str, symbol: str, size_usd: float, confirm_text: str) -> dict:
    status = get_status(user_id)
    if confirm_text.strip() != "EXECUTE LIVE":
        raise ValueError("Confirmation phrase mismatch")
    if status["paper_mode"]:
        raise ValueError("Disable paper mode first")
    if status["execution_provider"] != "integration":
        raise ValueError("Switch execution provider to integration first")
    if not status["integration_unlocked"]:
        raise ValueError("Integration not unlocked")

    trade = {
        "symbol": symbol,
        "side": "buy",
        "size_usd": min(size_usd, status["max_position_usd"]),
        "strategy_name": "Manual Confirm",
        "regime": "manual",
    }
    slippage_bps = predict_slippage(trade["size_usd"], trade["regime"])
    fill_prob = 0.9
    rl_score = 0.0
    exec_result = execute(trade["symbol"], trade["size_usd"], status["execution_provider"], status["paper_mode"], allow_live=True)
    pnl = 0.0

    updated_status = _record_trade(
        user_id=user_id,
        trade=trade,
        pnl=pnl,
        slippage_bps=slippage_bps,
        fill_prob=fill_prob,
        mode="integration_live_manual",
        provider_label=exec_result["provider"],
        rl_score=rl_score,
    )

    return {"ok": True, "execution": exec_result, "status": updated_status}
