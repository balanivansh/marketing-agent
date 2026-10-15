"""Database initialization and access layer for tenant SQLite databases."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Set

from core.config import get_brand_db_path
from core.logger import logfire, logger

EXPECTED_TABLES: Set[str] = {
    "research_items",
    "drafts",
    "draft_diffs",
    "style_observations",
}

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS research_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT,
    title TEXT,
    url TEXT UNIQUE,
    raw_text TEXT,
    relevance_score REAL DEFAULT 0.0,
    matched_pillar TEXT,
    one_line_angle TEXT,
    processed INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    format TEXT,
    pillar TEXT,
    target_mode TEXT,
    caption TEXT,
    payload_json TEXT,
    status TEXT DEFAULT 'pending_review',
    human_edited INTEGER DEFAULT 0,
    source_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS draft_diffs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id INTEGER,
    original_caption TEXT,
    edited_caption TEXT,
    diff_text TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(draft_id) REFERENCES drafts(id)
);

CREATE TABLE IF NOT EXISTS style_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    observation TEXT,
    count INTEGER DEFAULT 1,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def get_db_connection(tenant_id: str) -> sqlite3.Connection:
    """Get a SQLite connection for the specified tenant, ensuring directory exists."""
    db_path = get_brand_db_path(tenant_id)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


@contextmanager
def get_db_session(tenant_id: str) -> Generator[sqlite3.Connection, None, None]:
    """Context manager for safe database transactions with auto-commit and rollback."""
    conn = get_db_connection(tenant_id)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(tenant_id: str) -> Path:
    """Initialize the SQLite database for tenant_id, creating required tables."""
    with logfire.span("init_db", tenant_id=tenant_id):
        db_path = get_brand_db_path(tenant_id)
        db_path.parent.mkdir(parents=True, exist_ok=True)

        with get_db_session(tenant_id) as conn:
            conn.executescript(SCHEMA_SQL)
            try:
                conn.execute("ALTER TABLE research_items ADD COLUMN matched_pillar TEXT;")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("ALTER TABLE research_items ADD COLUMN one_line_angle TEXT;")
            except sqlite3.OperationalError:
                pass

        logger.info(f"Database initialized for tenant '{tenant_id}' at {db_path}")
        return db_path


def clear_research_items(tenant_id: str) -> int:
    """Clear all records from research_items table for a given tenant."""
    init_db(tenant_id)
    with get_db_session(tenant_id) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM research_items;")
        count = cursor.fetchone()[0]
        cursor.execute("DELETE FROM research_items;")
        try:
            cursor.execute("DELETE FROM sqlite_sequence WHERE name='research_items';")
        except sqlite3.OperationalError:
            pass
        logger.info(f"Cleared {count} research items for tenant '{tenant_id}'.")
        return count


def get_existing_tables(tenant_id: str) -> Set[str]:
    """Return the set of user table names existing in the tenant database."""
    conn = get_db_connection(tenant_id)
    try:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
        )
        return {row[0] for row in cursor.fetchall()}
    finally:
        conn.close()
