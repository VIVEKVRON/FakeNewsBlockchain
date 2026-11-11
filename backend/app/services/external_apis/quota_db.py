"""
Shared SQLite helpers, additive schema initialization, secret-scrubbing utilities,
and static SSRF URL validation for Group E external APIs.
"""

import ipaddress
import os
import re
import sqlite3
import threading
import urllib.parse
from datetime import datetime, timezone
from typing import Optional, Set, Tuple

from backend.app.config import get_settings

_SCHEMA_INIT_LOCK = threading.Lock()
_INITIALIZED_SCHEMA_KEYS: Set[Tuple[str, int, int]] = set()


def resolve_news_cache_db_path(db_path: Optional[str] = None) -> str:
    """Resolves path to the shared SQLite cache & quota DB (default: data/news_cache.db)."""
    if db_path:
        return db_path
    override_path = os.environ.get("FAKE_NEWS_TEST_NEWS_DB", "").strip()
    if override_path:
        return override_path
    settings = get_settings()
    return str((settings.PROJECT_ROOT / "data" / "news_cache.db").resolve())


def open_sqlite_connection(db_path: str, transactional: bool = False) -> sqlite3.Connection:
    """Opens a hardened SQLite connection with busy timeout."""
    parent = os.path.dirname(os.path.abspath(db_path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    isolation = None if transactional else ""
    conn = sqlite3.connect(db_path, timeout=10.0, isolation_level=isolation, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn


def ensure_external_tables(conn: sqlite3.Connection, default_limit: int = 200) -> None:
    """
    Idempotent additive migration inside data/news_cache.db.
    Never modifies existing news_articles/news_sources tables or resets requests_used.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS gdelt_usage_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            allowance_limit INTEGER NOT NULL DEFAULT 200,
            requests_used INTEGER NOT NULL DEFAULT 0,
            cache_hits INTEGER NOT NULL DEFAULT 0,
            failed_requests INTEGER NOT NULL DEFAULT 0,
            last_request_at TEXT,
            last_source TEXT,
            last_status TEXT,
            updated_at TEXT NOT NULL
        );
        """
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO gdelt_usage_state (
            id, allowance_limit, requests_used, cache_hits, failed_requests, updated_at
        ) VALUES (1, ?, 0, 0, 0, ?);
        """,
        (int(default_limit), now_iso),
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS external_evidence_cache (
            cache_key TEXT PRIMARY KEY,
            provider TEXT NOT NULL,
            normalized_query TEXT NOT NULL,
            response_json TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            hit_count INTEGER NOT NULL DEFAULT 0
        );
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ext_cache_provider_exp ON external_evidence_cache(provider, expires_at);"
    )


def _schema_cache_key(db_path: str, default_limit: int) -> Tuple[str, int, int]:
    abs_path = os.path.abspath(db_path)
    try:
        st = os.stat(abs_path)
        ino = int(st.st_ino) if st.st_ino and st.st_size > 0 else -1
    except OSError:
        ino = -1
    return (abs_path, ino, int(default_limit))


def invalidate_schema_cache_for_db(db_path: str) -> None:
    abs_path = os.path.abspath(db_path)
    with _SCHEMA_INIT_LOCK:
        stale = [k for k in _INITIALIZED_SCHEMA_KEYS if k[0] == abs_path]
        for k in stale:
            _INITIALIZED_SCHEMA_KEYS.discard(k)


def ensure_external_tables_once(
    conn: sqlite3.Connection,
    db_path: str,
    default_limit: int = 200,
) -> None:
    """
    Runs idempotent additive table creation once per live SQLite file inode/limit
    to avoid repeating CREATE TABLE/INSERT DDL on every quota or cache operation.
    Ensures DDL is committed before caching initialization state.
    """
    key = _schema_cache_key(db_path, default_limit)
    if key[1] != -1:
        with _SCHEMA_INIT_LOCK:
            if key in _INITIALIZED_SCHEMA_KEYS:
                return
    ensure_external_tables(conn, default_limit=default_limit)
    if conn.isolation_level is not None and conn.in_transaction:
        conn.commit()
    key_after = _schema_cache_key(db_path, default_limit)
    if key_after[1] != -1:
        with _SCHEMA_INIT_LOCK:
            _INITIALIZED_SCHEMA_KEYS.add(key_after)


def ensure_external_schema_ready(db_path: str, default_limit: int = 200) -> None:
    """Fast O(1) check ensuring tables/seed row exist and are committed before read-only access."""
    key = _schema_cache_key(db_path, default_limit)
    if key[1] != -1:
        with _SCHEMA_INIT_LOCK:
            if key in _INITIALIZED_SCHEMA_KEYS:
                return
    conn = open_sqlite_connection(db_path, transactional=True)
    try:
        conn.execute("BEGIN IMMEDIATE;")
        ensure_external_tables(conn, default_limit=default_limit)
        conn.commit()
        key_after = _schema_cache_key(db_path, default_limit)
        if key_after[1] != -1:
            with _SCHEMA_INIT_LOCK:
                _INITIALIZED_SCHEMA_KEYS.add(key_after)
    finally:
        conn.close()


def sanitize_secret_text(text: str, secret: str = "") -> str:
    """Removes Google API keys and query parameters before logging or returning error details."""
    if not text:
        return ""
    scrubbed = re.sub(r"([?&]|\b)(key=)[^&\s\"']+", r"\1\2[REDACTED]", str(text), flags=re.IGNORECASE)
    if secret and secret.strip():
        scrubbed = scrubbed.replace(secret.strip(), "[REDACTED]")
    try:
        cfg_key = (getattr(get_settings(), "GOOGLE_FACT_CHECK_API_KEY", "") or "").strip()
        if cfg_key:
            scrubbed = scrubbed.replace(cfg_key, "[REDACTED]")
    except Exception:
        pass
    return scrubbed


def validate_external_http_url(url: Optional[str]) -> Optional[str]:
    """
    Validates external review/article URLs strictly before persistence or display.
    Allows public http/https URLs; blocks non-HTTP schemes, localhost, loopback,
    link-local metadata, private IPv4/IPv6 ranges, and local hostnames.
    """
    if not url or not isinstance(url, str):
        return None
    raw = url.strip()
    if not raw or any(ch.isspace() for ch in raw):
        return None
    try:
        parsed = urllib.parse.urlparse(raw)
        if parsed.scheme.lower() not in ("http", "https"):
            return None
        hostname = (parsed.hostname or "").strip().lower()
        if not hostname:
            return None
        if hostname in ("localhost", "localhost.localdomain") or hostname.endswith((".local", ".internal", ".localhost")):
            return None
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local or ip.is_multicast or ip.is_unspecified:
                return None
        except ValueError:
            # Domain name: require at least one dot for standard public FQDN
            if "." not in hostname or hostname.startswith(".") or hostname.endswith("."):
                return None
        return raw
    except Exception:
        return None
