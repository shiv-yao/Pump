from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.db.database import db

PLANS = {
    "free": {"price_usd": 0, "features": ["dashboard", "paper"]},
    "pro": {"price_usd": 29, "features": ["dashboard", "reports", "api", "controls"]},
    "fund": {"price_usd": 199, "features": ["dashboard", "reports", "allocator", "investor_view"]},
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_plans() -> dict:
    return PLANS


def checkout(user_id: str, plan: str) -> dict:
    if plan not in {"pro", "fund"}:
        raise ValueError("Invalid plan")
    with db() as conn:
        conn.execute("UPDATE users SET plan = ?, active = 1 WHERE id = ?", (plan, user_id))
        conn.execute(
            '''
            INSERT INTO subscriptions (id, user_id, provider, provider_ref, plan, status, updated_at)
            VALUES (?, ?, 'mock', ?, ?, 'active', ?)
            ''',
            (uuid.uuid4().hex, user_id, f"mock_{plan}", plan, _now()),
        )
    return {"ok": True, "plan": plan, "message": f"Mock checkout complete for {plan}"}\n