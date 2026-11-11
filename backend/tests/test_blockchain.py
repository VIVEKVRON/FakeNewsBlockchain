"""
backend/tests/test_blockchain.py
Unit and integration tests for canonical verification hashing, tamper detection,
and blockchain status endpoints.
"""

import json
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.blockchain_service import (
    compute_sha256,
    build_canonical_record,
    serialize_canonical_record,
    create_hash_summary_from_text,
    create_hash_summary_from_article,
    get_blockchain_service
)
from backend.app.schemas.blockchain import (
    CanonicalVerificationRecord,
    VerificationHashSummary,
    VerifyHashRequest
)
from backend.app.schemas.verification import (
    TextVerificationResponse,
    VerdictEnum,
    EvidenceSentenceSchema,
    NLIProbabilitiesSchema
)
from backend.app.schemas.article import (
    ArticleVerificationResponse,
    ArticleClassifierSignal,
    ExtractedClaimVerification
)

client = TestClient(app)


def test_sha256_computation():
    """Verify SHA-256 produces valid 64-character lowercase hex string."""
    text = "The earth orbits around the sun."
    digest = compute_sha256(text)
    assert len(digest) == 64
    assert digest == digest.lower()
    assert all(c in "0123456789abcdef" for c in digest)
    # Idempotent
    assert compute_sha256(text) == digest


def test_canonical_record_deterministic_serialization():
    """Verify that canonical JSON serialization is sorted and compact."""
    record = CanonicalVerificationRecord(
        schema_version="1.0",
        verification_id="verif-test-001",
        original_content_hash=compute_sha256("Test Claim"),
        primary_verdict="LIKELY_GENUINE",
        confidence_score=0.9125,
        evidence_hashes=[compute_sha256("Evidence sentence 1")],
        timestamp="2026-11-06T12:00:00Z"
    )

    canonical_json, hash_hex, hash_bytes32 = serialize_canonical_record(record)
    
    # Assert deterministic key ordering
    parsed = json.loads(canonical_json)
    keys_in_json = list(parsed.keys())
    assert keys_in_json == sorted(keys_in_json)
    
    # Assert compact separators (no space after colon or comma)
    assert ": " not in canonical_json
    assert ", " not in canonical_json
    
    # Assert hash properties
    assert len(hash_hex) == 64
    assert hash_bytes32.startswith("0x")
    assert len(hash_bytes32) == 66


def test_tamper_detection_sensitivity():
    """Verify that any alteration in content, verdict, score, or evidence yields a different hash."""
    base = build_canonical_record(
        verification_id="art-test-100",
        original_content="Original verified article text.",
        primary_verdict="LIKELY_GENUINE",
        confidence_score=0.95,
        evidence_texts=["Evidence from Wikipedia page."],
        timestamp="2026-11-06T12:00:00Z"
    )

    # 1. Altered verdict (Tampering attempt: LIKELY_GENUINE -> LIKELY_FAKE)
    tampered_verdict = build_canonical_record(
        verification_id="art-test-100",
        original_content="Original verified article text.",
        primary_verdict="LIKELY_FAKE",
        confidence_score=0.95,
        evidence_texts=["Evidence from Wikipedia page."],
        timestamp="2026-11-06T12:00:00Z"
    )
    assert base.record_hash != tampered_verdict.record_hash

    # 2. Altered confidence score (Tampering attempt: 0.95 -> 0.99)
    tampered_score = build_canonical_record(
        verification_id="art-test-100",
        original_content="Original verified article text.",
        primary_verdict="LIKELY_GENUINE",
        confidence_score=0.99,
        evidence_texts=["Evidence from Wikipedia page."],
        timestamp="2026-11-06T12:00:00Z"
    )
    assert base.record_hash != tampered_score.record_hash

    # 3. Altered evidence (Tampering attempt: modified evidence text)
    tampered_evidence = build_canonical_record(
        verification_id="art-test-100",
        original_content="Original verified article text.",
        primary_verdict="LIKELY_GENUINE",
        confidence_score=0.95,
        evidence_texts=["Evidence from Wikipedia page with injected words."],
        timestamp="2026-11-06T12:00:00Z"
    )
    assert base.record_hash != tampered_evidence.record_hash

    # 4. Altered original content (Tampering attempt: modified claim)
    tampered_content = build_canonical_record(
        verification_id="art-test-100",
        original_content="Subtly altered article text.",
        primary_verdict="LIKELY_GENUINE",
        confidence_score=0.95,
        evidence_texts=["Evidence from Wikipedia page."],
        timestamp="2026-11-06T12:00:00Z"
    )
    assert base.record_hash != tampered_content.record_hash


def test_hash_summary_from_text_response():
    """Verify hashing from a real TextVerificationResponse structure."""
    dummy_text_res = TextVerificationResponse(
        verification_id="verif-abc-123",
        claim="Water freezes at 0 degrees Celsius.",
        verdict=VerdictEnum.LIKELY_GENUINE,
        confidence_score=0.92,
        explanation="Entailment verified by science articles.",
        evidence=[
            EvidenceSentenceSchema(
                rank=1,
                page="Water",
                sentence_id=4,
                doc_id="Water_4",
                text="Pure water freezes at 0 degrees Celsius under standard atmospheric pressure.",
                retrieval_similarity=0.88,
                nli_label="SUPPORTS",
                nli_confidence=0.96,
                nli_probabilities=NLIProbabilitiesSchema(supports=0.96, refutes=0.02, not_enough_info=0.02)
            )
        ],
        created_at="2026-11-06T12:00:00Z"
    )

    summary = create_hash_summary_from_text("Water freezes at 0 degrees Celsius.", dummy_text_res)
    assert summary.verification_id == "verif-abc-123"
    assert len(summary.record_hash) == 64
    assert summary.canonical_record.primary_verdict == "LIKELY_GENUINE"
    assert len(summary.canonical_record.evidence_hashes) == 1
    assert summary.record_hash_bytes32.startswith("0x")


def test_hash_summary_from_article_response():
    """Verify hashing from a real ArticleVerificationResponse structure."""
    dummy_art_res = ArticleVerificationResponse(
        article_id="art-xyz-987",
        title="Sample News",
        overall_verdict=VerdictEnum.MISLEADING,
        overall_confidence=0.75,
        summary_explanation="Conflicting claims detected.",
        article_classifier=ArticleClassifierSignal(
            model="google-bert/bert-base-uncased (ISOT)",
            prediction="REAL",
            confidence=0.85,
            probabilities={"REAL": 0.85, "FAKE": 0.15},
            distribution_shift_warning="Warning"
        ),
        claims_analyzed=1,
        extracted_claims=[],
        created_at="2026-11-06T12:00:00Z"
    )

    summary = create_hash_summary_from_article("Sample article body text with more than 20 chars.", dummy_art_res)
    assert summary.verification_id == "art-xyz-987"
    assert summary.canonical_record.primary_verdict == "MISLEADING"
    assert len(summary.record_hash) == 64


def test_blockchain_status_api():
    """Verify GET /api/v1/blockchain/status returns complete schema."""
    response = client.get("/api/v1/blockchain/status")
    assert response.status_code == 200
    data = response.json()
    assert "enabled" in data
    assert "connected" in data
    assert "network" in data
    assert "epistemological_disclaimer" in data
    assert "non-repudiation" in data["epistemological_disclaimer"].lower()
    # Contract address loaded from hardhat-deployment.json if present
    if data["contract_address"]:
        assert data["contract_address"].startswith("0x")


def test_verify_hash_api_unregistered():
    """Verify POST /api/v1/blockchain/verify-hash responds cleanly for non-existent record."""
    response = client.post(
        "/api/v1/blockchain/verify-hash",
        json={
            "verification_id": "non-existent-id-9999",
            "record_hash": "a" * 64
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["verification_id"] == "non-existent-id-9999"
    # When offline or contract not connected, returns appropriate status
    assert data["integrity_status"] in ["NOT_FOUND_ON_CHAIN", "RPC_UNAVAILABLE", "CONTRACT_NOT_FOUND"]
