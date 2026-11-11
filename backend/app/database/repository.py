"""
backend/app/database/repository.py
Repository operations for verification records, audit explorer queries, and on-chain syncing.
"""

import json
import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone

from backend.app.database.connection import get_db_connection

logger = logging.getLogger(__name__)


def save_verification_record(
    verification_id: str,
    content_type: str,
    title: Optional[str],
    content_preview: str,
    original_content: str,
    verdict: str,
    confidence_score: float,
    explanation: str,
    evidence_data: Any,
    canonical_record_dict: Dict[str, Any],
    record_hash: str,
    blockchain_anchored: bool = False,
    blockchain_status: str = "unanchored",
    network: Optional[str] = None,
    chain_id: Optional[int] = None,
    contract_address: Optional[str] = None,
    transaction_hash: Optional[str] = None,
    block_number: Optional[int] = None,
    block_timestamp: Optional[int] = None,
    block_datetime: Optional[str] = None,
    submitter_address: Optional[str] = None,
    gas_used: Optional[int] = None,
    etherscan_url: Optional[str] = None,
    created_at: Optional[str] = None
) -> Dict[str, Any]:
    """
    Saves or updates a verification record in SQLite.
    Prevents overwriting confirmed blockchain fields if already anchored.
    """
    now = datetime.now(timezone.utc).isoformat()
    if created_at is None:
        created_at = now

    evidence_json = json.dumps(evidence_data) if evidence_data is not None else None
    canonical_json = json.dumps(canonical_record_dict, sort_keys=True, separators=(",", ":"))

    with get_db_connection() as conn:
        # Check if record already exists
        cur = conn.cursor()
        cur.execute("SELECT verification_id, blockchain_status FROM verification_records WHERE verification_id = ?", (verification_id,))
        existing = cur.fetchone()

        if existing:
            # If already confirmed, don't revert to unanchored
            status_to_save = existing["blockchain_status"] if existing["blockchain_status"] == "confirmed" else blockchain_status
            anchored_val = 1 if status_to_save == "confirmed" else (1 if blockchain_anchored else 0)

            cur.execute("""
                UPDATE verification_records SET
                    content_type = ?,
                    title = COALESCE(?, title),
                    content_preview = ?,
                    original_content = ?,
                    verdict = ?,
                    confidence_score = ?,
                    explanation = ?,
                    evidence_json = ?,
                    canonical_record_json = ?,
                    record_hash = ?,
                    blockchain_anchored = ?,
                    blockchain_status = ?,
                    network = COALESCE(?, network),
                    chain_id = COALESCE(?, chain_id),
                    contract_address = COALESCE(?, contract_address),
                    transaction_hash = COALESCE(?, transaction_hash),
                    block_number = COALESCE(?, block_number),
                    block_timestamp = COALESCE(?, block_timestamp),
                    block_datetime = COALESCE(?, block_datetime),
                    submitter_address = COALESCE(?, submitter_address),
                    gas_used = COALESCE(?, gas_used),
                    etherscan_url = COALESCE(?, etherscan_url),
                    updated_at = ?
                WHERE verification_id = ?
            """, (
                content_type, title, content_preview, original_content,
                verdict, confidence_score, explanation, evidence_json,
                canonical_json, record_hash, anchored_val, status_to_save,
                network, chain_id, contract_address, transaction_hash,
                block_number, block_timestamp, block_datetime,
                submitter_address, gas_used, etherscan_url,
                now, verification_id
            ))
        else:
            cur.execute("""
                INSERT INTO verification_records (
                    verification_id, content_type, title, content_preview,
                    original_content, verdict, confidence_score, explanation,
                    evidence_json, canonical_record_json, record_hash,
                    blockchain_anchored, blockchain_status, network, chain_id,
                    contract_address, transaction_hash, block_number,
                    block_timestamp, block_datetime, submitter_address,
                    gas_used, etherscan_url, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                verification_id, content_type, title, content_preview,
                original_content, verdict, confidence_score, explanation,
                evidence_json, canonical_json, record_hash,
                1 if blockchain_anchored or blockchain_status == "confirmed" else 0,
                blockchain_status, network, chain_id, contract_address,
                transaction_hash, block_number, block_timestamp,
                block_datetime, submitter_address, gas_used,
                etherscan_url, created_at, now
            ))

    return get_verification_record(verification_id)


def update_blockchain_anchoring(
    verification_id: str,
    transaction_hash: str,
    contract_address: str,
    block_number: int,
    block_timestamp: int,
    block_datetime: str,
    submitter_address: str,
    gas_used: int,
    network: str,
    chain_id: int,
    etherscan_url: str,
    status: str = "confirmed"
) -> Optional[Dict[str, Any]]:
    """Updates blockchain anchoring status and transaction receipts after confirmation."""
    now = datetime.now(timezone.utc).isoformat()
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE verification_records SET
                blockchain_anchored = 1,
                blockchain_status = ?,
                transaction_hash = ?,
                contract_address = ?,
                block_number = ?,
                block_timestamp = ?,
                block_datetime = ?,
                submitter_address = ?,
                gas_used = ?,
                network = ?,
                chain_id = ?,
                etherscan_url = ?,
                updated_at = ?
            WHERE verification_id = ?
        """, (
            status, transaction_hash, contract_address, block_number,
            block_timestamp, block_datetime, submitter_address, gas_used,
            network, chain_id, etherscan_url, now, verification_id
        ))

    return get_verification_record(verification_id)


def get_verification_record(verification_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves a single verification record by unique ID."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM verification_records WHERE verification_id = ?", (verification_id,))
        row = cur.fetchone()
        if not row:
            return None
        return _format_record(dict(row))


def list_verification_records(
    content_type: Optional[str] = None,
    verdict: Optional[str] = None,
    blockchain_status: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    sort_by: str = "created_at",
    order: str = "desc"
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Queries paginated verification records with multi-field filtering and keyword search.
    Returns (records_list, total_matching_count).
    """
    conditions = []
    params = []

    if content_type and content_type.lower() != "all":
        conditions.append("content_type = ?")
        params.append(content_type.lower())

    if verdict and verdict.upper() != "ALL":
        v_up = verdict.upper()
        if v_up == "GENUINE":
            conditions.append("verdict IN ('GENUINE', 'LIKELY_GENUINE')")
        elif v_up == "FAKE":
            conditions.append("verdict IN ('FAKE', 'LIKELY_FAKE')")
        else:
            conditions.append("verdict = ?")
            params.append(v_up)

    if blockchain_status and blockchain_status.lower() != "all":
        conditions.append("blockchain_status = ?")
        params.append(blockchain_status.lower())

    if search and search.strip():
        term = f"%{search.strip()}%"
        conditions.append("(verification_id LIKE ? OR title LIKE ? OR content_preview LIKE ? OR transaction_hash LIKE ? OR record_hash LIKE ?)")
        params.extend([term, term, term, term, term])

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    # Validate sort column to avoid SQL injection
    valid_sorts = {
        "created_at": "created_at",
        "confidence_score": "confidence_score",
        "verdict": "verdict",
        "block_number": "block_number"
    }
    sort_col = valid_sorts.get(sort_by, "created_at")
    sort_dir = "ASC" if order.lower() == "asc" else "DESC"

    with get_db_connection() as conn:
        cur = conn.cursor()

        # Count total
        count_sql = f"SELECT COUNT(*) AS total FROM verification_records {where_clause}"
        cur.execute(count_sql, params)
        total = cur.fetchone()["total"]

        # Fetch page
        query_sql = f"""
            SELECT * FROM verification_records
            {where_clause}
            ORDER BY {sort_col} {sort_dir}
            LIMIT ? OFFSET ?
        """
        cur.execute(query_sql, params + [limit, offset])
        rows = cur.fetchall()

        records = [_format_record(dict(r)) for r in rows]
        return records, total


def list_audit_records() -> List[Dict[str, Any]]:
    """Returns all records with on-chain transactions for the Blockchain Audit Explorer."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT * FROM verification_records
            WHERE transaction_hash IS NOT NULL OR blockchain_status = 'confirmed'
            ORDER BY block_number DESC, created_at DESC
        """)
        rows = cur.fetchall()
        return [_format_record(dict(r)) for r in rows]


def _format_record(row_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Parses JSON columns into Python objects for serialization."""
    if row_dict.get("evidence_json"):
        try:
            row_dict["evidence"] = json.loads(row_dict["evidence_json"])
        except Exception:
            row_dict["evidence"] = []
    else:
        row_dict["evidence"] = []

    if row_dict.get("canonical_record_json"):
        try:
            row_dict["canonical_record"] = json.loads(row_dict["canonical_record_json"])
        except Exception:
            row_dict["canonical_record"] = None
    else:
        row_dict["canonical_record"] = None

    row_dict["blockchain_anchored"] = bool(row_dict.get("blockchain_anchored"))
    return row_dict


def seed_confirmed_sepolia_record_if_empty():
    """
    Ensures that our live Sepolia transaction (block #12076191) is preserved in SQLite
    if the database is initialized freshly.
    """
    sepolia_id = "verif-9c524ca7b6f5"
    existing = get_verification_record(sepolia_id)
    if not existing:
        save_verification_record(
            verification_id=sepolia_id,
            content_type="text",
            title="Duggar Family Reality Show Claim",
            content_preview="19 Kids and Counting is an American reality television show featuring the Duggar family.",
            original_content="19 Kids and Counting is an American reality television show featuring the Duggar family.",
            verdict="LIKELY_GENUINE",
            confidence_score=0.87,
            explanation="Claim corroborated by FEVER Wikipedia knowledge base. DeBERTa NLI predicts high entailment.",
            evidence_data=[
                {"rank": 1, "page": "19_Kids_and_Counting", "text": "19 Kids and Counting is an American reality television show that aired on the cable channel TLC for seven seasons."},
                {"rank": 2, "page": "19_Kids_and_Counting", "text": "The show features the Duggar family: parents Jim Bob and Michelle Duggar and their 19 children."}
            ],
            canonical_record_dict={
                "schema_version": "1.0",
                "verification_id": sepolia_id,
                "original_content_hash": "82fade398e2ccb1311c00df331885dd0a151b7cf98aa4dc794b8ccb974553ad9",
                "primary_verdict": "LIKELY_GENUINE",
                "confidence_score": 0.87,
                "evidence_hashes": [
                    "0bebdb7e50a509b28fd9b94753a8c5f71ee2e3fcbc772b8371aa72187844e2fb",
                    "70c04bf23b5b5c49333dfd0e53b63ba3d89ecea12967ed276f76764f78123fa1",
                    "7f70f21c05ac7ba33ab2252ca074d650108fb07eb4fc9183f57ba96ffe14223c"
                ],
                "timestamp": "2026-11-06T11:12:22.475564+00:00"
            },
            record_hash="42007960ae4bf66cbc74dfb24ef80429fdba86ca34de3bc1a8d0ff9c16a2cc53",
            blockchain_anchored=True,
            blockchain_status="confirmed",
            network="sepolia",
            chain_id=11155111,
            contract_address="0xcDa4CE06d44642Fd0034C817B5b7cB6AFC886ffb",
            transaction_hash="0x8ba191c38e155af5e69c4dbf949f8eda1cf3cdb63fdb35641ced5129386f8941",
            block_number=12076191,
            block_timestamp=1793963544,
            block_datetime="2026-11-06T11:12:24+00:00",
            submitter_address="0x85357b97fA45f09743e289D3366A5936F044e57E",
            gas_used=794658,
            etherscan_url="https://sepolia.etherscan.io/tx/0x8ba191c38e155af5e69c4dbf949f8eda1cf3cdb63fdb35641ced5129386f8941",
            created_at="2026-11-06T11:12:22.475564+00:00"
        )
        logger.info("Preserved live Sepolia anchor record %s in SQLite database", sepolia_id)
