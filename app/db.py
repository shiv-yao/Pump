import os
import sqlite3
import logging
from pathlib import Path

log = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
SQLITE_PATH = PROJECT_ROOT / "plugins.db"

DB_MODE = "postgres" if DATABASE_URL else "sqlite"


def get_db_conn():
    if DB_MODE == "postgres":
        import psycopg
        from psycopg.rows import dict_row
        return psycopg.connect(DATABASE_URL, row_factory=dict_row)

    conn = sqlite3.connect(str(SQLITE_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_plugin_db():
    conn = get_db_conn()
    cur = conn.cursor()

    if DB_MODE == "postgres":
        cur.execute("""
        CREATE TABLE IF NOT EXISTS installed_plugins (
            id BIGSERIAL PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            url TEXT NOT NULL,
            installed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """)
    else:
        cur.execute("""
        CREATE TABLE IF NOT EXISTS installed_plugins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            url TEXT NOT NULL,
            installed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """)

    conn.commit()
    cur.close()
    conn.close()

    log.info(f"Plugin DB initialized ({DB_MODE})")


def load_installed_plugin_records() -> list[dict]:
    try:
        conn = get_db_conn()
        cur = conn.cursor()

        cur.execute("""
            SELECT name, url, installed_at
            FROM installed_plugins
            ORDER BY installed_at ASC, id ASC
        """)

        rows = cur.fetchall()
        cur.close()
        conn.close()

        if DB_MODE == "postgres":
            return [
                {
                    "name": row["name"],
                    "url": row["url"],
                    "installed_at": str(row["installed_at"]),
                }
                for row in rows
            ]

        return [
            {
                "name": row["name"],
                "url": row["url"],
                "installed_at": row["installed_at"],
            }
            for row in rows
        ]

    except Exception as e:
        log.error(f"Failed to load installed plugin records: {e}")
        return []


def remember_installed_plugin(name: str, url: str) -> None:
    try:
        conn = get_db_conn()
        cur = conn.cursor()

        if DB_MODE == "postgres":
            cur.execute("""
                INSERT INTO installed_plugins (name, url)
                VALUES (%s, %s)
                ON CONFLICT (name)
                DO UPDATE SET url = EXCLUDED.url
            """, (name, url))
        else:
            cur.execute("""
                INSERT INTO installed_plugins (name, url)
                VALUES (?, ?)
                ON CONFLICT(name)
                DO UPDATE SET url=excluded.url
            """, (name, url))

        conn.commit()
        cur.close()
        conn.close()

    except Exception as e:
        log.error(f"Failed to remember plugin '{name}': {e}")


def forget_installed_plugin(name: str) -> None:
    try:
        conn = get_db_conn()
        cur = conn.cursor()

        if DB_MODE == "postgres":
            cur.execute("""
                DELETE FROM installed_plugins
                WHERE name = %s
            """, (name,))
        else:
            cur.execute("""
                DELETE FROM installed_plugins
                WHERE name = ?
            """, (name,))

        conn.commit()
        cur.close()
        conn.close()

    except Exception as e:
        log.error(f"Failed to forget plugin '{name}': {e}")
