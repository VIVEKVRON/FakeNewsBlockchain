"""
Comprehensive mocked test suite for Phase 2 / Group E External Integrations:
  1. Google Fact Check Tools API client (verbatim ratings, conflict/stale flags, error handling, secret hygiene)
  2. GDELT DOC 2.0 gateway (canonical deduplication, syndication collapse, SSRF safety, non-proof discipline)
  3. Shared persistent 200-request GDELT quota tracker (concurrency, warning @ 180, hard stop @ 200,
     cache 0-cost hits, failed request accounting, restart persistence, fail-closed on DB errors)
  4. Unified ExternalEvidenceAggregator, FastAPI routes, six-class compatibility, and canonical hash invariance.

All outbound HTTP calls in this module use local mocks — zero real Google or GDELT API quota is consumed.
"""

import asyncio
import json
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest
import requests
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.config import Settings, validate_gdelt_timespan
from backend.app.main import app
from backend.app.schemas.article import ArticleClassifierSignal, ArticleVerificationResponse
from backend.app.schemas.verification import TextVerificationRequest, TextVerificationResponse, VerdictEnum
from ml.inference.model_loader import get_ml_inference_semaphore
from backend.app.services import news_service, verification_service
from backend.app.services.blockchain_service import create_hash_summary_from_text
from backend.app.services.external_apis.evidence_aggregator import (
    ExternalEvidenceAggregator,
    build_focused_claim_queries,
    should_query_gdelt_for_claim,
)
from backend.app.services.external_apis.evidence_cache import ExternalEvidenceCache
from backend.app.services.external_apis.gdelt_client import GdeltClient, normalize_article_url
from backend.app.services.external_apis.gdelt_usage_tracker import GdeltUsageTracker
from backend.app.services.external_apis.google_factcheck_client import (
    GoogleFactCheckClient,
    GoogleFactCheckResult,
)
from backend.app.services.external_apis.quota_db import sanitize_secret_text, validate_external_http_url
from backend.app.services.news_service import NewsService
from backend.app.services.verification_service import VerificationService

client = TestClient(app)


def _mock_http_response(status_code=200, json_data=None, text_body=None, raise_json=False):
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.ok = 200 <= status_code < 300
    if raise_json:
        resp.json.side_effect = ValueError("Invalid JSON")
    else:
        resp.json.return_value = json_data if json_data is not None else {}
    resp.text = text_body if text_body is not None else json.dumps(json_data or {})
    return resp


def _make_settings(**overrides):
    defaults = dict(
        GOOGLE_FACT_CHECK_API_KEY="TEST_SECRET_API_KEY_DO_NOT_LEAK",
        GOOGLE_FACT_CHECK_TIMEOUT_SEC=5.0,
        GDELT_ENABLED=True,
        GDELT_REQUEST_LIMIT=200,
        GDELT_WARNING_THRESHOLD=20,
        GDELT_CONNECT_TIMEOUT_SEC=8.0,
        GDELT_TIMEOUT_SEC=12.0,
        GDELT_MAX_RECORDS=10,
        GDELT_MAX_RETRIES=0,
        GDELT_DEFAULT_TIMESPAN="1month",
        EXTERNAL_CACHE_TTL_HOURS=24,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# =====================================================================
# 1. Google Fact Check Tools API Client Tests
# =====================================================================

class TestGoogleFactCheckClient:
    def test_parses_all_claim_review_fields_and_preserves_verbatim_rating(self, tmp_path):
        db = str(tmp_path / "fc.db")
        cache = ExternalEvidenceCache(db_path=db)
        sess = MagicMock()
        sess.get.return_value = _mock_http_response(
            200,
            {
                "claims": [
                    {
                        "text": "Solar flares shut down global banking networks in 2025.",
                        "claimant": "Viral Social Post",
                        "claimDate": "2025-04-01T00:00:00Z",
                        "claimReview": [
                            {
                                "publisher": {"name": "PolitiFact", "site": "politifact.com"},
                                "reviewerName": "Jane Factchecker",
                                "url": "https://www.politifact.com/factchecks/2025/apr/02/example/",
                                "title": "No, solar flares did not shut down banks",
                                "reviewDate": "2025-04-02T12:00:00Z",
                                "textualRating": "Two Pinocchios - Mixed Context",
                                "languageCode": "en",
                            }
                        ],
                    }
                ]
            },
        )

        settings = _make_settings()
        with patch("backend.app.services.external_apis.google_factcheck_client.get_settings", return_value=settings):
            fc = GoogleFactCheckClient(cache=cache, session=sess)
            res = fc.search_claims("Solar flares shut down global banking")

        assert res.status == "ok"
        assert res.available is True
        assert len(res.matches) == 1
        m = res.matches[0]
        assert m.claim_text == "Solar flares shut down global banking networks in 2025."
        assert m.review_title == "No, solar flares did not shut down banks"
        assert m.publisher_name == "PolitiFact"
        assert m.publisher_site == "politifact.com"
        assert m.reviewer_name == "Jane Factchecker"
        assert m.rating_text == "Two Pinocchios - Mixed Context"  # Verbatim preservation
        assert m.review_url == "https://www.politifact.com/factchecks/2025/apr/02/example/"
        assert m.review_publication_date == "2025-04-02T12:00:00Z"
        assert m.claim_appearance_date == "2025-04-01T00:00:00Z"
        assert m.original_claim_author == "Viral Social Post"
        assert m.language_code == "en"

    def test_missing_api_key_graceful_unavailable(self, tmp_path):
        cache = ExternalEvidenceCache(db_path=str(tmp_path / "fc.db"))
        sess = MagicMock()
        settings = _make_settings(GOOGLE_FACT_CHECK_API_KEY="")
        with patch("backend.app.services.external_apis.google_factcheck_client.get_settings", return_value=settings):
            fc = GoogleFactCheckClient(cache=cache, session=sess)
            res = fc.search_claims("Paris is the capital of France")

        assert res.status == "unavailable_no_api_key"
        assert res.available is False
        assert res.matches == []
        sess.get.assert_not_called()

    def test_empty_results_do_not_infer_verdict_and_cache_works(self, tmp_path):
        cache = ExternalEvidenceCache(db_path=str(tmp_path / "fc.db"))
        sess = MagicMock()
        sess.get.return_value = _mock_http_response(200, {"claims": []})
        settings = _make_settings()
        with patch("backend.app.services.external_apis.google_factcheck_client.get_settings", return_value=settings):
            fc = GoogleFactCheckClient(cache=cache, session=sess)
            r1 = fc.search_claims("Unseen synthetic claim XYZ")
            r2 = fc.search_claims("Unseen synthetic claim XYZ")

        assert r1.status == "no_results"
        assert r1.matches == []
        assert r2.from_cache is True
        assert sess.get.call_count == 1  # Cached on second lookup

    @pytest.mark.parametrize(
        "status_code,expected_status",
        [
            (401, "auth_error"),
            (403, "auth_error"),
            (429, "rate_limited"),
            (503, "http_error"),
        ],
    )
    def test_http_errors_and_secret_scrubbing(self, tmp_path, status_code, expected_status):
        secret = "SUPER_SECRET_GOOGLE_API_KEY_98765"
        cache = ExternalEvidenceCache(db_path=str(tmp_path / f"fc_{status_code}.db"))
        sess = MagicMock()
        sess.get.return_value = _mock_http_response(status_code, {})
        settings = _make_settings(GOOGLE_FACT_CHECK_API_KEY=secret)
        with (
            patch("backend.app.services.external_apis.google_factcheck_client.get_settings", return_value=settings),
            patch("backend.app.services.external_apis.quota_db.get_settings", return_value=settings),
            patch("backend.app.services.external_apis.google_factcheck_client.time.sleep"),
        ):
            fc = GoogleFactCheckClient(cache=cache, session=sess)
            res = fc.search_claims("Test claim error handling")

        assert res.status == expected_status
        assert res.matches == []
        assert secret not in (res.error_detail or "")

    def test_timeout_network_error_and_malformed_json_scrub_secret(self, tmp_path):
        secret = "TOP_SECRET_KEY_ABC123"
        cache = ExternalEvidenceCache(db_path=str(tmp_path / "fc_err.db"))
        settings = _make_settings(GOOGLE_FACT_CHECK_API_KEY=secret)

        sess_timeout = MagicMock()
        sess_timeout.get.side_effect = requests.Timeout(f"Connection timed out with key={secret}")
        with (
            patch("backend.app.services.external_apis.google_factcheck_client.get_settings", return_value=settings),
            patch("backend.app.services.external_apis.quota_db.get_settings", return_value=settings),
            patch("backend.app.services.external_apis.google_factcheck_client.time.sleep"),
        ):
            fc = GoogleFactCheckClient(cache=cache, session=sess_timeout)
            r_timeout = fc.search_claims("Timeout claim test")
            assert r_timeout.status == "timeout"
            assert secret not in (r_timeout.error_detail or "")

        sess_bad_json = MagicMock()
        sess_bad_json.get.return_value = _mock_http_response(200, raise_json=True)
        with (
            patch("backend.app.services.external_apis.google_factcheck_client.get_settings", return_value=settings),
            patch("backend.app.services.external_apis.quota_db.get_settings", return_value=settings),
        ):
            fc2 = GoogleFactCheckClient(cache=cache, session=sess_bad_json)
            r_json = fc2.search_claims("Malformed json claim")
            assert r_json.status == "invalid_response"

    def test_detects_conflicting_ratings_and_stale_reviews(self, tmp_path):
        cache = ExternalEvidenceCache(db_path=str(tmp_path / "fc_conflict.db"))
        sess = MagicMock()
        sess.get.return_value = _mock_http_response(
            200,
            {
                "claims": [
                    {
                        "text": "Example official holds office currently.",
                        "claimReview": [
                            {
                                "publisher": {"name": "FactCheck A"},
                                "url": "https://factchecka.org/r1",
                                "reviewDate": "2018-05-10",
                                "textualRating": "True",
                                "languageCode": "en",
                            },
                            {
                                "publisher": {"name": "FactCheck B"},
                                "url": "https://factcheckb.org/r2",
                                "reviewDate": "2024-06-01",
                                "textualRating": "False",
                                "languageCode": "en",
                            },
                        ],
                    }
                ]
            },
        )
        settings = _make_settings()
        with patch("backend.app.services.external_apis.google_factcheck_client.get_settings", return_value=settings):
            fc = GoogleFactCheckClient(cache=cache, session=sess)
            res = fc.search_claims("Example official is the current officeholder")

        assert res.has_conflicting_reviews is True
        assert res.conflict_summary is not None
        assert all(m.is_conflicting for m in res.matches)
        assert res.has_stale_reviews is True
        assert any(m.is_stale and m.stale_reason for m in res.matches)


# =====================================================================
# 2. GDELT DOC 2.0 Client & 3. Shared Persistent 200-Req Quota Tests
# =====================================================================

class TestGdeltClientAndSharedQuota:
    def _build_gdelt(self, db_path, sess=None, limit=200, warn=20, max_retries=0):
        tracker = GdeltUsageTracker(db_path=db_path)
        cache = ExternalEvidenceCache(db_path=db_path)
        client_obj = GdeltClient(tracker=tracker, cache=cache, session=sess)
        settings = _make_settings(
            GDELT_REQUEST_LIMIT=limit,
            GDELT_WARNING_THRESHOLD=warn,
            GDELT_MAX_RETRIES=max_retries,
        )
        return client_obj, tracker, cache, settings

    def test_valid_artlist_deduplicates_tracking_params_and_syndication(self, tmp_path):
        db = str(tmp_path / "gdelt.db")
        sess = MagicMock()
        sess.get.return_value = _mock_http_response(
            200,
            {
                "articles": [
                    {
                        "title": "EU Approves New AI Safety Regulation Framework",
                        "url": "https://www.reuters.com/world/europe/ai-safety-2026/?utm_source=x&fbclid=123",
                        "domain": "reuters.com",
                        "seendate": "20261101T100000Z",
                        "language": "English",
                        "sourcecountry": "United Kingdom",
                    },
                    {
                        "title": "EU Approves New AI Safety Regulation Framework",
                        "url": "https://www.reuters.com/world/europe/ai-safety-2026/?utm_medium=email",
                        "domain": "reuters.com",
                        "seendate": "20261101T100500Z",
                    },
                    {
                        "title": "EU approves new AI safety regulation framework!",
                        "url": "https://syndicate.partner-news.org/eu-ai-safety-copy",
                        "domain": "partner-news.org",
                        "seendate": "20261101T110000Z",
                    },
                    {
                        "title": "Local unsafe SSRF injection test",
                        "url": "http://127.0.0.1/admin",
                        "domain": "localhost",
                    },
                    {
                        "title": "Metadata SSRF blocked",
                        "url": "http://169.254.169.254/latest/meta-data/",
                        "domain": "metadata",
                    },
                ]
            },
        )
        gd, tracker, _, settings = self._build_gdelt(db, sess=sess)
        with (
            patch("backend.app.services.external_apis.gdelt_client.get_settings", return_value=settings),
            patch("backend.app.services.external_apis.gdelt_usage_tracker.get_settings", return_value=settings),
            patch("backend.app.services.external_apis.quota_db.get_settings", return_value=settings),
        ):
            res = gd.search_coverage("EU AI safety regulation", source_label="verify_text")

            assert res.status == "ok"
            assert res.raw_count == 5
            assert len(res.articles) == 1  # Canonical + normalized title deduplicated & SSRF filtered
            assert res.articles[0].syndicated_count == 3
            assert res.duplicates_collapsed == 2
            assert res.articles[0].url == "https://www.reuters.com/world/europe/ai-safety-2026"
            assert res.usage.requests_used == 1
            assert res.usage.requests_remaining == 199

            # Google API key MUST never be sent to GDELT
            called_params = sess.get.call_args.kwargs.get("params", {})
            assert "key" not in called_params
            assert settings.GOOGLE_FACT_CHECK_API_KEY not in str(called_params)

            # Second identical call hits SQLite cache with ZERO quota consumption
            res2 = gd.search_coverage("EU AI safety regulation", source_label="verify_text")
            assert res2.status == "ok_cached"
            assert res2.from_cache is True
            assert sess.get.call_count == 1
            status_after = tracker.get_status()
            assert status_after.requests_used == 1
            assert status_after.cache_hits == 1

    def test_failed_requests_are_counted_and_persisted_across_restarts(self, tmp_path):
        db = str(tmp_path / "persist.db")
        sess = MagicMock()
        sess.get.side_effect = [
            requests.Timeout("GDELT timed out"),
            _mock_http_response(429, {}),
            _mock_http_response(200, raise_json=True),
        ]
        gd, tracker, _, settings = self._build_gdelt(db, sess=sess, limit=200, max_retries=0)
        with (
            patch("backend.app.services.external_apis.gdelt_client.get_settings", return_value=settings),
            patch("backend.app.services.external_apis.gdelt_usage_tracker.get_settings", return_value=settings),
            patch("backend.app.services.external_apis.quota_db.get_settings", return_value=settings),
        ):
            r1 = gd.search_coverage("query one", source_label="verify_text")
            r2 = gd.search_coverage("query two", source_label="verify_article")
            r3 = gd.search_coverage("query three", source_label="news_refresh")

            assert r1.status == "timeout"
            assert r2.status == "rate_limited"
            assert r3.status == "invalid_response"

            # Simulate process restart with new GdeltUsageTracker instance reading same SQLite DB
            new_tracker = GdeltUsageTracker(db_path=db)
            st = new_tracker.get_status()
            assert st.requests_used == 3
            assert st.failed_requests == 3
            assert st.requests_remaining == 197
            assert st.last_source == "news_refresh"

    def test_warning_threshold_and_hard_200_request_cap(self, tmp_path):
        db = str(tmp_path / "cap200.db")
        sess = MagicMock()
        sess.get.return_value = _mock_http_response(200, {"articles": []})
        gd, tracker, _, settings = self._build_gdelt(db, sess=sess, limit=200, warn=20, max_retries=0)

        with (
            patch("backend.app.services.external_apis.gdelt_client.get_settings", return_value=settings),
            patch("backend.app.services.external_apis.gdelt_usage_tracker.get_settings", return_value=settings),
            patch("backend.app.services.external_apis.quota_db.get_settings", return_value=settings),
        ):
            # Advance persistent counter cleanly via valid reservations up to 179
            for idx in range(179):
                allowed, st = tracker.reserve_request_slot(f"seed_{idx}")
                assert allowed is True
            assert st.warning_active is False

            # Request #180 hits warning threshold (20 remaining <= 20)
            allowed_180, st_180 = tracker.reserve_request_slot("seed_180")
            assert allowed_180 is True
            assert st_180.requests_used == 180
            assert st_180.requests_remaining == 20
            assert st_180.warning_active is True
            assert st_180.limit_reached is False

            # Advance from 180 to 199 (19 slots), then make request #200 through GdeltClient -> allowed!
            for idx in range(180, 199):
                ok_step, _ = tracker.reserve_request_slot(f"seed_{idx}")
                assert ok_step is True

            r_200 = gd.search_coverage("two hundredth real call", source_label="verify_text")
            assert r_200.status == "no_results"
            assert sess.get.call_count == 1
            assert r_200.usage.requests_used == 200
            assert r_200.usage.requests_remaining == 0
            assert r_200.usage.limit_reached is True

            # Request #201 MUST fail closed with ZERO outbound HTTP requests
            r_201 = gd.search_coverage("blocked request 201", source_label="verify_article")
            assert r_201.status == "quota_exhausted"
            assert sess.get.call_count == 1  # Still 1! 201st never fired
            assert r_201.usage.requests_used == 200

    def test_concurrent_reservations_never_exceed_hard_limit(self, tmp_path):
        db = str(tmp_path / "concurrent.db")
        sess = MagicMock()
        sess.get.return_value = _mock_http_response(200, {"articles": []})
        gd, tracker, _, settings = self._build_gdelt(db, sess=sess, limit=8, warn=2, max_retries=0)

        with (
            patch("backend.app.services.external_apis.gdelt_client.get_settings", return_value=settings),
            patch("backend.app.services.external_apis.gdelt_usage_tracker.get_settings", return_value=settings),
            patch("backend.app.services.external_apis.quota_db.get_settings", return_value=settings),
        ):
            def run_query(i: int):
                return gd.search_coverage(f"unique concurrent claim {i}", source_label="concurrency")

            with ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(run_query, range(16)))

            exhausted = [r for r in results if r.status == "quota_exhausted"]
            allowed = [r for r in results if r.status != "quota_exhausted"]
            assert len(allowed) == 8
            assert len(exhausted) == 8
            assert sess.get.call_count == 8
            assert tracker.get_status().requests_used == 8

    def test_tracker_fails_closed_when_sqlite_unwritable_or_corrupt(self, tmp_path):
        bad_path = str(tmp_path / "missing_dir" / "bad.db")
        tracker = GdeltUsageTracker(db_path=bad_path)
        cache = ExternalEvidenceCache(db_path=bad_path)
        sess = MagicMock()
        gd = GdeltClient(tracker=tracker, cache=cache, session=sess)
        settings = _make_settings()

        with (
            patch("backend.app.services.external_apis.gdelt_usage_tracker.open_sqlite_connection", side_effect=sqlite3.OperationalError("DB locked")),
            patch("backend.app.services.external_apis.gdelt_client.get_settings", return_value=settings),
        ):
            res = gd.search_coverage("should fail closed", source_label="verify_text")

        assert res.status == "tracker_unavailable"
        assert res.usage.tracker_available is False
        sess.get.assert_not_called()

    def test_shared_counter_between_live_news_and_verification(self, tmp_path):
        db = str(tmp_path / "shared.db")
        sess = MagicMock()
        sess.get.return_value = _mock_http_response(
            200,
            {
                "articles": [
                    {
                        "title": "Breaking Summit News",
                        "url": "https://www.bbc.com/news/world-12345",
                        "domain": "bbc.com",
                        "seendate": "20261110T080000Z",
                    }
                ]
            },
        )
        tracker = GdeltUsageTracker(db_path=db)
        cache = ExternalEvidenceCache(db_path=db)
        gd = GdeltClient(tracker=tracker, cache=cache, session=sess)
        fc = GoogleFactCheckClient(cache=cache, session=sess)
        settings = _make_settings(GOOGLE_FACT_CHECK_API_KEY="", GDELT_MAX_RETRIES=0)

        with (
            patch("backend.app.services.external_apis.gdelt_client.get_settings", return_value=settings),
            patch("backend.app.services.external_apis.gdelt_usage_tracker.get_settings", return_value=settings),
            patch("backend.app.services.external_apis.google_factcheck_client.get_settings", return_value=settings),
            patch("backend.app.services.news_service.feedparser.parse", return_value=SimpleNamespace(entries=[])),
        ):
            ns = NewsService(db_path=db)
            ns.gdelt_tracker = tracker
            ns.gdelt_cache = cache
            ns.gdelt_client = gd
            refresh_res = ns.refresh_feeds()
            assert refresh_res.gdelt_usage.requests_used == 1

            agg = ExternalEvidenceAggregator(fact_check_client=fc, gdelt_client=gd)
            ext_res = agg.enrich_claims(
                ["New climate treaty signed by European Summit 2026"],
                phase1_verdict="UNVERIFIED",
                source_label="verify_text",
            )
            assert ext_res.gdelt_usage.requests_used == 2  # Same counter!

    def test_live_news_handles_quota_exhaustion_without_crashing(self, tmp_path):
        db = str(tmp_path / "live_exhausted.db")
        tracker = GdeltUsageTracker(db_path=db)
        cache = ExternalEvidenceCache(db_path=db)
        sess = MagicMock()
        gd = GdeltClient(tracker=tracker, cache=cache, session=sess)
        settings = _make_settings(GDELT_REQUEST_LIMIT=1, GDELT_WARNING_THRESHOLD=1)

        with (
            patch("backend.app.services.external_apis.gdelt_client.get_settings", return_value=settings),
            patch("backend.app.services.external_apis.gdelt_usage_tracker.get_settings", return_value=settings),
            patch("backend.app.services.news_service.feedparser.parse", return_value=SimpleNamespace(entries=[])),
        ):
            tracker.reserve_request_slot("exhaust")
            ns = NewsService(db_path=db)
            ns.gdelt_tracker = tracker
            ns.gdelt_cache = cache
            ns.gdelt_client = gd
            res = ns.refresh_feeds()

        assert res.gdelt_usage.limit_reached is True
        assert any("allowance" in err.lower() or "exhausted" in err.lower() or "limit" in err.lower() for err in res.errors)
        sess.get.assert_not_called()


# =====================================================================
# 4. Aggregation, Query Scoping, API Routes & Six-Class / Hash Stability
# =====================================================================

class TestAggregatorAndApiIntegration:
    def test_focused_query_builder_and_static_fact_gdelt_skip(self):
        long_article = (
            "The International Space Agency launched Explorer IX from Cape Canaveral on Monday. "
            "Scientists reported that solar sensors activated normally in orbit. "
            + ("Additional background commentary paragraph. " * 25)
        )
        fc_q, gd_q = build_focused_claim_queries(long_article)
        assert len(fc_q) <= 280
        assert len(gd_q) < 120
        assert "Additional background commentary" not in gd_q

        run_static, reason = should_query_gdelt_for_claim(
            "Water boils at 100 degrees Celsius at standard atmospheric pressure.",
            phase1_verdict="GENUINE",
        )
        assert run_static is False
        assert reason == "resolved_static_reference_fact"

        run_news, _ = should_query_gdelt_for_claim(
            "Leaked defense memo claimed troops moved in 2026.",
            phase1_verdict="UNVERIFIED",
        )
        assert run_news is True

    def test_aggregator_detects_conflicting_gdelt_framing_and_preserves_phase1(self, tmp_path):
        db = str(tmp_path / "agg.db")
        tracker = GdeltUsageTracker(db_path=db)
        cache = ExternalEvidenceCache(db_path=db)
        fc_sess = MagicMock()
        fc_sess.get.return_value = _mock_http_response(200, {"claims": []})
        gd_sess = MagicMock()
        gd_sess.get.return_value = _mock_http_response(
            200,
            {
                "articles": [
                    {
                        "title": "Ministry confirms new digital ID policy approved today",
                        "url": "https://newsone.example/confirmed",
                        "domain": "newsone.example",
                    },
                    {
                        "title": "Regulator denies claims and refutes rumor of approved digital ID",
                        "url": "https://newstwo.example/denied",
                        "domain": "newstwo.example",
                    },
                ]
            },
        )
        settings = _make_settings(GDELT_MAX_RETRIES=0)
        with (
            patch("backend.app.services.external_apis.google_factcheck_client.get_settings", return_value=settings),
            patch("backend.app.services.external_apis.gdelt_client.get_settings", return_value=settings),
            patch("backend.app.services.external_apis.gdelt_usage_tracker.get_settings", return_value=settings),
        ):
            agg = ExternalEvidenceAggregator(
                fact_check_client=GoogleFactCheckClient(cache=cache, session=fc_sess),
                gdelt_client=GdeltClient(tracker=tracker, cache=cache, session=gd_sess),
            )
            res = agg.enrich_claims(
                ["Digital ID policy approved in 2026"],
                phase1_verdict="UNVERIFIED",
                force_gdelt=True,
            )

        assert res.gdelt_conflicting_coverage is True
        assert any("contrasting framing" in n.lower() for n in res.supplementary_notes)
        assert any("factual proof" in lim.lower() or "coverage metadata" in lim.lower() for lim in res.limitations)

    def test_api_gdelt_usage_endpoint_and_no_unauthenticated_reset(self):
        resp = client.get("/api/v1/news/gdelt-usage")
        assert resp.status_code == 200
        body = resp.json()
        assert body["allowance_limit"] == 200
        assert "requests_used" in body
        assert "requests_remaining" in body
        assert "cache_hits" in body
        assert "google_fact_check_available" in body
        assert "GOOGLE_FACT_CHECK_API_KEY" not in resp.text

        # Ensure no unauthenticated reset endpoint exists
        reset_resp = client.post("/api/v1/news/gdelt-usage/reset")
        assert reset_resp.status_code in (404, 405)

    def test_verify_text_endpoint_includes_external_evidence_without_altering_verdict_or_canonical_hash(self, tmp_path):
        db = str(tmp_path / "api_verify.db")
        tracker = GdeltUsageTracker(db_path=db)
        cache = ExternalEvidenceCache(db_path=db)
        fc_sess = MagicMock()
        fc_sess.get.return_value = _mock_http_response(
            200,
            {
                "claims": [
                    {
                        "text": "19 Kids and Counting was cancelled in 2030.",
                        "claimReview": [
                            {
                                "publisher": {"name": "Lead Stories", "site": "leadstories.com"},
                                "url": "https://leadstories.com/hoax-alert/example",
                                "title": "Fact Check: False claim about cancellation date",
                                "reviewDate": "2026-01-15",
                                "textualRating": "False",
                                "languageCode": "en",
                            }
                        ],
                    }
                ]
            },
        )
        gd_sess = MagicMock()
        gd_sess.get.return_value = _mock_http_response(200, {"articles": []})
        settings = _make_settings(GDELT_MAX_RETRIES=0)

        svc = verification_service.get_verification_service()
        orig_agg = svc.external_aggregator
        try:
            with (
                patch("backend.app.services.external_apis.google_factcheck_client.get_settings", return_value=settings),
                patch("backend.app.services.external_apis.gdelt_client.get_settings", return_value=settings),
                patch("backend.app.services.external_apis.gdelt_usage_tracker.get_settings", return_value=settings),
            ):
                svc.external_aggregator = ExternalEvidenceAggregator(
                    fact_check_client=GoogleFactCheckClient(cache=cache, session=fc_sess),
                    gdelt_client=GdeltClient(tracker=tracker, cache=cache, session=gd_sess),
                )
                r = client.post(
                    "/api/v1/verify/text",
                    json={"claim": "19 Kids and Counting was cancelled in 2030.", "top_k": 5},
                )
                assert r.status_code == 200
                payload = r.json()
                assert payload["verdict"] == "FAKE"  # Phase 1 verdict preserved
                assert len(payload["fact_check_matches"]) == 1
                assert payload["fact_check_matches"][0]["rating_text"] == "False"
                assert payload["external_source_status"]["google_fact_check_status"] == "ok"
                assert settings.GOOGLE_FACT_CHECK_API_KEY not in r.text

                # Canonical hash invariance check against Phase 1 record fields only
                parsed_resp = verification_service.TextVerificationResponse(**payload)
                recomputed = create_hash_summary_from_text("19 Kids and Counting was cancelled in 2030.", parsed_resp)
                assert recomputed.record_hash == payload["blockchain_hash"]["record_hash"]
                assert recomputed.canonical_json == payload["blockchain_hash"]["canonical_json"]
        finally:
            svc.external_aggregator = orig_agg

    def test_verify_article_queries_focused_claims_only(self, tmp_path):
        db = str(tmp_path / "api_art.db")
        tracker = GdeltUsageTracker(db_path=db)
        cache = ExternalEvidenceCache(db_path=db)
        fc_sess = MagicMock()
        fc_sess.get.return_value = _mock_http_response(200, {"claims": []})
        gd_sess = MagicMock()
        gd_sess.get.return_value = _mock_http_response(200, {"articles": []})
        settings = _make_settings(GDELT_MAX_RETRIES=0)

        svc = verification_service.get_verification_service()
        orig_agg = svc.external_aggregator
        try:
            with (
                patch("backend.app.services.external_apis.google_factcheck_client.get_settings", return_value=settings),
                patch("backend.app.services.external_apis.gdelt_client.get_settings", return_value=settings),
                patch("backend.app.services.external_apis.gdelt_usage_tracker.get_settings", return_value=settings),
            ):
                svc.external_aggregator = ExternalEvidenceAggregator(
                    fact_check_client=GoogleFactCheckClient(cache=cache, session=fc_sess),
                    gdelt_client=GdeltClient(tracker=tracker, cache=cache, session=gd_sess),
                )
                body_text = (
                    "19 Kids and Counting is an American reality television show featuring the Duggar family. "
                    "The show aired for multiple seasons on TLC before ending its run. "
                    + ("Routine background context filler text for article length validation. " * 6)
                )
                r = client.post(
                    "/api/v1/verify/article",
                    json={"title": "TLC Reality Show", "text": body_text, "max_claims": 3},
                )
                assert r.status_code == 200
                data = r.json()
                assert data["overall_verdict"] in ("GENUINE", "PARTIALLY_TRUE", "UNVERIFIED", "FAKE", "MISLEADING", "OUTDATED")
                assert "external_source_status" in data
                # Ensure whole 500+ char body was NOT pushed as a single Google Fact Check query
                for call in fc_sess.get.call_args_list:
                    sent_q = call.kwargs.get("params", {}).get("query", "")
                    assert len(sent_q) <= 280
        finally:
            svc.external_aggregator = orig_agg


# =====================================================================
# 5. GDELT Timeout, Retry Conservation, Timespan, Query & Event-Loop Tests
# =====================================================================

class TestGdeltRemediationImprovements:
    def test_settings_defaults_and_timeout_timespan_validation(self):
        default_settings = Settings(_env_file=None)
        assert default_settings.GDELT_CONNECT_TIMEOUT_SEC == 8.0
        assert default_settings.GDELT_TIMEOUT_SEC == 12.0
        assert default_settings.GDELT_MAX_RETRIES == 0
        assert default_settings.GDELT_DEFAULT_TIMESPAN == "1month"

        with pytest.raises(ValidationError):
            Settings(_env_file=None, GDELT_CONNECT_TIMEOUT_SEC=0.0)
        with pytest.raises(ValidationError):
            Settings(_env_file=None, GDELT_TIMEOUT_SEC=-2.0)
        with pytest.raises(ValidationError):
            Settings(_env_file=None, GDELT_TIMEOUT_SEC=120.0)
        with pytest.raises(ValidationError):
            Settings(_env_file=None, GDELT_MAX_RETRIES=-1)
        with pytest.raises(ValidationError):
            Settings(_env_file=None, GDELT_DEFAULT_TIMESPAN="0days")
        with pytest.raises(ValidationError):
            Settings(_env_file=None, GDELT_DEFAULT_TIMESPAN="bad_window")

        assert validate_gdelt_timespan("1WEEK") == "1week"
        assert validate_gdelt_timespan("24h") == "24h"

    def test_uses_decoupled_connect_read_timeout_tuple_and_default_timespan(self, tmp_path):
        db = str(tmp_path / "t_tuple.db")
        sess = MagicMock()
        sess.get.return_value = _mock_http_response(200, {"articles": []})
        settings = _make_settings(
            GDELT_CONNECT_TIMEOUT_SEC=8.0,
            GDELT_TIMEOUT_SEC=12.0,
            GDELT_DEFAULT_TIMESPAN="1month",
        )
        with (
            patch("backend.app.services.external_apis.gdelt_client.get_settings", return_value=settings),
            patch("backend.app.services.external_apis.gdelt_usage_tracker.get_settings", return_value=settings),
            patch("backend.app.services.external_apis.quota_db.get_settings", return_value=settings),
        ):
            gd = GdeltClient(
                tracker=GdeltUsageTracker(db_path=db),
                cache=ExternalEvidenceCache(db_path=db),
                session=sess,
            )
            res = gd.search_coverage("Artemis lunar mission", source_label="remed_test")
            assert res.search_window == "1month"
            assert sess.get.call_args.kwargs.get("timeout") == (8.0, 12.0)
            assert sess.get.call_args.kwargs.get("params", {}).get("timespan") == "1month"

            # Explicit valid timespan preserved
            res_explicit = gd.search_coverage("Artemis explicit window", timespan="1week", source_label="remed_test")
            assert res_explicit.search_window == "1week"
            assert sess.get.call_args.kwargs.get("params", {}).get("timespan") == "1week"

            # Custom connect & read tuple honored without 5s clamp
            settings_custom = _make_settings(GDELT_CONNECT_TIMEOUT_SEC=9.5, GDELT_TIMEOUT_SEC=15.0)
            with patch("backend.app.services.external_apis.gdelt_client.get_settings", return_value=settings_custom):
                gd.search_coverage("Custom timeout claim", source_label="remed_test")
                assert sess.get.call_args.kwargs.get("timeout") == (9.5, 15.0)

            # Invalid configured timeout fails loudly instead of clamping
            bad_settings = _make_settings(GDELT_CONNECT_TIMEOUT_SEC=-1.0)
            with patch("backend.app.services.external_apis.gdelt_client.get_settings", return_value=bad_settings):
                with pytest.raises(ValueError):
                    gd.search_coverage("Should reject negative timeout", source_label="remed_test")

    def test_distinguishes_connect_read_generic_timeouts_and_never_retries_timeouts_or_429(self, tmp_path):
        db = str(tmp_path / "t_exceptions.db")
        tracker = GdeltUsageTracker(db_path=db)
        cache = ExternalEvidenceCache(db_path=db)

        cases = [
            (requests.ConnectTimeout("connect stalled"), "connect_timeout", "connect_timeout"),
            (requests.ReadTimeout("read stalled"), "read_timeout", "read_timeout"),
            (requests.Timeout("generic timeout"), "timeout", "timeout"),
            (_mock_http_response(429, {}), "rate_limited", "http_429_rate_limited"),
            (_mock_http_response(503, {}), "http_error", "http_503"),
        ]
        # Even when GDELT_MAX_RETRIES=1 is configured, timeouts & 429 must NEVER retry (only HTTP 5xx retries once)
        settings_retry1 = _make_settings(GDELT_MAX_RETRIES=1)
        settings_default = _make_settings(GDELT_MAX_RETRIES=0)

        for idx, (outcome, exp_status, exp_tracker_status) in enumerate(cases):
            sess = MagicMock()
            if isinstance(outcome, Exception):
                sess.get.side_effect = outcome
            else:
                sess.get.return_value = outcome
            gd = GdeltClient(tracker=tracker, cache=cache, session=sess)

            # Default settings (GDELT_MAX_RETRIES=0): even HTTP 503 runs exactly 1 call
            with (
                patch("backend.app.services.external_apis.gdelt_client.get_settings", return_value=settings_default),
                patch("backend.app.services.external_apis.gdelt_usage_tracker.get_settings", return_value=settings_default),
                patch("backend.app.services.external_apis.quota_db.get_settings", return_value=settings_default),
            ):
                before_used = tracker.get_status().requests_used
                r = gd.search_coverage(f"unique failure default {idx}", source_label="diag")
                assert r.status == exp_status
                assert sess.get.call_count == 1
                st = tracker.get_status()
                assert st.requests_used == before_used + 1
                assert st.last_status == exp_tracker_status

            # Explicit GDELT_MAX_RETRIES=1: ONLY 5xx retries (2 calls); ConnectTimeout/ReadTimeout/Timeout/429 still do 1 call
            sess2 = MagicMock()
            if isinstance(outcome, Exception):
                sess2.get.side_effect = outcome
            else:
                sess2.get.return_value = outcome
            gd2 = GdeltClient(tracker=tracker, cache=cache, session=sess2)
            with (
                patch("backend.app.services.external_apis.gdelt_client.get_settings", return_value=settings_retry1),
                patch("backend.app.services.external_apis.gdelt_usage_tracker.get_settings", return_value=settings_retry1),
                patch("backend.app.services.external_apis.quota_db.get_settings", return_value=settings_retry1),
                patch("backend.app.services.external_apis.gdelt_client.time.sleep"),
            ):
                before_used = tracker.get_status().requests_used
                r2 = gd2.search_coverage(f"unique failure retry1 {idx}", source_label="diag")
                assert r2.status == exp_status
                expected_calls = 2 if exp_status == "http_error" else 1
                assert sess2.get.call_count == expected_calls
                assert tracker.get_status().requests_used == before_used + expected_calls

    def test_invalid_timespan_rejected_with_zero_http_or_quota_cost(self, tmp_path):
        db = str(tmp_path / "t_bad_ts.db")
        tracker = GdeltUsageTracker(db_path=db)
        cache = ExternalEvidenceCache(db_path=db)
        sess = MagicMock()
        settings = _make_settings()
        with (
            patch("backend.app.services.external_apis.gdelt_client.get_settings", return_value=settings),
            patch("backend.app.services.external_apis.gdelt_usage_tracker.get_settings", return_value=settings),
            patch("backend.app.services.external_apis.quota_db.get_settings", return_value=settings),
        ):
            gd = GdeltClient(tracker=tracker, cache=cache, session=sess)
            for bad_ts in ("0days", "-5weeks", "abc", "1week&bad=1", "99months"):
                res = gd.search_coverage("NASA Artemis test", timespan=bad_ts, source_label="diag")
                assert res.status == "invalid_timespan"
            sess.get.assert_not_called()
            assert tracker.get_status().requests_used == 0

    def test_concise_gdelt_query_preserves_entities_and_filters_temporal_noise(self):
        q1 = "2026 Artemis NASA lunar mission November"
        fc1, gd1 = build_focused_claim_queries(q1)
        assert fc1 == q1  # Google Fact Check query unchanged
        assert "Artemis" in gd1
        assert "NASA" in gd1
        assert "November" not in gd1
        assert "2026" not in gd1
        assert 3 <= len(gd1.split()) <= 5

        q2 = "NASA Space Shuttle currently flies regular astronaut missions to the International Space Station"
        fc2, gd2 = build_focused_claim_queries(q2)
        assert fc2 == q2
        assert "International Space Station" in gd2
        assert "NASA" in gd2
        assert "currently" not in gd2.lower()
        assert "regular" not in gd2.lower()

        # Sparse claim with fewer than 3 non-temporal terms may keep year fallback safely
        _, gd3 = build_focused_claim_queries("2026 Olympics Paris")
        assert "Olympics" in gd3
        assert "Paris" in gd3

    def test_verify_routes_run_off_event_loop_and_do_not_block_health_or_gdelt_usage(self):
        async def _exercise_concurrency():
            loop_thread_id = threading.get_ident()
            worker_thread_ids = []
            entered_verify = threading.Event()
            release_verify = threading.Event()

            svc = verification_service.get_verification_service()

            def slow_fake_verify_text(req):
                worker_thread_ids.append(threading.get_ident())
                entered_verify.set()
                release_verify.wait(timeout=3.0)
                return TextVerificationResponse(
                    claim=req.claim,
                    verdict=VerdictEnum.UNVERIFIED,
                    confidence_score=0.25,
                    explanation="Mocked non-blocking check",
                    evidence=[],
                    limitations=[],
                )

            with patch.object(svc, "verify_text_claim", side_effect=slow_fake_verify_text):
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
                    verify_task = asyncio.create_task(
                        ac.post("/api/v1/verify/text", json={"claim": "Concurrency event loop check claim"})
                    )
                    # Wait briefly on event loop until threadpool enters slow_fake_verify_text
                    for _ in range(40):
                        if entered_verify.is_set():
                            break
                        await asyncio.sleep(0.01)
                    assert entered_verify.is_set()
                    assert not verify_task.done()

                    t0 = time.monotonic()
                    health_resp, usage_resp = await asyncio.gather(
                        ac.get("/api/v1/health"),
                        ac.get("/api/v1/news/gdelt-usage"),
                    )
                    elapsed_light = time.monotonic() - t0

                    assert health_resp.status_code == 200
                    assert usage_resp.status_code == 200
                    assert elapsed_light < 0.5
                    assert not verify_task.done()

                    release_verify.set()
                    v_resp = await verify_task
                    assert v_resp.status_code == 200
                    assert v_resp.json()["verdict"] == "UNVERIFIED"
                    assert worker_thread_ids and worker_thread_ids[0] != loop_thread_id

            # Verify /verify/article also runs off the event loop cleanly and ML semaphore is bounded
            sem = get_ml_inference_semaphore()
            assert sem.acquire(blocking=False) is True
            assert sem.acquire(blocking=False) is False  # Bounded to 1 concurrent CPU inference pass
            sem.release()

            art_entered = threading.Event()
            art_release = threading.Event()
            art_thread_ids = []

            def slow_fake_verify_article(req):
                art_thread_ids.append(threading.get_ident())
                art_entered.set()
                art_release.wait(timeout=3.0)
                return ArticleVerificationResponse(
                    title=req.title,
                    overall_verdict=VerdictEnum.UNVERIFIED,
                    overall_confidence=0.25,
                    summary_explanation="Mocked article off-loop",
                    article_classifier=ArticleClassifierSignal(
                        prediction="REAL",
                        confidence=0.5,
                        probabilities={"FAKE": 0.5, "REAL": 0.5},
                        distribution_shift_warning="test",
                    ),
                    claims_analyzed=0,
                    extracted_claims=[],
                    limitations=[],
                )

            with patch.object(svc, "verify_article", side_effect=slow_fake_verify_article):
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
                    art_task = asyncio.create_task(
                        ac.post(
                            "/api/v1/verify/article",
                            json={"title": "Concurrency test", "text": "Testing blocking article verification off the event loop safely."},
                        )
                    )
                    for _ in range(40):
                        if art_entered.is_set():
                            break
                        await asyncio.sleep(0.01)
                    assert art_entered.is_set()
                    h_r = await ac.get("/api/v1/health")
                    assert h_r.status_code == 200
                    assert not art_task.done()
                    art_release.set()
                    a_resp = await art_task
                    assert a_resp.status_code == 200
                    assert art_thread_ids and art_thread_ids[0] != loop_thread_id

        asyncio.run(_exercise_concurrency())
