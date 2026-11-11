"""
Google Fact Check Tools API client (backend-only, read-only supplementary third-party ClaimReview lookup).

Important Epistemological Notice:
  - Google Fact Check Tools returns third-party fact-checking organization ClaimReviews.
  - Original publisher rating text is ALWAYS preserved verbatim and attributed to its publisher.
  - Missing ratings are NEVER inferred; missing/empty results NEVER imply GENUINE or FAKE.
  - API keys are strictly restricted to backend Settings and scrubbed from all logs/errors.
"""

import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import requests

from backend.app.config import get_settings
from backend.app.services.external_apis.evidence_cache import ExternalEvidenceCache
from backend.app.services.external_apis.quota_db import sanitize_secret_text, validate_external_http_url
from backend.app.utils.logger import logger


GOOGLE_FACT_CHECK_ENDPOINT = "https://factchecktools.googleapis.com/v1alpha1/claims:search"

_CURRENT_STATE_RE = re.compile(
    r"\b(current|currently|incumbent|presently|nowadays|sitting|reigning|today|remains)\b",
    re.IGNORECASE,
)


@dataclass
class FactCheckMatch:
    claim_text: Optional[str]
    review_title: Optional[str]
    publisher_name: Optional[str]
    publisher_site: Optional[str]
    reviewer_name: Optional[str]
    rating_text: Optional[str]
    review_url: Optional[str]
    review_publication_date: Optional[str]
    claim_appearance_date: Optional[str]
    original_claim_author: Optional[str]
    language_code: Optional[str]
    retrieved_at: str
    is_stale: bool = False
    stale_reason: Optional[str] = None
    is_conflicting: bool = False
    claim_id: Optional[str] = None


@dataclass
class GoogleFactCheckResult:
    status: str  # ok, ok_cached, no_results, unavailable_no_api_key, auth_error, rate_limited, timeout, http_error, invalid_response, network_error
    available: bool
    query: str
    matches: List[FactCheckMatch] = field(default_factory=list)
    has_conflicting_reviews: bool = False
    conflict_summary: Optional[str] = None
    has_stale_reviews: bool = False
    from_cache: bool = False
    retrieved_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    error_detail: Optional[str] = None


def _extract_iso_year(date_str: Optional[str]) -> Optional[int]:
    if not date_str:
        return None
    m = re.search(r"\b((?:19|20)\d{2})\b", str(date_str))
    return int(m.group(1)) if m else None


def _assess_rating_polarity_for_conflict_only(rating_text: Optional[str]) -> Optional[str]:
    """
    Lightweight helper ONLY to flag when multiple third-party publishers disagree with each other.
    Never converts publisher ratings into our six application verdicts.
    """
    if not rating_text:
        return None
    low = rating_text.strip().lower()
    if any(w in low for w in ("partly", "half", "mixed", "missing context", "misleading", "exaggerat", "mostly false", "mostly true")):
        return "mixed_or_misleading"
    if any(w in low for w in ("false", "fake", "incorrect", "pants on fire", "fabricated", "hoax", "untrue", "wrong")):
        return "negative"
    if any(w in low for w in ("true", "correct", "accurate", "verified")):
        return "positive"
    return None


def _check_stale_review(query: str, review_date: Optional[str], now_dt: Optional[datetime] = None) -> Tuple[bool, Optional[str]]:
    rev_year = _extract_iso_year(review_date)
    if rev_year is None:
        return False, None
    now = now_dt or datetime.now(timezone.utc)
    claim_years = [int(y) for y in re.findall(r"\b((?:19|20)\d{2})\b", query)]
    if claim_years and rev_year < max(claim_years):
        return True, f"Review dated {review_date} precedes claimed year {max(claim_years)}."
    if _CURRENT_STATE_RE.search(query) and (now.year - rev_year) >= 2:
        return True, f"Review dated {review_date} may be outdated for a present-tense assertion (current year: {now.year})."
    if (now.year - rev_year) >= 4:
        return True, f"Historical fact-check review ({review_date}) is over 4 years old."
    return False, None


class GoogleFactCheckClient:
    """Backend-only HTTP client for Google Fact Check Tools API with SQLite caching and safe key handling."""

    def __init__(
        self,
        cache: Optional[ExternalEvidenceCache] = None,
        session: Optional[requests.Session] = None,
    ):
        self.cache = cache or ExternalEvidenceCache()
        self._explicit_session = session is not None
        self._session = session or requests.Session()
        self._session.headers.update({"User-Agent": "FakeNewsBlockchain/1.0 (fact-check-research)"})
        self._default_session_get = getattr(self._session, "get", None)
        self._thread_local = threading.local()

    def _get_session(self) -> Any:
        """Uses injected/mocked session when provided or patched, else a thread-local Session."""
        if self._explicit_session or getattr(self._session, "get", None) != self._default_session_get:
            return self._session
        sess = getattr(self._thread_local, "session", None)
        if sess is None:
            sess = requests.Session()
            sess.headers.update({"User-Agent": "FakeNewsBlockchain/1.0 (fact-check-research)"})
            self._thread_local.session = sess
        return sess

    def _parse_claims_payload(
        self,
        query: str,
        payload: Dict[str, Any],
        retrieved_at: str,
    ) -> Tuple[List[FactCheckMatch], bool, Optional[str], bool]:
        claims = payload.get("claims")
        if not isinstance(claims, list):
            return [], False, None, False

        matches: List[FactCheckMatch] = []
        polarities = set()
        any_stale = False

        for claim_obj in claims:
            if not isinstance(claim_obj, dict):
                continue
            claim_text = claim_obj.get("text")
            claimant = claim_obj.get("claimant")
            claim_date = claim_obj.get("claimDate")
            reviews = claim_obj.get("claimReview") or []
            if not isinstance(reviews, list):
                continue

            for rev in reviews:
                if not isinstance(rev, dict):
                    continue
                pub = rev.get("publisher") if isinstance(rev.get("publisher"), dict) else {}
                raw_rating = rev.get("textualRating")
                rating_text = str(raw_rating).strip() if isinstance(raw_rating, str) and raw_rating.strip() else None
                review_url = validate_external_http_url(rev.get("url"))
                rev_date = rev.get("reviewDate")
                stale, stale_reason = _check_stale_review(query, rev_date)
                if stale:
                    any_stale = True

                pol = _assess_rating_polarity_for_conflict_only(rating_text)
                if pol:
                    polarities.add(pol)

                matches.append(
                    FactCheckMatch(
                        claim_text=claim_text,
                        review_title=rev.get("title"),
                        publisher_name=pub.get("name") or pub.get("site"),
                        publisher_site=pub.get("site"),
                        reviewer_name=rev.get("reviewerName"),
                        rating_text=rating_text,
                        review_url=review_url,
                        review_publication_date=rev_date,
                        claim_appearance_date=claim_date,
                        original_claim_author=claimant,
                        language_code=rev.get("languageCode"),
                        retrieved_at=retrieved_at,
                        is_stale=stale,
                        stale_reason=stale_reason,
                    )
                )

        has_conflict = len(polarities) > 1 or ("positive" in polarities and "negative" in polarities)
        conflict_summary = None
        if has_conflict:
            for m in matches:
                m.is_conflicting = True
            pubs_summary = "; ".join(
                f"{m.publisher_name or 'Reviewer'}: '{m.rating_text or 'unrated'}'"
                for m in matches[:4]
            )
            conflict_summary = f"Third-party fact-check publishers reported differing ratings ({pubs_summary})."

        return matches, has_conflict, conflict_summary, any_stale

    def search_claims(self, query: str, max_results: int = 5) -> GoogleFactCheckResult:
        """
        Queries Google Fact Check Tools API for reviews matching a single concise factual claim.
        Never leaks API key in logs or errors; returns safe empty results when key is missing or offline.
        """
        clean_query = re.sub(r"\s+", " ", (query or "").strip())
        now_iso = datetime.now(timezone.utc).isoformat()
        if not clean_query:
            return GoogleFactCheckResult(status="empty_query", available=False, query="")

        settings = get_settings()
        api_key = (getattr(settings, "GOOGLE_FACT_CHECK_API_KEY", "") or "").strip()
        if not api_key:
            return GoogleFactCheckResult(
                status="unavailable_no_api_key",
                available=False,
                query=clean_query,
                retrieved_at=now_iso,
                error_detail="GOOGLE_FACT_CHECK_API_KEY is not configured in backend environment.",
            )

        # 1. Check cache first (keyed only by normalized query)
        cached = self.cache.get("google_fact_check", clean_query)
        if cached is not None:
            cached_ts = cached.get("retrieved_at") or now_iso
            matches, has_conf, conf_sum, any_stale = self._parse_claims_payload(clean_query, cached, cached_ts)
            return GoogleFactCheckResult(
                status="ok_cached" if matches else "no_results",
                available=True,
                query=clean_query,
                matches=matches[:max_results],
                has_conflicting_reviews=has_conf,
                conflict_summary=conf_sum,
                has_stale_reviews=any_stale,
                from_cache=True,
                retrieved_at=cached_ts,
            )

        timeout_sec = max(2.0, float(getattr(settings, "GOOGLE_FACT_CHECK_TIMEOUT_SEC", 8.0)))
        params = {
            "query": clean_query[:400],
            "languageCode": "en",
            "pageSize": max(1, min(10, int(max_results))),
            "key": api_key,
        }

        last_err_status = "network_error"
        last_err_detail = ""
        data: Optional[Dict[str, Any]] = None

        # 2. Bounded retries (max 2 attempts total) only for transient timeouts / 5xx
        sess = self._get_session()
        for attempt in range(2):
            try:
                resp = sess.get(
                    GOOGLE_FACT_CHECK_ENDPOINT,
                    params=params,
                    timeout=(min(5.0, timeout_sec), timeout_sec),
                )
                if resp.status_code in (401, 403):
                    msg = sanitize_secret_text(f"Google Fact Check authentication failed (HTTP {resp.status_code}).", api_key)
                    logger.warning(msg)
                    return GoogleFactCheckResult(
                        status="auth_error",
                        available=False,
                        query=clean_query,
                        retrieved_at=now_iso,
                        error_detail=msg,
                    )
                if resp.status_code == 429:
                    msg = "Google Fact Check API rate limit exceeded (HTTP 429)."
                    logger.warning(msg)
                    return GoogleFactCheckResult(
                        status="rate_limited",
                        available=True,
                        query=clean_query,
                        retrieved_at=now_iso,
                        error_detail=msg,
                    )
                if resp.status_code >= 500:
                    last_err_status = "http_error"
                    last_err_detail = f"Google Fact Check server error (HTTP {resp.status_code})."
                    if attempt == 0:
                        time.sleep(0.3)
                        continue
                    return GoogleFactCheckResult(
                        status=last_err_status,
                        available=True,
                        query=clean_query,
                        retrieved_at=now_iso,
                        error_detail=last_err_detail,
                    )
                if not resp.ok:
                    last_err_detail = sanitize_secret_text(f"HTTP {resp.status_code} from Google Fact Check API.", api_key)
                    return GoogleFactCheckResult(
                        status="http_error",
                        available=True,
                        query=clean_query,
                        retrieved_at=now_iso,
                        error_detail=last_err_detail,
                    )
                parsed = resp.json()
                if not isinstance(parsed, dict):
                    return GoogleFactCheckResult(
                        status="invalid_response",
                        available=True,
                        query=clean_query,
                        retrieved_at=now_iso,
                        error_detail="Malformed JSON object returned by Google Fact Check API.",
                    )
                data = parsed
                break
            except requests.Timeout as exc:
                last_err_status = "timeout"
                last_err_detail = sanitize_secret_text(f"Google Fact Check API timed out: {exc}", api_key)
                if attempt == 0:
                    time.sleep(0.3)
                    continue
            except requests.RequestException as exc:
                last_err_status = "network_error"
                last_err_detail = sanitize_secret_text(f"Google Fact Check network error: {exc}", api_key)
                if attempt == 0:
                    time.sleep(0.3)
                    continue
            except ValueError:
                return GoogleFactCheckResult(
                    status="invalid_response",
                    available=True,
                    query=clean_query,
                    retrieved_at=now_iso,
                    error_detail="Invalid JSON payload from Google Fact Check API.",
                )

        if data is None:
            logger.warning(last_err_detail)
            return GoogleFactCheckResult(
                status=last_err_status,
                available=True,
                query=clean_query,
                retrieved_at=now_iso,
                error_detail=last_err_detail,
            )

        payload_to_cache = dict(data)
        payload_to_cache["retrieved_at"] = now_iso
        self.cache.set("google_fact_check", clean_query, payload_to_cache)

        matches, has_conf, conf_sum, any_stale = self._parse_claims_payload(clean_query, data, now_iso)
        return GoogleFactCheckResult(
            status="ok" if matches else "no_results",
            available=True,
            query=clean_query,
            matches=matches[:max_results],
            has_conflicting_reviews=has_conf,
            conflict_summary=conf_sum,
            has_stale_reviews=any_stale,
            from_cache=False,
            retrieved_at=now_iso,
        )
