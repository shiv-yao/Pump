from __future__ import annotations

import asyncio

from app.db.database import db
from app.services.trading import simulate_trade


async def background_trading_loop():
    while True:
        with db() as conn:
            rows = conn.execute(
                '''
                SELECT s.user_id
                FROM trading_state s
                JOIN trading_settings t ON t.user_id = s.user_id
                WHERE s.running = 1 AND t.auto_trading_enabled = 1
                '''
            ).fetchall()

        for row in rows:
            try:
                simulate_trade(row["user_id"])
            except Exception:
                pass

        await asyncio.sleep(8)\n