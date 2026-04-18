import os
import sqlite3

DATABASE_URL = os.getenv("DATABASE_URL")

DB_MODE = "postgres" if DATABASE_URL else "sqlite"

SQLITE_PATH = "plugins.db"


# ===============================
# DB CONNECTION
# ===============================

def get_db_conn():
    if DB_MODE == "postgres":
        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(DATABASE_URL, row_factory=dict_row)

    else:
        conn = sqlite3.connect(SQLITE_PATH)
        conn.row_factory = sqlite3.Row
        return conn


# ===============================
# INIT TABLE
# ===============================

def init_plugin_db():
    conn = get_db_conn()
    cur = conn.cursor()

    if DB_MODE == "postgres":
        cur.execute("""
        CREATE TABLE IF NOT EXISTS plugins (
            name TEXT PRIMARY KEY,
            url TEXT,
            enabled BOOLEAN DEFAULT TRUE
        )
        """)
    else:
        cur.execute("""
        CREATE TABLE IF NOT EXISTS plugins (
            name TEXT PRIMARY KEY,
            url TEXT,
            enabled INTEGER DEFAULT 1
        )
        """)

    conn.commit()
    cur.close()
    conn.close()

    print(f"[DB] initialized ({DB_MODE})")


# ===============================
# SAVE PLUGIN
# ===============================

def save_plugin(name, url):
    conn = get_db_conn()
    cur = conn.cursor()

    if DB_MODE == "postgres":
        cur.execute("""
        INSERT INTO plugins (name, url, enabled)
        VALUES (%s, %s, TRUE)
        ON CONFLICT (name)
        DO UPDATE SET url = EXCLUDED.url, enabled = TRUE
        """, (name, url))
    else:
        cur.execute("""
        INSERT OR REPLACE INTO plugins (name, url, enabled)
        VALUES (?, ?, 1)
        """, (name, url))

    conn.commit()
    cur.close()
    conn.close()


# ===============================
# LOAD PLUGINS
# ===============================

def load_plugins():
    conn = get_db_conn()
    cur = conn.cursor()

    cur.execute("SELECT name, url FROM plugins WHERE enabled=1")
    rows = cur.fetchall()

    cur.close()
    conn.close()

    return rows


# ===============================
# DISABLE PLUGIN
# ===============================

def disable_plugin(name):
    conn = get_db_conn()
    cur = conn.cursor()

    if DB_MODE == "postgres":
        cur.execute("UPDATE plugins SET enabled=FALSE WHERE name=%s", (name,))
    else:
        cur.execute("UPDATE plugins SET enabled=0 WHERE name=?", (name,))

    conn.commit()
    cur.close()
    conn.close()
