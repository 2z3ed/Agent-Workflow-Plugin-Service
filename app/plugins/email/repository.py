import json
import os
import sqlite3
from pathlib import Path

from app.config import settings


TABLE_SQL = """
CREATE TABLE IF NOT EXISTS email_processed (
    message_id TEXT PRIMARY KEY,
    mailbox_email TEXT,
    sender TEXT,
    subject TEXT,
    received_time DATETIME,
    analysis_result TEXT,
    processed_at DATETIME
)
"""


def _get_connection() -> sqlite3.Connection:
    db_path = Path(settings.database_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(db_path)


def init_email_db() -> None:
    with _get_connection() as conn:
        conn.execute(TABLE_SQL)
        conn.commit()


def is_duplicate(message_id: str) -> bool:
    with _get_connection() as conn:
        cursor = conn.execute(
            "SELECT 1 FROM email_processed WHERE message_id = ? LIMIT 1",
            (message_id,),
        )
        return cursor.fetchone() is not None


def save_processed(
    message_id: str,
    mailbox_email: str,
    sender: str,
    subject: str,
    received_time: str,
    analysis_result,
) -> None:
    processed_at = __import__("datetime").datetime.utcnow().isoformat()
    analysis_json = json.dumps(analysis_result, ensure_ascii=False)
    with _get_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO email_processed
            (message_id, mailbox_email, sender, subject, received_time, analysis_result, processed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (message_id, mailbox_email, sender, subject, received_time, analysis_json, processed_at),
        )
        conn.commit()
