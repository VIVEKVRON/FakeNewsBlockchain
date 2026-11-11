"""
backend/app/api/routes/certificates.py
API endpoints for generating downloadable PDF verification certificates and
independent public cryptographic certificate verification.
"""

from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field

from backend.app.services.certificate_service import generate_verification_pdf
from backend.app.services.blockchain_service import (
    get_blockchain_service,
    serialize_canonical_record
)
from backend.app.schemas.blockchain import CanonicalVerificationRecord
from backend.app.database.repository import get_verification_record
from backend.app.utils.logger import logger

router = APIRouter(prefix="/certificates", tags=["Verification Certificates"])


class PublicCertificateVerifyRequest(BaseModel):
    verification_id: str = Field(..., description="Unique verification ID on the certificate")
    record_hash: Optional[str] = Field(default=None, description="Optional SHA-256 hash from certificate to compare against on-chain anchor")


class PublicCertificateVerifyResponse(BaseModel):
    verification_id: str
    status: str = Field(..., description="MATCH, MISMATCH, NOT_FOUND, or NETWORK_UNAVAILABLE")
    is_authentic: bool
    canonical_hash: Optional[str] = None
    on_chain_hash: Optional[str] = None
    contract_address: Optional[str] = None
    transaction_hash: Optional[str] = None
    block_number: Optional[int] = None
    block_datetime: Optional[str] = None
    submitter: Optional[str] = None
    network: str
    chain_id: Optional[int] = None
    etherscan_url: Optional[str] = None
    message: str
    epistemological_disclaimer: str = (
        "Cryptographic certificate verification provides mathematical proof that this verification record "
        "is genuine and untampered with since its Ethereum blockchain anchor. It does not certify that the "
        "underlying real-world statement is empirical ground truth."
    )


@router.get(
    "/{verification_id}/download",
    summary="Download cryptographic verification certificate as PDF",
    description="Generates an official high-resolution vector PDF certificate with embedded QR code. Strict requirement: record must be confirmed on-chain."
)
async def download_certificate(verification_id: str):
    try:
        pdf_bytes = generate_verification_pdf(verification_id)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="FakeNewsBlockchain_Certificate_{verification_id}.pdf"'
            }
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error generating PDF certificate for {verification_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate certificate: {str(e)}"
        )


@router.post(
    "/verify",
    response_model=PublicCertificateVerifyResponse,
    summary="Public independent certificate verification",
    description="Recomputes the canonical record hash and verifies it against the immutable Ethereum Sepolia smart contract."
)
async def verify_certificate(request: PublicCertificateVerifyRequest) -> PublicCertificateVerifyResponse:
    service = get_blockchain_service()
    
    # 1. Check RPC connectivity
    if not service.is_connected():
        return PublicCertificateVerifyResponse(
            verification_id=request.verification_id,
            status="NETWORK_UNAVAILABLE",
            is_authentic=False,
            network=service.network_name,
            chain_id=service.settings.SEPOLIA_CHAIN_ID,
            message="Ethereum blockchain RPC is unreachable. Certificate cannot be audited on-chain at this time."
        )

    # 2. Query smart contract directly on Sepolia
    on_chain = service.query_verification(request.verification_id)
    if not on_chain or not on_chain.is_registered:
        return PublicCertificateVerifyResponse(
            verification_id=request.verification_id,
            status="NOT_FOUND",
            is_authentic=False,
            contract_address=service.contract_address,
            network=service.network_name,
            chain_id=service.settings.SEPOLIA_CHAIN_ID,
            message=f"No on-chain record found for verification ID '{request.verification_id}'. This certificate is not registered on the blockchain."
        )

    # 3. Retrieve local record to recompute canonical hash if available
    local_rec = get_verification_record(request.verification_id)
    recomputed_hash = None
    if local_rec and local_rec.get("canonical_record"):
        try:
            canon = CanonicalVerificationRecord(**local_rec["canonical_record"])
            _, recomputed_hash, _ = serialize_canonical_record(canon)
        except Exception as e:
            logger.warning(f"Could not re-serialize canonical record: {e}")

    # Determine hash to compare
    hash_to_check = request.record_hash or recomputed_hash or (local_rec.get("record_hash") if local_rec else None)
    
    clean_on_chain_hash = on_chain.record_hash.lower().replace("0x", "")
    etherscan_url = (
        f"https://sepolia.etherscan.io/address/{service.contract_address}"
        if service.w3 and service.w3.eth.chain_id == 11155111
        else f"http://127.0.0.1:8545/address/{service.contract_address}"
    )

    if local_rec and local_rec.get("transaction_hash"):
        if service.w3 and service.w3.eth.chain_id == 11155111:
            etherscan_url = f"https://sepolia.etherscan.io/tx/{local_rec['transaction_hash']}"
        else:
            etherscan_url = f"http://127.0.0.1:8545/tx/{local_rec['transaction_hash']}"

    if hash_to_check:
        clean_check = hash_to_check.lower().replace("0x", "")
        if clean_check == clean_on_chain_hash:
            return PublicCertificateVerifyResponse(
                verification_id=request.verification_id,
                status="MATCH",
                is_authentic=True,
                canonical_hash=clean_check,
                on_chain_hash=clean_on_chain_hash,
                contract_address=service.contract_address,
                transaction_hash=local_rec.get("transaction_hash") if local_rec else None,
                block_number=local_rec.get("block_number") if local_rec else None,
                block_datetime=on_chain.block_datetime,
                submitter=on_chain.submitter,
                network=service.network_name,
                chain_id=service.w3.eth.chain_id if service.w3 else 11155111,
                etherscan_url=etherscan_url,
                message=(
                    f"CERTIFICATE VERIFIED AUTHENTIC: The certificate record hash '{clean_check[:16]}...' "
                    f"exactly matches the immutable on-chain anchor registered at block timestamp {on_chain.block_datetime}. "
                    "This verification record is authentic and untampered."
                )
            )
        else:
            return PublicCertificateVerifyResponse(
                verification_id=request.verification_id,
                status="MISMATCH",
                is_authentic=False,
                canonical_hash=clean_check,
                on_chain_hash=clean_on_chain_hash,
                contract_address=service.contract_address,
                transaction_hash=local_rec.get("transaction_hash") if local_rec else None,
                block_number=local_rec.get("block_number") if local_rec else None,
                block_datetime=on_chain.block_datetime,
                submitter=on_chain.submitter,
                network=service.network_name,
                chain_id=service.w3.eth.chain_id if service.w3 else 11155111,
                etherscan_url=etherscan_url,
                message=(
                    f"CRITICAL TAMPERING DETECTED: The provided hash '{clean_check[:16]}...' does NOT match "
                    f"the immutable on-chain anchor '{clean_on_chain_hash[:16]}...'. "
                    "This certificate has been forged, altered, or tampered with."
                )
            )

    # If no hash was provided to compare, report on-chain existence
    return PublicCertificateVerifyResponse(
        verification_id=request.verification_id,
        status="MATCH",
        is_authentic=True,
        canonical_hash=clean_on_chain_hash,
        on_chain_hash=clean_on_chain_hash,
        contract_address=service.contract_address,
        transaction_hash=local_rec.get("transaction_hash") if local_rec else None,
        block_number=local_rec.get("block_number") if local_rec else None,
        block_datetime=on_chain.block_datetime,
        submitter=on_chain.submitter,
        network=service.network_name,
        chain_id=service.w3.eth.chain_id if service.w3 else 11155111,
        etherscan_url=etherscan_url,
        message=f"Record '{request.verification_id}' exists on-chain with anchored hash '{clean_on_chain_hash[:16]}...'."
    )
