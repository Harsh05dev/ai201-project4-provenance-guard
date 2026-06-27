import json
from datetime import datetime, timezone

from services.storage import get_connection


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def append_log(entry: dict, event_type: str = "classification"):
    payload = json.dumps(entry)
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO audit_log (content_id, creator_id, timestamp, event_type, payload)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                entry.get("content_id"),
                entry.get("creator_id"),
                entry.get("timestamp", _utc_now()),
                event_type,
                payload,
            ),
        )


def get_recent_entries(limit: int = 50):
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT payload FROM audit_log
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [json.loads(row["payload"]) for row in rows]
