"""
backend/tests/test_milestone3.py
Comprehensive unit and integration tests for Day 3 Milestone 3:
- SQLite persistence, repository operations, CRUD, and pagination
- Search and multi-field filtering (content_type, verdict, blockchain_status, keyword)
- Vector PDF verification certificate generation and unanchored record safeguards
- QR code generation and payload verification
- Independent public certificate verification (MATCH, MISMATCH, NOT_FOUND)
- Blockchain audit explorer endpoints and live on-chain comparison
"""

import io
import pytest
from PIL import Image
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.database.repository import (
    save_verification_record,
    get_verification_record,
    list_verification_records,
    update_blockchain_anchoring
)
from backend.app.services.certificate_service import (
    generate_certificate_qr_code,
    generate_verification_pdf
)

client = TestClient(app)


# ==============================================================================
# 1. DATABASE REPOSITORY & PERSISTENCE TESTS
# ==============================================================================

def test_sqlite_save_and_retrieve_text_record():
    """Test saving a text verification record and retrieving it by unique ID."""
    test_id = "test-verif-text-001"
    evidence_data = [
        {"rank": 1, "page": "Mars_Water", "text": "Water ice is abundant at Mars polar ice caps."}
    ]
    canonical_dict = {
        "verification_id": test_id,
        "original_content_hash": "a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90",
        "primary_verdict": "LIKELY_GENUINE",
        "confidence_score": 0.92,
        "evidence_hashes": ["e1e2e3e4e5e6e7e8e9e0e1e2e3e4e5e6e7e8e9e0e1e2e3e4e5e6e7e8e9e0e1e2"],
        "timestamp": "2026-11-06T12:00:00Z",
        "schema_version": "1.0"
    }

    saved = save_verification_record(
        verification_id=test_id,
        content_type="text",
        title="Unit Test Text Claim",
        content_preview="NASA confirmed water ice on Mars surface.",
        original_content="NASA confirmed water ice on Mars surface during polar exploration missions.",
        verdict="LIKELY_GENUINE",
        confidence_score=0.92,
        explanation="Corroborated by reliable scientific documentation.",
        evidence_data=evidence_data,
        canonical_record_dict=canonical_dict,
        record_hash="1111222233334444555566667777888899990000aaaabbbbccccddddeeeeffff",
        blockchain_anchored=False,
        blockchain_status="unanchored"
    )
    assert saved is not None
    assert saved["verification_id"] == test_id

    retrieved = get_verification_record(test_id)
    assert retrieved is not None
    assert retrieved["verification_id"] == test_id
    assert retrieved["content_type"] == "text"
    assert retrieved["verdict"] == "LIKELY_GENUINE"
    assert retrieved["confidence_score"] == 0.92
    assert retrieved["blockchain_status"] == "unanchored"
    assert retrieved["blockchain_anchored"] is False
    assert len(retrieved["evidence"]) == 1
    assert retrieved["evidence"][0]["page"] == "Mars_Water"


def test_sqlite_update_blockchain_status():
    """Test updating blockchain anchoring status for a record."""
    test_id = "test-verif-update-002"
    canonical_dict = {
        "verification_id": test_id,
        "original_content_hash": "b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90a1",
        "primary_verdict": "UNVERIFIED",
        "confidence_score": 0.45,
        "evidence_hashes": [],
        "timestamp": "2026-11-06T12:05:00Z",
        "schema_version": "1.0"
    }
    save_verification_record(
        verification_id=test_id,
        content_type="article",
        title="Article To Anchor",
        content_preview="Breaking news report about economy.",
        original_content="Full article text detailing macroeconomic shifts.",
        verdict="UNVERIFIED",
        confidence_score=0.45,
        explanation="Insufficient verifiable sources in index.",
        evidence_data=[],
        canonical_record_dict=canonical_dict,
        record_hash="222233334444555566667777888899990000aaaabbbbccccddddeeeeffff1111",
        blockchain_anchored=False,
        blockchain_status="unanchored"
    )

    # Now update with mock tx receipt
    tx_hash = "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
    updated = update_blockchain_anchoring(
        verification_id=test_id,
        transaction_hash=tx_hash,
        contract_address="0xcDa4CE06d44642Fd0034C817B5b7cB6AFC886ffb",
        block_number=123456,
        block_timestamp=1762428000,
        block_datetime="2026-11-06T12:06:40Z",
        submitter_address="0x1111111111111111111111111111111111111111",
        gas_used=80000,
        network="sepolia",
        chain_id=11155111,
        etherscan_url=f"https://sepolia.etherscan.io/tx/{tx_hash}",
        status="confirmed"
    )
    assert updated is not None

    record = get_verification_record(test_id)
    assert record["blockchain_status"] == "confirmed"
    assert record["blockchain_anchored"] is True
    assert record["transaction_hash"] == tx_hash
    assert record["block_number"] == 123456
    assert record["gas_used"] == 80000


def test_sqlite_search_and_filtering():
    """Test filtering records by content_type, verdict, blockchain_status, and search keyword."""
    # List paginated records and confirm the original confirmed Sepolia record remains persisted
    records, total = list_verification_records(limit=100)
    assert total >= 1
    assert len(records) <= 100
    sepolia_hits, sepolia_total = list_verification_records(search="verif-9c524ca7b6f5", limit=10)
    assert sepolia_total == 1
    assert any(r["verification_id"] == "verif-9c524ca7b6f5" for r in sepolia_hits)

    # Filter by verdict: LIKELY_GENUINE
    genuine_records, genuine_total = list_verification_records(verdict="LIKELY_GENUINE")
    assert genuine_total >= 1
    for r in genuine_records:
        assert r["verdict"] == "LIKELY_GENUINE"

    # Filter by blockchain_status: confirmed
    confirmed_records, confirmed_total = list_verification_records(blockchain_status="confirmed")
    assert confirmed_total >= 1
    for r in confirmed_records:
        assert r["blockchain_status"] == "confirmed"

    # Search keyword
    searched, search_total = list_verification_records(search="Duggar")
    assert search_total >= 1
    assert any("Duggar" in ((r.get("title") or "") + (r.get("content_preview") or "")) for r in searched)

    # Search non-matching keyword
    empty_res, empty_total = list_verification_records(search="XYZNONEXISTENTSTRING999")
    assert empty_total == 0
    assert len(empty_res) == 0


# ==============================================================================
# 2. QR CODE & VERIFICATION CERTIFICATE TESTS
# ==============================================================================

def test_qr_code_generation():
    """Test generating a valid PNG QR code containing the verification URL."""
    qr_buf = generate_certificate_qr_code(
        verification_id="verif-test-qr",
        record_hash="42007960ae4bf66cbc74dfb24ef80429fdba86ca34de3bc1a8d0ff9c16a2cc53"
    )
    assert qr_buf is not None
    qr_bytes = qr_buf.getvalue()
    assert len(qr_bytes) > 100

    # Validate that it can be opened as an image
    img = Image.open(io.BytesIO(qr_bytes))
    assert img.format == "PNG"
    assert img.size[0] > 50 and img.size[1] > 50


def test_pdf_generation_confirmed_record():
    """Test generating an official vector PDF certificate for a confirmed record."""
    # verif-9c524ca7b6f5 is confirmed on-chain
    pdf_bytes = generate_verification_pdf("verif-9c524ca7b6f5")
    assert pdf_bytes is not None
    assert len(pdf_bytes) > 5000
    # Must start with standard PDF magic header
    assert pdf_bytes.startswith(b"%PDF-")


def test_pdf_generation_unanchored_record_rejected():
    """Test that generating a PDF for an unanchored record is strictly rejected with ValueError."""
    # test-verif-text-001 is unanchored
    with pytest.raises(ValueError) as excinfo:
        generate_verification_pdf("test-verif-text-001")
    assert "not confirmed on the blockchain" in str(excinfo.value)


def test_pdf_generation_nonexistent_record_rejected():
    """Test that generating a PDF for a nonexistent record raises ValueError."""
    with pytest.raises(ValueError) as excinfo:
        generate_verification_pdf("nonexistent-record-id-xyz")
    assert "does not exist" in str(excinfo.value)


# ==============================================================================
# 3. FASTAPI ROUTE TESTS: CERTIFICATES & AUDIT
# ==============================================================================

def test_api_download_certificate_confirmed():
    """Test GET /api/v1/certificates/{id}/download returns 200 and PDF bytes."""
    response = client.get("/api/v1/certificates/verif-9c524ca7b6f5/download")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "FakeNewsBlockchain_Certificate_verif-9c524ca7b6f5.pdf" in response.headers.get("content-disposition", "")
    assert response.content.startswith(b"%PDF-")


def test_api_download_certificate_unanchored_400():
    """Test GET /api/v1/certificates/{id}/download rejects unanchored record with 400."""
    response = client.get("/api/v1/certificates/test-verif-text-001/download")
    assert response.status_code == 400
    assert "not confirmed on the blockchain" in response.json()["detail"]


def test_api_public_certificate_verify_match():
    """Test POST /api/v1/certificates/verify with correct hash returns MATCH and authentic=True."""
    payload = {
        "verification_id": "verif-9c524ca7b6f5",
        "record_hash": "42007960ae4bf66cbc74dfb24ef80429fdba86ca34de3bc1a8d0ff9c16a2cc53"
    }
    response = client.post("/api/v1/certificates/verify", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "MATCH"
    assert data["is_authentic"] is True
    assert data["verification_id"] == "verif-9c524ca7b6f5"
    assert data["contract_address"] == "0xcDa4CE06d44642Fd0034C817B5b7cB6AFC886ffb"
    assert "CERTIFICATE VERIFIED AUTHENTIC" in data["message"]


def test_api_public_certificate_verify_mismatch_tampered():
    """Test POST /api/v1/certificates/verify with tampered hash returns MISMATCH and authentic=False."""
    payload = {
        "verification_id": "verif-9c524ca7b6f5",
        "record_hash": "bad0bad0bad0bad0bad0bad0bad0bad0bad0bad0bad0bad0bad0bad0bad0bad0"
    }
    response = client.post("/api/v1/certificates/verify", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "MISMATCH"
    assert data["is_authentic"] is False
    assert "CRITICAL TAMPERING DETECTED" in data["message"]


def test_api_public_certificate_verify_not_found():
    """Test POST /api/v1/certificates/verify with nonexistent ID returns NOT_FOUND."""
    payload = {
        "verification_id": "nonexistent-id-99999"
    }
    response = client.post("/api/v1/certificates/verify", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "NOT_FOUND"
    assert data["is_authentic"] is False
    assert "No on-chain record found" in data["message"]


def test_api_blockchain_audit_list():
    """Test GET /api/v1/blockchain/audit returns network metadata and anchored records."""
    response = client.get("/api/v1/blockchain/audit")
    assert response.status_code == 200
    data = response.json()
    assert data["network"] in ["sepolia", "localhost", "hardhat"]
    assert data["chain_id"] in [11155111, 31337]
    assert data["contract_deployed"] is True
    assert data["total_records"] >= 1
    assert any(r["verification_id"] == "verif-9c524ca7b6f5" for r in data["records"])


def test_api_blockchain_audit_compare_match():
    """Test GET /api/v1/blockchain/audit/{id}/compare compares local hash to on-chain anchor."""
    response = client.get("/api/v1/blockchain/audit/verif-9c524ca7b6f5/compare")
    assert response.status_code == 200
    data = response.json()
    assert data["verification_id"] == "verif-9c524ca7b6f5"
    assert data["matched"] is True
    assert data["status"] == "VERIFIED_MATCH"
    assert data["local_hash"] == data["on_chain_hash"]


def test_api_history_endpoints():
    """Test GET /api/v1/history and GET /api/v1/history/{id}."""
    # 1. List
    res = client.get("/api/v1/history?limit=10")
    assert res.status_code == 200
    data = res.json()
    assert "total" in data
    assert "records" in data
    assert len(data["records"]) >= 1

    # 2. Get Single
    detail_res = client.get("/api/v1/history/verif-9c524ca7b6f5")
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["verification_id"] == "verif-9c524ca7b6f5"
    assert detail["verdict"] == "LIKELY_GENUINE"
    assert detail["blockchain_status"] == "confirmed"

    # 3. Get 404 for missing
    missing_res = client.get("/api/v1/history/does-not-exist-12345")
    assert missing_res.status_code == 404
