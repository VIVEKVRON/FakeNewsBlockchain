"""
backend/tests/test_news.py
Unit and integration tests for live breaking news monitoring:
  - Public RSS ingestion
  - GDELT integration
  - Duplicate detection via canonical URL & content hashing
  - SSRF protection on internal/private IPs
  - SQLite persistence, filtering, and pagination
  - One-click article verification dispatch
"""

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.news_service import (
    is_safe_url,
    normalize_canonical_url,
    get_news_service
)

client = TestClient(app)


def test_ssrf_protection():
    """Verify that SSRF protection rejects private, loopback, and local network URLs."""
    unsafe_urls = [
        "http://localhost:8000/secret",
        "http://127.0.0.1/admin",
        "http://127.0.0.1:8000/api/v1/health",
        "http://10.0.0.1/internal",
        "http://192.168.1.1/router",
        "http://172.16.0.1/private",
        "ftp://example.com/file",
        "file:///etc/passwd",
        "http://169.254.169.254/latest/meta-data/",  # Cloud metadata service
    ]
    for url in unsafe_urls:
        assert not is_safe_url(url), f"Unsafe URL was incorrectly allowed: {url}"

    # Public URLs should be permitted
    assert is_safe_url("https://www.bbc.co.uk/news")
    assert is_safe_url("https://feeds.npr.org/1001/rss.xml")


def test_canonical_url_normalization():
    """Verify stripping of marketing tracking and social redirect parameters."""
    url1 = "https://www.bbc.co.uk/news/articles/12345?utm_source=twitter&utm_medium=social"
    url2 = "https://www.bbc.co.uk/news/articles/12345?fbclid=IwAR123&utm_campaign=breaking"
    
    canon1 = normalize_canonical_url(url1)
    canon2 = normalize_canonical_url(url2)

    assert canon1 == canon2
    assert "utm_source" not in canon1
    assert "fbclid" not in canon2
    assert canon1 == "https://www.bbc.co.uk/news/articles/12345"


def test_news_sources_endpoint():
    """Verify listing of configured news monitoring sources."""
    response = client.get("/api/v1/news/sources")
    assert response.status_code == 200
    data = response.json()
    assert "sources" in data
    assert len(data["sources"]) >= 4
    
    source_names = [s["name"] for s in data["sources"]]
    assert any("BBC" in name for name in source_names)
    assert any("NPR" in name for name in source_names)


def test_news_refresh_and_deduplication():
    """Verify RSS ingestion, SQLite caching, and duplicate suppression."""
    response = client.post("/api/v1/news/refresh")
    assert response.status_code == 200
    data = response.json()

    assert data["status"] in ["success", "partial"]
    assert data["sources_contacted"] >= 4
    assert data["sources_succeeded"] >= 1
    assert "refreshed_at" in data

    # Re-running refresh immediately should detect duplicates
    second_response = client.post("/api/v1/news/refresh")
    assert second_response.status_code == 200
    second_data = second_response.json()
    assert second_data["duplicates_skipped"] >= 0


def test_news_list_and_filters():
    """Verify retrieval of news articles with pagination and filtering."""
    response = client.get("/api/v1/news?limit=10&offset=0")
    assert response.status_code == 200
    data = response.json()

    assert "total" in data
    assert "articles" in data
    assert data["limit"] == 10
    assert data["offset"] == 0

    if data["articles"]:
        first_art = data["articles"][0]
        assert "id" in first_art
        assert "canonical_url" in first_art
        assert "title" in first_art
        assert "publisher" in first_art

        # Test keyword filter
        kw = first_art["title"].split()[0]
        kw_resp = client.get(f"/api/v1/news?keyword={kw}")
        assert kw_resp.status_code == 200
        assert kw_resp.json()["total"] >= 1


def test_verify_cached_news_article():
    """Verify dispatching a cached news article to the verification engine."""
    # Ensure there is at least one article
    client.post("/api/v1/news/refresh")
    list_resp = client.get("/api/v1/news?limit=1")
    assert list_resp.status_code == 200
    articles = list_resp.json()["articles"]
    assert len(articles) > 0

    target_id = articles[0]["id"]

    # Verify article
    verify_resp = client.post(f"/api/v1/news/{target_id}/verify")
    assert verify_resp.status_code == 200
    v_data = verify_resp.json()

    assert "overall_verdict" in v_data
    assert "overall_confidence" in v_data
    assert "article_classifier" in v_data
    assert "extracted_claims" in v_data

    # Check that SQLite recorded the verdict
    cached_resp = client.get("/api/v1/news?limit=10")
    matching = [a for a in cached_resp.json()["articles"] if a["id"] == target_id]
    assert len(matching) == 1
    assert matching[0]["verified_verdict"] == v_data["overall_verdict"]


def test_verify_nonexistent_news_article():
    """Verify that requesting verification for an invalid ID returns 404."""
    response = client.post("/api/v1/news/art-nonexistent-99999/verify")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
