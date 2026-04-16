from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.getenv("APP_DB_PATH", "app.db")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def db():
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with db() as conn:
        conn.executescript(
            '''
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                full_name TEXT NOT NULL,
                plan TEXT NOT NULL DEFAULT 'free',
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS trading_settings (
                user_id TEXT PRIMARY KEY,
                paper_mode INTEGER NOT NULL DEFAULT 1,
                strategy_mode TEXT NOT NULL DEFAULT 'safe',
                execution_provider TEXT NOT NULL DEFAULT 'mock',
                max_position_usd REAL NOT NULL DEFAULT 100,
                daily_loss_limit_usd REAL NOT NULL DEFAULT 100,
                auto_trading_enabled INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS trading_state (
                user_id TEXT PRIMARY KEY,
                running INTEGER NOT NULL DEFAULT 0,
                daily_pnl_usd REAL NOT NULL DEFAULT 0,
                total_pnl_usd REAL NOT NULL DEFAULT 0,
                trades_today INTEGER NOT NULL DEFAULT 0,
                win_rate_pct REAL NOT NULL DEFAULT 0,
                max_drawdown_pct REAL NOT NULL DEFAULT 0,
                last_signal TEXT,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS trades (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                pnl_usd REAL NOT NULL,
                size_usd REAL NOT NULL,
                slippage_bps REAL NOT NULL,
                fill_prob REAL NOT NULL,
                strategy_name TEXT NOT NULL,
                regime TEXT NOT NULL,
                mode TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS subscriptions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                provider_ref TEXT,
                plan TEXT NOT NULL,
                status TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            '''
        )\n