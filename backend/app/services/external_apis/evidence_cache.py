"""
Persistent SQLite cache for external API responses (Google Fact Check & GDELT DOC 2.0).
Repeated normalized queries hit cache without consuming external API or GDELT request budget.
"""

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from backend.app.config import get_settings
from backend.app.services.external_apis.quota_db import (
    ensure_external_schema_ready,
    ensure_external_tables_once,
    open_sqlite_connection,
    resolve_news_cache_db_path,
)
from backend.app.utils.logger import logger


class ExternalEvidenceCache:
    """Thread-safe SQLite response cache stored additively in news_cache.db."""

    def __init__(self, db_path: Optional[str] = None, ttl_hours: Optional[int] = None):
        self.db_path = resolve_news_cache_db_path(db_path)
        settings = get_settings()
        default_ttl = int(getattr(settings, "EXTERNAL_CACHE_TTL_HOURS", 24))
        self.ttl_hours = int(ttl_hours if ttl_hours is not None else default_ttl)

    @staticmethod
    def normalize_query(query: str) -> str:
        clean = re.sub(r"\s+", " ", (query or "").strip().lower())
        return clean.strip(" .,;:\"'")

    @classmethod
    def make_cache_key(cls, provider: str, query: str) -> Tuple[str, str]:
        norm = cls.normalize_query(query)
        digest = hashlib.sha256(f"{provider.strip().lower()}:{norm}".encode("utf-8")).hexdigest()
        return digest, norm

    def get(self, provider: str, query: str) -> Optional[Dict[str, Any]]:
        """
        Read-first cache lookup: queries SQLite using a shared read lock on cache misses
        so reads never contend for write locks, and acquires a brief write transaction
        only to purge expired entries or increment cache-hit / GDELT cache_hits counters.
        """
        cache_key, _ = self.make_cache_key(provider, query)
        now_dt = datetime.now(timezone.utc)
        default_limit = int(get_settings().GDELT_REQUEST_LIMIT)
        conn: Optional[sqlite3.Connection] = None
        try:
            ensure_external_schema_ready(self.db_path, default_limit=default_limit)
            conn = open_sqlite_connection(self.db_path, transactional=False)
            row = conn.execute(
                "SELECT response_json, expires_at FROM external_evidence_cache WHERE cache_key = ?;",
                (cache_key,),
            ).fetchone()
            if not row:
                return None

            exp_dt = datetime.fromisoformat(row["expires_at"])
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            if exp_dt <= now_dt:
                conn.close()
                conn = open_sqlite_connection(self.db_path, transactional=True)
                conn.execute("BEGIN IMMEDIATE;")
                conn.execute("DELETE FROM external_evidence_cache WHERE cache_key = ?;", (cache_key,))
                conn.commit()
                return None

            payload = json.loads(row["response_json"])
            conn.close()
            conn = open_sqlite_connection(self.db_path, transactional=True)
            conn.execute("BEGIN IMMEDIATE;")
            conn.execute(
                "UPDATE external_evidence_cache SET hit_count = hit_count + 1 WHERE cache_key = ?;",
                (cache_key,),
            )
            if provider == "gdelt":
                conn.execute(
                    "UPDATE gdelt_usage_state SET cache_hits = cache_hits + 1, updated_at = ? WHERE id = 1;",
                    (now_dt.isoformat(),),
                )
            conn.commit()
            return payload
        except (sqlite3.Error, ValueError, OSError) as exc:
            logger.warning(f"External cache read error ({provider}): {exc}")
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass
            return None
        finally:
            if conn is not None:
                conn.close()

    def set(self, provider: str, query: str, payload: Dict[str, Any], ttl_hours: Optional[int] = None) -> None:
        """Persists a normalized external response payload with explicit expiration."""
        cache_key, norm_query = self.make_cache_key(provider, query)
        now_dt = datetime.now(timezone.utc)
        effective_ttl = max(1, int(ttl_hours if ttl_hours is not None else self.ttl_hours))
        exp_dt = now_dt + timedelta(hours=effective_ttl)
        conn: Optional[sqlite3.Connection] = None
        try:
            conn = open_sqlite_connection(self.db_path, transactional=True)
            conn.execute("BEGIN IMMEDIATE;")
            ensure_external_tables_once(conn, self.db_path, default_limit=int(get_settings().GDELT_REQUEST_LIMIT))
            conn.execute(
                """
                INSERT INTO external_evidence_cache (
                    cache_key, provider, normalized_query, response_json, fetched_at, expires_at, hit_count
                ) VALUES (?, ?, ?, ?, ?, ?, 0)
                ON CONFLICT(cache_key) DO UPDATE SET
                    normalized_query = excluded.normalized_query,
                    response_json = excluded.response_json,
                    fetched_at = excluded.fetched_at,
                    expires_at = excluded.expires_at;
                """,
                (
                    cache_key,
                    provider,
                    norm_query,
                    json.dumps(payload),
                    now_dt.isoformat(),
                    exp_dt.isoformat(),
                ),
            )
            conn.commit()
        except (sqlite3.Error, ValueError, OSError) as exc:
            logger.warning(f"External cache write error ({provider}): {exc}")
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass
        finally:
            if conn is not None:
                conn.close()
