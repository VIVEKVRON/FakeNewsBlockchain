"""
Persistent, concurrency-safe shared GDELT request quota tracker backed by SQLite (data/news_cache.db).

Accounting Policy:
  - Hard application allowance defaults to GDELT_REQUEST_LIMIT (200) across ALL endpoints
    (Live News refresh, text claim verification, and article verification share row id=1).
  - Counts every atomic pre-flight reservation (`requests_used += 1`) inside a SQLite
    `BEGIN IMMEDIATE` transaction BEFORE any outbound HTTP request leaves the application.
  - Failed provider attempts (timeouts, HTTP 429/5xx, malformed JSON) remain counted and are
    NEVER silently refunded after leaving the host.
  - Cache hits (`external_evidence_cache`) never call `reserve_request_slot()` and never consume quota.
  - Fail-closed rule: if the SQLite tracker cannot be opened or locked, outbound GDELT calls are blocked.
"""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from backend.app.config import get_settings
from backend.app.services.external_apis.quota_db import (
    ensure_external_tables_once,
    open_sqlite_connection,
    resolve_news_cache_db_path,
)
from backend.app.utils.logger import logger

ACCOUNTING_RULE = (
    "Counts reserved/attempted outbound GDELT provider HTTP requests across all routes "
    "(Live News, Text Verify, Article Verify). Slots are reserved atomically before each outbound "
    "request and never refunded on provider error; cache hits do not consume quota."
)


@dataclass
class GdeltUsageStatus:
    enabled: bool
    allowance_limit: int
    requests_used: int
    requests_remaining: int
    warning_threshold: int
    warning_active: bool
    limit_reached: bool
    cache_hits: int
    failed_requests: int
    last_request_at: Optional[str]
    last_source: Optional[str]
    last_status: Optional[str]
    tracker_available: bool
    accounting_rule: str = ACCOUNTING_RULE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "allowance_limit": self.allowance_limit,
            "requests_used": self.requests_used,
            "requests_remaining": self.requests_remaining,
            "warning_threshold": self.warning_threshold,
            "warning_active": self.warning_active,
            "limit_reached": self.limit_reached,
            "cache_hits": self.cache_hits,
            "failed_requests": self.failed_requests,
            "last_request_at": self.last_request_at,
            "last_source": self.last_source,
            "last_status": self.last_status,
            "tracker_available": self.tracker_available,
            "accounting_rule": self.accounting_rule,
        }


class GdeltUsageTracker:
    """Atomic, fail-closed SQLite counter governing the 200-request GDELT hard cap."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = resolve_news_cache_db_path(db_path)

    def ensure_schema(self) -> bool:
        """Initializes additive GDELT/cache SQLite tables cleanly once during startup."""
        limit = max(0, int(getattr(get_settings(), "GDELT_REQUEST_LIMIT", 200)))
        conn: Optional[sqlite3.Connection] = None
        try:
            conn = open_sqlite_connection(self.db_path, transactional=True)
            conn.execute("BEGIN IMMEDIATE;")
            ensure_external_tables_once(conn, self.db_path, default_limit=limit)
            conn.commit()
            return True
        except (sqlite3.Error, OSError) as exc:
            logger.warning(f"Could not pre-initialize GDELT SQLite schema: {exc}")
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass
            return False
        finally:
            if conn is not None:
                conn.close()

    def _build_status(
        self,
        *,
        requests_used: int,
        cache_hits: int,
        failed_requests: int,
        last_request_at: Optional[str],
        last_source: Optional[str],
        last_status: Optional[str],
        tracker_available: bool,
    ) -> GdeltUsageStatus:
        settings = get_settings()
        enabled = bool(getattr(settings, "GDELT_ENABLED", True))
        limit = max(0, int(getattr(settings, "GDELT_REQUEST_LIMIT", 200)))
        warn_thresh = max(0, int(getattr(settings, "GDELT_WARNING_THRESHOLD", 20)))
        remaining = max(0, limit - requests_used) if tracker_available else 0
        limit_reached = (not tracker_available) or (requests_used >= limit)
        warning_active = tracker_available and (remaining <= warn_thresh)
        return GdeltUsageStatus(
            enabled=enabled,
            allowance_limit=limit,
            requests_used=requests_used,
            requests_remaining=remaining,
            warning_threshold=warn_thresh,
            warning_active=warning_active,
            limit_reached=limit_reached,
            cache_hits=cache_hits,
            failed_requests=failed_requests,
            last_request_at=last_request_at,
            last_source=last_source,
            last_status=last_status,
            tracker_available=tracker_available,
        )

    def _unavailable_status(self, reason: str) -> GdeltUsageStatus:
        return self._build_status(
            requests_used=0,
            cache_hits=0,
            failed_requests=0,
            last_request_at=None,
            last_source=None,
            last_status=reason,
            tracker_available=False,
        )

    def get_status(self) -> GdeltUsageStatus:
        """Read-only inspection of persistent GDELT usage state (never mutates requests_used)."""
        settings = get_settings()
        limit = max(0, int(getattr(settings, "GDELT_REQUEST_LIMIT", 200)))
        conn: Optional[sqlite3.Connection] = None
        try:
            conn = open_sqlite_connection(self.db_path, transactional=True)
            conn.execute("BEGIN IMMEDIATE;")
            ensure_external_tables_once(conn, self.db_path, default_limit=limit)
            row = conn.execute("SELECT * FROM gdelt_usage_state WHERE id = 1;").fetchone()
            conn.commit()
            if not row:
                return self._unavailable_status("tracker_row_missing")
            return self._build_status(
                requests_used=int(row["requests_used"]),
                cache_hits=int(row["cache_hits"]),
                failed_requests=int(row["failed_requests"]),
                last_request_at=row["last_request_at"],
                last_source=row["last_source"],
                last_status=row["last_status"],
                tracker_available=True,
            )
        except (sqlite3.Error, OSError) as exc:
            logger.error(f"GDELT quota tracker unavailable (fail closed): {exc}")
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass
            return self._unavailable_status("tracker_unavailable")
        finally:
            if conn is not None:
                conn.close()

    def reserve_request_slot(self, source: str) -> Tuple[bool, GdeltUsageStatus]:
        """
        Atomically reserves 1 GDELT request slot BEFORE sending an external HTTP request.
        Returns (True, updated_status) if permitted, or (False, status) when exhausted,
        disabled, or tracker DB fails (fail closed).
        """
        settings = get_settings()
        if not bool(getattr(settings, "GDELT_ENABLED", True)):
            st = self.get_status()
            return False, st

        limit = max(0, int(getattr(settings, "GDELT_REQUEST_LIMIT", 200)))
        now_iso = datetime.now(timezone.utc).isoformat()
        conn: Optional[sqlite3.Connection] = None
        try:
            conn = open_sqlite_connection(self.db_path, transactional=True)
            conn.execute("BEGIN IMMEDIATE;")
            ensure_external_tables_once(conn, self.db_path, default_limit=limit)

            cur = conn.execute(
                """
                UPDATE gdelt_usage_state
                SET requests_used = requests_used + 1,
                    allowance_limit = ?,
                    last_request_at = ?,
                    last_source = ?,
                    last_status = 'reserved',
                    updated_at = ?
                WHERE id = 1 AND requests_used < ?;
                """,
                (limit, now_iso, source, now_iso, limit),
            )
            reserved = cur.rowcount == 1
            if not reserved:
                conn.execute(
                    """
                    UPDATE gdelt_usage_state
                    SET allowance_limit = ?,
                        last_source = ?,
                        last_status = 'limit_reached_blocked',
                        updated_at = ?
                    WHERE id = 1;
                    """,
                    (limit, source, now_iso),
                )
            row = conn.execute("SELECT * FROM gdelt_usage_state WHERE id = 1;").fetchone()
            conn.commit()
            if not row:
                return False, self._unavailable_status("tracker_row_missing")
            status_obj = self._build_status(
                requests_used=int(row["requests_used"]),
                cache_hits=int(row["cache_hits"]),
                failed_requests=int(row["failed_requests"]),
                last_request_at=row["last_request_at"],
                last_source=row["last_source"],
                last_status=row["last_status"],
                tracker_available=True,
            )
            if reserved and status_obj.warning_active:
                logger.warning(
                    f"GDELT quota warning: {status_obj.requests_used}/{status_obj.allowance_limit} used "
                    f"({status_obj.requests_remaining} remaining)."
                )
            elif not reserved:
                logger.warning(
                    f"GDELT request BLOCKED for '{source}': allowance limit {limit} reached ({status_obj.requests_used}/{limit})."
                )
            return reserved, status_obj
        except (sqlite3.Error, OSError) as exc:
            logger.error(f"GDELT atomic reservation failed (fail closed): {exc}")
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass
            return False, self._unavailable_status("tracker_unavailable")
        finally:
            if conn is not None:
                conn.close()

    def record_request_outcome(self, source: str, status_msg: str, failed: bool = False) -> None:
        """
        Updates outcome metadata for an already-reserved request.
        Never decrements or refunds `requests_used`.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        conn: Optional[sqlite3.Connection] = None
        try:
            conn = open_sqlite_connection(self.db_path, transactional=True)
            conn.execute("BEGIN IMMEDIATE;")
            ensure_external_tables_once(conn, self.db_path, default_limit=int(get_settings().GDELT_REQUEST_LIMIT))
            conn.execute(
                """
                UPDATE gdelt_usage_state
                SET failed_requests = failed_requests + ?,
                    last_source = ?,
                    last_status = ?,
                    updated_at = ?
                WHERE id = 1;
                """,
                (1 if failed else 0, source, status_msg[:120], now_iso),
            )
            conn.commit()
        except (sqlite3.Error, OSError) as exc:
            logger.warning(f"GDELT outcome update failed (count remains intact): {exc}")
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass
        finally:
            if conn is not None:
                conn.close()
