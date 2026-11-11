"""
backend/app/database/connection.py
Thread-safe SQLite database connection and schema management for FakeNewsBlockchain.
"""

import sqlite3
import logging
from pathlib import Path
from contextlib import contextmanager
from backend.app.config import get_settings

logger = logging.getLogger(__name__)

DB_PATH: Path = get_settings().get_absolute_path("data/database/fakenews.db")


def get_db_path() -> Path:
    """Ensures database directory exists and returns absolute path."""
    db_path = get_settings().get_absolute_path("data/database/fakenews.db")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


@contextmanager
def get_db_connection():
    """
    Context manager providing a SQLite connection configured for concurrent access:
    - WAL (Write-Ahead Logging) journal mode
    - 5000ms busy timeout
    - Row factory enabled for dictionary-style column access
    """
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path), timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Database error during transaction: {e}")
        raise
    finally:
        conn.close()


def init_db():
    """Initializes SQLite schema and ensures tables and indexes exist."""
    with get_db_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS verification_records (
                verification_id TEXT PRIMARY KEY,
                content_type TEXT NOT NULL,
                title TEXT,
                content_preview TEXT NOT NULL,
                original_content TEXT NOT NULL,
                verdict TEXT NOT NULL,
                confidence_score REAL NOT NULL,
                explanation TEXT NOT NULL,
                evidence_json TEXT,
                canonical_record_json TEXT NOT NULL,
                record_hash TEXT NOT NULL,
                blockchain_anchored INTEGER DEFAULT 0,
                blockchain_status TEXT DEFAULT 'unanchored',
                network TEXT,
                chain_id INTEGER,
                contract_address TEXT,
                transaction_hash TEXT,
                block_number INTEGER,
                block_timestamp INTEGER,
                block_datetime TEXT,
                submitter_address TEXT,
                gas_used INTEGER,
                etherscan_url TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)

        # Indexes for fast search and filtering
        conn.execute("CREATE INDEX IF NOT EXISTS idx_verif_created ON verification_records(created_at DESC);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_verif_verdict ON verification_records(verdict);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_verif_status ON verification_records(blockchain_status);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_verif_content_type ON verification_records(content_type);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_verif_tx_hash ON verification_records(transaction_hash);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_verif_record_hash ON verification_records(record_hash);")

        logger.info("SQLite database schema initialized at %s", get_db_path())
