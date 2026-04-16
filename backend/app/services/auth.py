from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone

from app.core.security import hash_password
from app.db.database import db
from app.models.schemas import SessionResponse, UserResponse


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def signup(email: str, password: str, full_name: str) -> UserResponse:
    user_id = uuid.uuid4().hex
    with db() as conn:
        existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            raise ValueError("User already exists")

        conn.execute(
            '''
            INSERT INTO users (id, email, password, full_name, plan, active, created_at)
            VALUES (?, ?, ?, ?, 'free', 1, ?)
            ''',
            (user_id, email, hash_password(password), full_name, _now()),
        )

        conn.execute(
            '''
            INSERT INTO trading_settings (
                user_id, paper_mode, strategy_mode, execution_provider,
                max_position_usd, daily_loss_limit_usd, auto_trading_enabled, updated_at
            ) VALUES (?, 1, 'safe', 'mock', 100, 100, 0, ?)
            ''',
            (user_id, _now()),
        )

        conn.execute(
            '''
            INSERT INTO trading_state (
                user_id, running, daily_pnl_usd, total_pnl_usd, trades_today,
                win_rate_pct, max_drawdown_pct, last_signal, updated_at
            ) VALUES (?, 0, 0, 0, 0, 0, 0, NULL, ?)
            ''',
            (user_id, _now()),
        )

    return UserResponse(id=user_id, email=email, full_name=full_name, plan="free", active=True)


def login(email: str, password: str) -> SessionResponse:
    with db() as conn:
        row = conn.execute(
            "SELECT id, email, full_name, plan, active, password FROM users WHERE email = ?",
            (email,),
        ).fetchone()

        if not row or row["password"] != hash_password(password):
            raise ValueError("Invalid credentials")

        token = secrets.token_hex(24)
        conn.execute(
            "INSERT INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)",
            (token, row["id"], _now()),
        )

    return SessionResponse(
        user=UserResponse(
            id=row["id"],
            email=row["email"],
            full_name=row["full_name"],
            plan=row["plan"],
            active=bool(row["active"]),
        ),
        token=token,
    )\n