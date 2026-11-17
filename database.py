import os
import sqlite3
from pathlib import Path
from contextlib import contextmanager
from dotenv import load_dotenv

load_dotenv()  # <-- Ye line .env file se DATABASE_URL load karegi

BASE_DIR = Path(__file__).resolve().parent
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
IS_POSTGRES = DATABASE_URL.startswith("postgres://") or DATABASE_URL.startswith("postgresql://")

if IS_POSTGRES:
    import psycopg2
    import psycopg2.extras

SERVER_DB_PATH = BASE_DIR / "cloud_backup.db"
CLOUD_UPLOADS_DIR = BASE_DIR / "cloud_files"
CLOUD_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


class UnifiedCursor:
    """SQLite (?) aur PostgreSQL (%s) placeholders ko ek jaisa handle karta hai."""
    def __init__(self, cursor, is_pg: bool):
        self._cur = cursor
        self._is_pg = is_pg

    def execute(self, query: str, params: tuple = ()):
        if self._is_pg:
            query = query.replace("?", "%s")
        self._cur.execute(query, params)
        return self

    def fetchone(self):
        row = self._cur.fetchone()
        return dict(row) if row is not None else None

    def fetchall(self):
        rows = self._cur.fetchall()
        return [dict(r) for r in rows]


@contextmanager
def server_db_session():
    if IS_POSTGRES:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            cur = conn.cursor()
            yield UnifiedCursor(cur, is_pg=True)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    else:
        conn = sqlite3.connect(SERVER_DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.cursor()
            yield UnifiedCursor(cur, is_pg=False)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def init_server_db():
    """Local SQLite ya Cloud PostgreSQL mein sync table banata hai."""
    pk_col = "id SERIAL PRIMARY KEY" if IS_POSTGRES else "id INTEGER PRIMARY KEY AUTOINCREMENT"
    with server_db_session() as db:
        db.execute(
            f"""
            CREATE TABLE IF NOT EXISTS synced_records (
                {pk_col},
                table_name TEXT NOT NULL,
                record_key TEXT NOT NULL,
                device_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                is_deleted INTEGER NOT NULL DEFAULT 0,
                deleted_at TEXT,
                updated_at TEXT NOT NULL,
                server_received_at TEXT NOT NULL,
                UNIQUE(table_name, record_key)
            );
            """
        )
        db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_sync_table_time
            ON synced_records(table_name, server_received_at);
            """
        )