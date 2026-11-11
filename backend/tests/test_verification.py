"""
backend/tests/test_verification.py
Comprehensive integration tests for Evidence Retrieval, Claim Verification,
Verdict Synthesis, and input validation.
"""

import pytest
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


def test_verify_supported_claim():
    """Validates that a factual claim supported by Wikipedia yields GENUINE."""
    payload = {
        "claim": "19 Kids and Counting is an American reality television show featuring the Duggar family.",
        "top_k": 5
    }
    response = client.post("/api/v1/verify/text", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["claim"] == payload["claim"]
    assert data["verdict"] == "GENUINE"
    assert data["confidence_score"] > 0.60
    assert len(data["evidence"]) > 0
    assert "uncertainty_explanation" in data and len(data["uncertainty_explanation"]) > 10

    top_evidence = data["evidence"][0]
    assert "19 Kids and Counting" in top_evidence["page"]
    assert top_evidence["nli_label"] == "SUPPORTS"
    assert top_evidence["retrieval_similarity"] > 0.50
    assert top_evidence["nli_probabilities"]["supports"] > 0.80
    assert top_evidence["publication_date"]

    limitations_text = " ".join(data["limitations"])
    assert "FEVER" in limitations_text or "uncalibrated" in limitations_text


def test_verify_refuted_claim():
    """Validates that a claim directly contradicted by Wikipedia yields FAKE."""
    payload = {
        "claim": "19 Kids and Counting was cancelled in 2030.",
        "top_k": 5
    }
    response = client.post("/api/v1/verify/text", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["verdict"] == "FAKE"
    assert data["confidence_score"] > 0.60
    assert len(data["evidence"]) > 0

    # Entity-matched evidence should refute the 2030 cancellation
    target_evidence = [e for e in data["evidence"] if "19 Kids and Counting" in e["page"]]
    assert len(target_evidence) > 0
    assert any(e["nli_label"] == "REFUTES" for e in target_evidence)


def test_verify_unverified_weak_retrieval():
    """Validates that an out-of-domain or futuristic claim yields UNVERIFIED."""
    payload = {
        "claim": "Quantum entangled alien potatoes were discovered on Pluto in 2026.",
        "top_k": 5
    }
    response = client.post("/api/v1/verify/text", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["verdict"] == "UNVERIFIED"
    assert "lacks" in data["explanation"] or "insufficient" in data["explanation"] or "relevance" in data["explanation"]


def test_verify_not_enough_info():
    """Validates that an unprovable personal claim yields UNVERIFIED without fabricating certainty."""
    payload = {
        "claim": "Michelle Duggar ate a croissant in Paris on May 4, 1999.",
        "top_k": 5
    }
    response = client.post("/api/v1/verify/text", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["verdict"] == "UNVERIFIED"
    assert any(
        kw in data["explanation"].lower()
        for kw in ("insufficient", "relevance", "lacks", "similarity", "verify or refute")
    )


def test_validation_empty_input():
    """Validates 422 error on empty or whitespace claims."""
    response = client.post("/api/v1/verify/text", json={"claim": ""})
    assert response.status_code == 422

    response_ws = client.post("/api/v1/verify/text", json={"claim": "   "})
    assert response_ws.status_code == 422


def test_validation_oversized_input():
    """Validates 422 error when claim exceeds 1000 characters."""
    long_claim = "A" * 1005
    response = client.post("/api/v1/verify/text", json={"claim": long_claim})
    assert response.status_code == 422


def test_validation_top_k_bounds():
    """Validates 422 error when top_k is out of 1..20 bounds."""
    response_low = client.post("/api/v1/verify/text", json={"claim": "Valid claim", "top_k": 0})
    assert response_low.status_code == 422

    response_high = client.post("/api/v1/verify/text", json={"claim": "Valid claim", "top_k": 50})
    assert response_high.status_code == 422
