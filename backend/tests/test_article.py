"""
backend/tests/test_article.py
Unit and integration tests for full article verification, factual claim extraction,
ISOT classification, LIAR signals, and Swagger documentation.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.services import verification_service
from backend.app.services.external_apis.evidence_aggregator import ExternalEvidenceAggregator
from backend.app.services.external_apis.evidence_cache import ExternalEvidenceCache
from backend.app.services.external_apis.gdelt_client import GdeltClient
from backend.app.services.external_apis.gdelt_usage_tracker import GdeltUsageTracker
from backend.app.services.external_apis.google_factcheck_client import GoogleFactCheckClient

client = TestClient(app)


def test_article_supported(tmp_path):
    """Tests an article whose claims are independently corroborated as GENUINE."""
    payload = {
        "title": "TLC Reality Series Follows Duggar Family",
        "text": (
            "19 Kids and Counting is an American reality television show featuring the Duggar family. "
            "The reality show focused on the life of the Duggar family who are devout Baptists. "
            "The series originally documented their day-to-day household activities in Arkansas."
        ),
        "max_claims": 2
    }
    db = str(tmp_path / "art_supported.db")
    tracker = GdeltUsageTracker(db_path=db)
    cache = ExternalEvidenceCache(db_path=db)

    def _fc_get(_url, params=None, **_kwargs):
        q = (params or {}).get("query", "")
        if "baptist" in q.lower():
            return MagicMock(
                status_code=200,
                ok=True,
                json=lambda: {
                    "claims": [
                        {
                            "text": "The reality show focused on the life of the Duggar family who are devout Baptists.",
                            "claimReview": [
                                {
                                    "publisher": {"name": "Broadcast Reference Check", "site": "refcheck.example.org"},
                                    "url": "https://refcheck.example.org/duggar-baptists",
                                    "title": "Duggar family religious background verified",
                                    "reviewDate": "2026-01-15",
                                    "textualRating": "True",
                                    "languageCode": "en",
                                }
                            ],
                        }
                    ]
                },
            )
        return MagicMock(status_code=200, ok=True, json=lambda: {"claims": []})

    fc_sess = MagicMock()
    fc_sess.get.side_effect = _fc_get
    gd_sess = MagicMock()
    gd_sess.get.return_value = MagicMock(status_code=200, ok=True, json=lambda: {"articles": []})
    settings = SimpleNamespace(
        GOOGLE_FACT_CHECK_API_KEY="test-key-safe",
        GOOGLE_FACT_CHECK_TIMEOUT_SEC=5.0,
        GDELT_ENABLED=True,
        GDELT_REQUEST_LIMIT=200,
        GDELT_WARNING_THRESHOLD=20,
        GDELT_CONNECT_TIMEOUT_SEC=8.0,
        GDELT_TIMEOUT_SEC=12.0,
        GDELT_MAX_RECORDS=10,
        GDELT_MAX_RETRIES=0,
        GDELT_DEFAULT_TIMESPAN="1month",
    )

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
            response = client.post("/api/v1/verify/article", json=payload)
    finally:
        svc.external_aggregator = orig_agg

    assert response.status_code == 200
    data = response.json()

    assert data["overall_verdict"] == "GENUINE"
    assert data["claims_analyzed"] >= 1
    assert data["article_classifier"]["prediction"] in ["FAKE", "REAL"]
    assert "distribution shifts" in data["article_classifier"]["distribution_shift_warning"]
    
    # Check that individual claims have supporting evidence
    top_claim = data["extracted_claims"][0]
    assert top_claim["verdict"] == "GENUINE"
    assert top_claim["liar_signal"] is not None


def test_article_refuted():
    """Tests an article containing a fabricated cancellation date yielding FAKE."""
    payload = {
        "title": "Television Show Cancellation Date Rumors",
        "text": (
            "19 Kids and Counting was cancelled in 2030. "
            "Industry analysts claimed that network executives delayed the official cancellation "
            "until the beginning of the next decade."
        ),
        "max_claims": 2
    }
    response = client.post("/api/v1/verify/article", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["overall_verdict"] == "FAKE"
    assert any(c["verdict"] == "FAKE" for c in data["extracted_claims"])


def test_article_misleading_broadcaster():
    """Tests that claiming an alternative broadcaster (HBO vs TLC) yields MISLEADING rather than absolute fake."""
    payload = {
        "title": "Television Network Broadcasting History",
        "text": (
            "19 Kids and Counting aired on HBO. "
            "The show attracted millions of viewers across the country during its primetime weekend broadcast slot."
        ),
        "max_claims": 1
    }
    response = client.post("/api/v1/verify/article", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["overall_verdict"] == "MISLEADING"
    assert any(c["verdict"] == "MISLEADING" for c in data["extracted_claims"])
    assert "tlc" in data["extracted_claims"][0]["explanation"].lower()


def test_article_unverified_out_of_domain():
    """Tests an article with futuristic/alien claims yielding UNVERIFIED."""
    payload = {
        "title": "Space Discovery Telemetry",
        "text": (
            "Quantum entangled alien potatoes were discovered on Pluto in 2026. "
            "Autonomous exploration probes returned unexpected spectroscopic measurements to researchers."
        ),
        "max_claims": 1
    }
    response = client.post("/api/v1/verify/article", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["overall_verdict"] == "UNVERIFIED"


def test_article_empty_and_invalid_input():
    """Tests 422 validation on empty, too short, or out-of-bounds requests."""
    # Empty text
    assert client.post("/api/v1/verify/article", json={"text": ""}).status_code == 422
    # Too short text (< 20 chars)
    assert client.post("/api/v1/verify/article", json={"text": "Short"}).status_code == 422
    # Max claims out of bounds (0 or 10)
    assert client.post("/api/v1/verify/article", json={"text": "Valid text length here for testing", "max_claims": 0}).status_code == 422
    assert client.post("/api/v1/verify/article", json={"text": "Valid text length here for testing", "max_claims": 10}).status_code == 422


def test_article_multiple_factual_claims():
    """Tests that max_claims extracts and verifies multiple claims up to the specified limit."""
    payload = {
        "title": "Multi-claim Reality Show Overview",
        "text": (
            "19 Kids and Counting is an American reality television show featuring the Duggar family. "
            "The parents Jim Bob and Michelle Duggar raised nineteen children in Arkansas. "
            "The reality show focused on the life of the Duggar family who are devout Baptists."
        ),
        "max_claims": 3
    }
    response = client.post("/api/v1/verify/article", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["claims_analyzed"] == 3
    assert len(data["extracted_claims"]) == 3
    for i, c in enumerate(data["extracted_claims"], 1):
        assert c["relevance_rank"] == i
        assert len(c["claim"]) > 10


def test_swagger_and_openapi_documentation():
    """Verifies that OpenAPI schema includes both text and article endpoints with correct schemas."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    spec = response.json()

    paths = spec.get("paths", {})
    assert "/api/v1/verify/text" in paths
    assert "/api/v1/verify/article" in paths
    assert "post" in paths["/api/v1/verify/article"]

    schemas = spec.get("components", {}).get("schemas", {})
    assert "ArticleVerificationRequest" in schemas
    assert "ArticleVerificationResponse" in schemas
    assert "ArticleClassifierSignal" in schemas
    assert "ExtractedClaimVerification" in schemas
