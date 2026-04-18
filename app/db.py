import logging
import psycopg
from psycopg.rows import dict_row

from app.settings import DATABASE_URL

log = logging.getLogger(__name__)


def get_db_conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL 未設定")
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def init_plugin_db():
    conn = get_db_conn()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS installed_plugins (
        id BIGSERIAL PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
        url TEXT NOT NULL,
        installed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)

    conn.commit()
    cur.close()
    conn.close()


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

        return [
            {
                "name": row["name"],
                "url": row["url"],
                "installed_at": str(row["installed_at"]),
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
        cur.execute("""
            INSERT INTO installed_plugins (name, url)
            VALUES (%s, %s)
            ON CONFLICT (name)
            DO UPDATE SET url = EXCLUDED.url
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
        cur.execute("DELETE FROM installed_plugins WHERE name = %s", (name,))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        log.error(f"Failed to forget plugin '{name}': {e}")
