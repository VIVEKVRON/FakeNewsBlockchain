"""
Shared GDELT DOC 2.0 HTTP gateway enforcing the application-wide 200-request quota
and SQLite response caching across verification pipelines and Live News Monitor.

Important Epistemological Notice:
  - GDELT DOC 2.0 is a global news coverage discovery engine (article metadata/headlines only).
  - Article volume, tone, sentiment, or syndication count MUST NEVER be treated as truth proof.
  - Strictly uses the shared GdeltUsageTracker before every outbound request and fails closed on
    database unavailability or quota exhaustion.
"""

import math
import re
import threading
import time
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import requests

from backend.app.config import get_settings, validate_gdelt_timespan
from backend.app.services.external_apis.evidence_cache import ExternalEvidenceCache
from backend.app.services.external_apis.gdelt_usage_tracker import GdeltUsageStatus, GdeltUsageTracker
from backend.app.services.external_apis.quota_db import sanitize_secret_text, validate_external_http_url
from backend.app.utils.logger import logger


GDELT_DOC_ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"


def normalize_article_url(raw_url: str) -> str:
    """Strips tracking query params and fragments for canonical URL deduplication."""
    try:
        parsed = urllib.parse.urlparse(raw_url.strip())
        qs = urllib.parse.parse_qsl(parsed.query)
        tracking = {
            "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
            "at_medium", "at_campaign", "fbclid", "gclid", "ref", "source"
        }
        filtered = [(k, v) for k, v in qs if k.lower() not in tracking]
        return urllib.parse.urlunparse((
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path.rstrip("/"),
            parsed.params,
            urllib.parse.urlencode(filtered),
            "",
        ))
    except Exception:
        return raw_url.strip()


@dataclass
class GdeltArticleItem:
    title: str
    url: str
    domain: str
    published_at: Optional[str]
    language: Optional[str]
    source_country: Optional[str]
    search_query: str
    search_window: str
    retrieved_at: str
    syndicated_count: int = 1
    claim_id: Optional[str] = None


@dataclass
class GdeltSearchResult:
    status: str  # ok, ok_cached, no_results, disabled, quota_exhausted, tracker_unavailable, connect_timeout, read_timeout, timeout, invalid_timespan, rate_limited, http_error, invalid_response, network_error
    articles: List[GdeltArticleItem] = field(default_factory=list)
    query: str = ""
    search_window: str = "1month"
    raw_count: int = 0
    duplicates_collapsed: int = 0
    from_cache: bool = False
    usage: Optional[GdeltUsageStatus] = None
    retrieved_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    error_detail: Optional[str] = None


class GdeltClient:
    """
    Central gateway for all GDELT DOC 2.0 requests (`ArtList` JSON mode).
    Never receives Google API credentials and never bypasses `GdeltUsageTracker`.
    """

    def __init__(
        self,
        tracker: Optional[GdeltUsageTracker] = None,
        cache: Optional[ExternalEvidenceCache] = None,
        session: Optional[requests.Session] = None,
    ):
        self.tracker = tracker or GdeltUsageTracker()
        self.cache = cache or ExternalEvidenceCache()
        self._explicit_session = session is not None
        self._session = session or requests.Session()
        self._session.headers.update({"User-Agent": "FakeNewsBlockchain/1.0 (gdelt-doc-discovery)"})
        self._default_session_get = getattr(self._session, "get", None)
        self._thread_local = threading.local()

    def _get_session(self) -> Any:
        """Uses injected/mocked session when provided or patched, else a thread-local Session."""
        if self._explicit_session or getattr(self._session, "get", None) != self._default_session_get:
            return self._session
        sess = getattr(self._thread_local, "session", None)
        if sess is None:
            sess = requests.Session()
            sess.headers.update({"User-Agent": "FakeNewsBlockchain/1.0 (gdelt-doc-discovery)"})
            self._thread_local.session = sess
        return sess

    @staticmethod
    def _parse_and_dedupe_articles(
        payload: Dict[str, Any],
        *,
        search_query: str,
        search_window: str,
        retrieved_at: str,
        max_records: int,
    ) -> Tuple[List[GdeltArticleItem], int, int]:
        raw_list = payload.get("articles")
        if not isinstance(raw_list, list):
            return [], 0, 0

        deduped: List[GdeltArticleItem] = []
        seen_urls: Dict[str, int] = {}
        seen_titles: Dict[str, int] = {}
        duplicates = 0

        for entry in raw_list:
            if not isinstance(entry, dict):
                continue
            raw_url = entry.get("url")
            valid_url = validate_external_http_url(raw_url)
            title = str(entry.get("title") or "").strip()
            if not valid_url or not title:
                continue

            canon_url = normalize_article_url(valid_url)
            title_sig = re.sub(r"\W+", "", title.lower())[:90]

            if canon_url in seen_urls:
                duplicates += 1
                idx = seen_urls[canon_url]
                deduped[idx].syndicated_count += 1
                continue
            if title_sig and title_sig in seen_titles:
                duplicates += 1
                idx = seen_titles[title_sig]
                deduped[idx].syndicated_count += 1
                continue

            domain = str(entry.get("domain") or "").strip()
            if not domain:
                domain = (urllib.parse.urlparse(canon_url).hostname or "gdelt-source").lower()

            seendate = entry.get("seendate") or entry.get("publishdate")
            pub_date = str(seendate).strip() if seendate else None
            lang = str(entry.get("language")).strip() if entry.get("language") else None
            country = str(entry.get("sourcecountry")).strip() if entry.get("sourcecountry") else None

            idx = len(deduped)
            seen_urls[canon_url] = idx
            if title_sig:
                seen_titles[title_sig] = idx

            deduped.append(
                GdeltArticleItem(
                    title=title,
                    url=canon_url,
                    domain=domain,
                    published_at=pub_date,
                    language=lang,
                    source_country=country,
                    search_query=search_query,
                    search_window=search_window,
                    retrieved_at=retrieved_at,
                    syndicated_count=1,
                )
            )
            if len(deduped) >= max_records:
                # Continue counting duplicates in remaining raw_list accurately
                pass

        return deduped[:max_records], len(raw_list), duplicates

    @staticmethod
    def _resolve_timeouts(settings: Any) -> Tuple[float, float]:
        connect_raw = getattr(settings, "GDELT_CONNECT_TIMEOUT_SEC", 8.0)
        read_raw = getattr(settings, "GDELT_TIMEOUT_SEC", 12.0)
        try:
            connect_t = float(connect_raw)
            read_t = float(read_raw)
        except (TypeError, ValueError) as exc:
            raise ValueError("GDELT timeout settings must be numeric values in (0.0, 60.0] seconds.") from exc
        if not math.isfinite(connect_t) or connect_t <= 0.0 or connect_t > 60.0:
            raise ValueError(f"Invalid GDELT_CONNECT_TIMEOUT_SEC={connect_t}; must be in (0.0, 60.0] seconds.")
        if not math.isfinite(read_t) or read_t <= 0.0 or read_t > 60.0:
            raise ValueError(f"Invalid GDELT_TIMEOUT_SEC={read_t}; must be in (0.0, 60.0] seconds.")
        return connect_t, read_t

    def _execute_query(
        self,
        *,
        params: Dict[str, Any],
        cache_key_query: str,
        display_query: str,
        search_window: str,
        max_records: int,
        source_label: str,
        max_retries: Optional[int] = None,
    ) -> GdeltSearchResult:
        settings = get_settings()
        now_iso = datetime.now(timezone.utc).isoformat()

        if not bool(getattr(settings, "GDELT_ENABLED", True)):
            return GdeltSearchResult(
                status="disabled",
                query=display_query,
                search_window=search_window,
                usage=self.tracker.get_status(),
                retrieved_at=now_iso,
                error_detail="GDELT integration is disabled via configuration (GDELT_ENABLED=false).",
            )

        # Fail closed cleanly if DB/tracker unavailable BEFORE even relying on unverified state
        pre_status = self.tracker.get_status()
        if not pre_status.tracker_available:
            return GdeltSearchResult(
                status="tracker_unavailable",
                query=display_query,
                search_window=search_window,
                usage=pre_status,
                retrieved_at=now_iso,
                error_detail="Shared GDELT quota database is unavailable; request blocked fail-closed.",
            )

        # 1. Check cache FIRST (cache hits do NOT consume quota!)
        cached = self.cache.get("gdelt", cache_key_query)
        if cached is not None:
            cached_ts = cached.get("retrieved_at") or now_iso
            items, raw_cnt, dupes = self._parse_and_dedupe_articles(
                cached,
                search_query=display_query,
                search_window=search_window,
                retrieved_at=cached_ts,
                max_records=max_records,
            )
            return GdeltSearchResult(
                status="ok_cached" if items else "no_results",
                articles=items,
                query=display_query,
                search_window=search_window,
                raw_count=raw_cnt,
                duplicates_collapsed=dupes,
                from_cache=True,
                usage=self.tracker.get_status(),
                retrieved_at=cached_ts,
            )

        # Ensure Google Fact Check key is NEVER included in GDELT parameters
        safe_params = {k: v for k, v in params.items() if "key" not in k.lower()}
        connect_timeout, read_timeout = self._resolve_timeouts(settings)
        retries = int(getattr(settings, "GDELT_MAX_RETRIES", 0) if max_retries is None else max_retries)
        if retries < 0 or retries > 2:
            raise ValueError(f"Invalid GDELT_MAX_RETRIES={retries}; must be between 0 and 2.")
        max_attempts = 1 + retries

        last_status = "network_error"
        last_error = ""
        usage = pre_status
        parsed_data: Optional[Dict[str, Any]] = None

        sess = self._get_session()
        for attempt in range(max_attempts):
            # Reserve slot atomically BEFORE every outbound HTTP attempt
            allowed, usage = self.tracker.reserve_request_slot(source=source_label)
            if not allowed:
                status_flag = "tracker_unavailable" if not usage.tracker_available else "quota_exhausted"
                return GdeltSearchResult(
                    status=status_flag,
                    query=display_query,
                    search_window=search_window,
                    usage=usage,
                    retrieved_at=now_iso,
                    error_detail=last_error or f"GDELT request blocked ({status_flag}).",
                )

            try:
                resp = sess.get(
                    GDELT_DOC_ENDPOINT,
                    params=safe_params,
                    timeout=(connect_timeout, read_timeout),
                )
                if resp.status_code == 429:
                    last_error = "GDELT API returned HTTP 429 (Too Many Requests)."
                    self.tracker.record_request_outcome(source_label, "http_429_rate_limited", failed=True)
                    return GdeltSearchResult(
                        status="rate_limited",
                        query=display_query,
                        search_window=search_window,
                        usage=self.tracker.get_status(),
                        retrieved_at=now_iso,
                        error_detail=last_error,
                    )

                if resp.status_code >= 500:
                    last_status = "http_error"
                    last_error = f"GDELT API server error (HTTP {resp.status_code})."
                    self.tracker.record_request_outcome(source_label, f"http_{resp.status_code}", failed=True)
                    if attempt + 1 < max_attempts:
                        time.sleep(0.4 * (attempt + 1))
                        continue
                    return GdeltSearchResult(
                        status="http_error",
                        query=display_query,
                        search_window=search_window,
                        usage=self.tracker.get_status(),
                        retrieved_at=now_iso,
                        error_detail=last_error,
                    )

                if not resp.ok:
                    last_error = f"GDELT API returned HTTP {resp.status_code}."
                    self.tracker.record_request_outcome(source_label, f"http_{resp.status_code}", failed=True)
                    return GdeltSearchResult(
                        status="http_error",
                        query=display_query,
                        search_window=search_window,
                        usage=self.tracker.get_status(),
                        retrieved_at=now_iso,
                        error_detail=last_error,
                    )

                raw_json = resp.json()
                if not isinstance(raw_json, dict):
                    self.tracker.record_request_outcome(source_label, "invalid_json_type", failed=True)
                    return GdeltSearchResult(
                        status="invalid_response",
                        query=display_query,
                        search_window=search_window,
                        usage=self.tracker.get_status(),
                        retrieved_at=now_iso,
                        error_detail="Malformed JSON object returned by GDELT DOC 2.0.",
                    )
                parsed_data = raw_json
                self.tracker.record_request_outcome(source_label, "ok", failed=False)
                break

            except requests.ConnectTimeout:
                last_error = f"GDELT connection/TLS timed out after {connect_timeout:.1f}s."
                self.tracker.record_request_outcome(source_label, "connect_timeout", failed=True)
                return GdeltSearchResult(
                    status="connect_timeout",
                    query=display_query,
                    search_window=search_window,
                    usage=self.tracker.get_status(),
                    retrieved_at=now_iso,
                    error_detail=last_error,
                )
            except requests.ReadTimeout:
                last_error = f"GDELT response read timed out after {read_timeout:.1f}s."
                self.tracker.record_request_outcome(source_label, "read_timeout", failed=True)
                return GdeltSearchResult(
                    status="read_timeout",
                    query=display_query,
                    search_window=search_window,
                    usage=self.tracker.get_status(),
                    retrieved_at=now_iso,
                    error_detail=last_error,
                )
            except requests.Timeout:
                last_error = "GDELT request timed out."
                self.tracker.record_request_outcome(source_label, "timeout", failed=True)
                return GdeltSearchResult(
                    status="timeout",
                    query=display_query,
                    search_window=search_window,
                    usage=self.tracker.get_status(),
                    retrieved_at=now_iso,
                    error_detail=last_error,
                )
            except requests.RequestException as exc:
                last_error = sanitize_secret_text(f"GDELT request failed: {type(exc).__name__}.")
                self.tracker.record_request_outcome(source_label, "network_error", failed=True)
                return GdeltSearchResult(
                    status="network_error",
                    query=display_query,
                    search_window=search_window,
                    usage=self.tracker.get_status(),
                    retrieved_at=now_iso,
                    error_detail=last_error,
                )
            except ValueError:
                self.tracker.record_request_outcome(source_label, "malformed_json", failed=True)
                return GdeltSearchResult(
                    status="invalid_response",
                    query=display_query,
                    search_window=search_window,
                    usage=self.tracker.get_status(),
                    retrieved_at=now_iso,
                    error_detail="Malformed JSON returned by GDELT DOC 2.0.",
                )

        if parsed_data is None:
            return GdeltSearchResult(
                status=last_status,
                query=display_query,
                search_window=search_window,
                usage=self.tracker.get_status(),
                retrieved_at=now_iso,
                error_detail=last_error,
            )

        cache_payload = dict(parsed_data)
        cache_payload["retrieved_at"] = now_iso
        self.cache.set("gdelt", cache_key_query, cache_payload)

        items, raw_cnt, dupes = self._parse_and_dedupe_articles(
            parsed_data,
            search_query=display_query,
            search_window=search_window,
            retrieved_at=now_iso,
            max_records=max_records,
        )
        return GdeltSearchResult(
            status="ok" if items else "no_results",
            articles=items,
            query=display_query,
            search_window=search_window,
            raw_count=raw_cnt,
            duplicates_collapsed=dupes,
            from_cache=False,
            usage=self.tracker.get_status(),
            retrieved_at=now_iso,
        )

    def search_coverage(
        self,
        query: str,
        *,
        max_records: Optional[int] = None,
        timespan: Optional[str] = None,
        source_label: str = "verification",
        max_retries: Optional[int] = None,
    ) -> GdeltSearchResult:
        """Searches GDELT DOC 2.0 `ArtList` for English coverage matching focused claim query."""
        settings = get_settings()
        limit_rec = max(1, min(25, int(max_records or getattr(settings, "GDELT_MAX_RECORDS", 10))))
        clean_q = re.sub(r"\s+", " ", (query or "").strip())
        if not clean_q:
            return GdeltSearchResult(status="empty_query", usage=self.tracker.get_status())

        raw_ts = timespan if timespan is not None else getattr(settings, "GDELT_DEFAULT_TIMESPAN", "1month")
        try:
            validated_ts = validate_gdelt_timespan(raw_ts)
        except ValueError as exc:
            return GdeltSearchResult(
                status="invalid_timespan",
                query=clean_q,
                search_window=str(raw_ts),
                usage=self.tracker.get_status(),
                error_detail=str(exc),
            )

        params = {
            "query": f"{clean_q} sourcelang:eng",
            "mode": "ArtList",
            "maxrecords": limit_rec,
            "timespan": validated_ts,
            "sort": "DateDesc",
            "format": "json",
        }
        cache_key = f"artlist:{validated_ts}:{limit_rec}:{clean_q}"
        return self._execute_query(
            params=params,
            cache_key_query=cache_key,
            display_query=clean_q,
            search_window=validated_ts,
            max_records=limit_rec,
            source_label=source_label,
            max_retries=max_retries,
        )

    def fetch_feed_articles(
        self,
        feed_url: str,
        *,
        source_label: str = "news_refresh",
        max_retries: Optional[int] = None,
    ) -> GdeltSearchResult:
        """
        Shared gateway replacement for Live News Monitor's GDELT feed polling.
        Parses query parameters from configured feed URL and routes through the shared tracker + cache.
        """
        parsed = urllib.parse.urlparse((feed_url or "").strip())
        if (parsed.hostname or "").lower() != "api.gdeltproject.org":
            return GdeltSearchResult(
                status="invalid_feed_url",
                query=feed_url,
                usage=self.tracker.get_status(),
                error_detail="GDELT feed URL hostname rejected.",
            )

        raw_qs = dict(urllib.parse.parse_qsl(parsed.query))
        q_str = raw_qs.get("query", "sourcelang:eng")
        max_rec = max(1, min(50, int(raw_qs.get("maxrecords", 25))))
        raw_ts = raw_qs.get("timespan", "3days")
        try:
            timespan = validate_gdelt_timespan(raw_ts)
        except ValueError as exc:
            return GdeltSearchResult(
                status="invalid_timespan",
                query=q_str,
                search_window=str(raw_ts),
                usage=self.tracker.get_status(),
                error_detail=str(exc),
            )

        params = {
            "query": q_str,
            "mode": raw_qs.get("mode", "ArtList"),
            "maxrecords": max_rec,
            "timespan": timespan,
            "format": "json",
        }
        cache_key = f"feed:{timespan}:{max_rec}:{q_str}"
        return self._execute_query(
            params=params,
            cache_key_query=cache_key,
            display_query=q_str,
            search_window=f"{timespan} (rolling)",
            max_records=max_rec,
            source_label=source_label,
            max_retries=max_retries,
        )
