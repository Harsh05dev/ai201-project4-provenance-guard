import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "provenance.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS content (
                content_id TEXT PRIMARY KEY,
                creator_id TEXT NOT NULL,
                text TEXT NOT NULL,
                content_type TEXT NOT NULL DEFAULT 'text',
                attribution TEXT,
                confidence REAL,
                status TEXT NOT NULL DEFAULT 'classified',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content_id TEXT,
                creator_id TEXT,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS verified_creators (
                creator_id TEXT PRIMARY KEY,
                verified_at TEXT NOT NULL
            );
            """
        )
