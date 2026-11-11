"""
backend/app/schemas/blockchain.py
Pydantic schemas for blockchain cryptographic anchoring, canonical verification records,
and on-chain integrity verification.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from pydantic import BaseModel, Field, field_validator


class CanonicalVerificationRecord(BaseModel):
    """
    Deterministic canonical verification record used to produce the SHA-256 hash.
    Serialized strictly with sorted keys and no extraneous whitespace (separators=(',', ':')).
    """
    schema_version: str = Field(default="1.0", description="Schema version of the canonical record")
    verification_id: str = Field(..., description="Unique verification identifier")
    original_content_hash: str = Field(..., description="SHA-256 hash (64 hex characters) of input text/claim/article")
    primary_verdict: str = Field(..., description="Primary verdict string (e.g. LIKELY_GENUINE, LIKELY_FAKE, MISLEADING, UNVERIFIED)")
    confidence_score: float = Field(..., description="Confidence score rounded to 4 decimal places")
    evidence_hashes: List[str] = Field(default_factory=list, description="Array of SHA-256 hashes of individual evidence sentences")
    timestamp: str = Field(..., description="ISO 8601 UTC timestamp string")

    @field_validator("original_content_hash")
    @classmethod
    def validate_hash_format(cls, v: str) -> str:
        clean = v.strip().lower()
        if len(clean) == 64 and all(c in "0123456789abcdef" for c in clean):
            return clean
        raise ValueError("original_content_hash must be a 64-character hex string.")


class VerificationHashSummary(BaseModel):
    """
    Cryptographic hash summary attached to verification responses or verification exports.
    """
    schema_version: str = "1.0"
    verification_id: str
    canonical_record: CanonicalVerificationRecord
    canonical_json: str = Field(..., description="Canonical deterministic JSON string")
    record_hash: str = Field(..., description="Deterministic SHA-256 hex digest of the canonical JSON (64 chars)")
    record_hash_bytes32: str = Field(..., description="Ethereum bytes32 representation (0x prefixed 64 chars)")
    blockchain_anchored: bool = Field(default=False, description="Whether this record is already registered on-chain")
    network: Optional[str] = Field(default=None, description="Blockchain network name if registered")
    transaction_hash: Optional[str] = Field(default=None, description="Ethereum transaction hash if registered")
    contract_address: Optional[str] = Field(default=None, description="Smart contract address")


class OnChainRecordDetails(BaseModel):
    verification_id: str
    record_hash: str
    record_hash_bytes32: str
    submitter: str
    block_timestamp: int
    block_datetime: str
    is_registered: bool


class VerifyHashRequest(BaseModel):
    verification_id: str = Field(..., description="Unique verification ID to query on-chain")
    record_hash: Optional[str] = Field(default=None, description="Optional SHA-256 hash to compare against on-chain anchor")


class VerifyHashResponse(BaseModel):
    verification_id: str
    is_registered_on_chain: bool
    hash_matched: Optional[bool] = None
    on_chain_record: Optional[OnChainRecordDetails] = None
    network: str
    contract_address: Optional[str] = None
    integrity_status: str = Field(..., description="VERIFIED_TAMPER_FREE, HASH_MISMATCH_TAMPERED, NOT_FOUND_ON_CHAIN, or RPC_UNAVAILABLE")
    explanation: str


class BlockchainStatusResponse(BaseModel):
    enabled: bool
    connected: bool
    network: str
    chain_id: Optional[int] = None
    contract_address: Optional[str] = None
    contract_deployed: bool = False
    is_paused: Optional[bool] = None
    owner: Optional[str] = None
    total_verifications: Optional[int] = None
    latest_block: Optional[int] = None
    rpc_endpoint_configured: bool = False
    epistemological_disclaimer: str = (
        "The Ethereum smart contract anchors cryptographic SHA-256 hashes of verification records. "
        "It provides immutable mathematical proof of record integrity and non-repudiation (proving that a specific "
        "AI verification result was produced and not tampered with), NOT that the underlying claim or AI verdict "
        "is infallible empirical truth."
    )


class AnchorVerificationRequest(BaseModel):
    verification_id: str = Field(..., description="Unique verification identifier (e.g. verif-... or art-...)")
    record_hash: str = Field(..., description="Deterministic SHA-256 hex digest (64 chars) of the canonical record")
    canonical_record: Optional[CanonicalVerificationRecord] = Field(
        default=None,
        description="Optional canonical verification record to re-verify hash before submission"
    )

    @field_validator("record_hash")
    @classmethod
    def validate_record_hash(cls, v: str) -> str:
        clean = v.strip().lower().replace("0x", "")
        if len(clean) == 64 and all(c in "0123456789abcdef" for c in clean):
            return clean
        raise ValueError("record_hash must be a 64-character hex string.")


class AnchorVerificationResponse(BaseModel):
    success: bool
    verification_id: str
    record_hash: str
    transaction_hash: Optional[str] = None
    contract_address: str
    block_number: Optional[int] = None
    block_timestamp: Optional[int] = None
    block_datetime: Optional[str] = None
    submitter_address: Optional[str] = None
    gas_used: Optional[int] = None
    network: str
    chain_id: int
    etherscan_url: Optional[str] = None
    already_registered: bool = False
    message: str
    epistemological_disclaimer: str = (
        "The on-chain transaction anchors the cryptographic SHA-256 hash of this verification record. "
        "It guarantees record integrity and non-repudiation (proof that this exact AI result was issued "
        "at this block height without subsequent tampering). It is NOT proof that the underlying claim is true."
    )

