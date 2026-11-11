"""
backend/app/api/routes/blockchain.py
API endpoints for blockchain status, canonical record hashing, and on-chain verification.
"""

from fastapi import APIRouter, HTTPException, status
from backend.app.schemas.blockchain import (
    BlockchainStatusResponse,
    VerifyHashRequest,
    VerifyHashResponse,
    OnChainRecordDetails,
    VerificationHashSummary,
    AnchorVerificationRequest,
    AnchorVerificationResponse
)
from backend.app.services.blockchain_service import (
    get_blockchain_service,
    build_canonical_record
)
from backend.app.utils.logger import logger

router = APIRouter(prefix="/blockchain", tags=["Blockchain"])


@router.get(
    "/status",
    response_model=BlockchainStatusResponse,
    summary="Get blockchain connection and smart contract status",
    description="Returns current RPC connectivity, network ID, deployed contract address, paused state, and total anchored verification count."
)
async def get_blockchain_status() -> BlockchainStatusResponse:
    service = get_blockchain_service()
    return service.get_status()


@router.get(
    "/records/{verification_id}",
    response_model=OnChainRecordDetails,
    summary="Get anchored verification record by ID",
    description="Queries the VerificationRegistry smart contract directly to retrieve the immutable record hash, submitter, and block timestamp."
)
async def get_on_chain_record(verification_id: str) -> OnChainRecordDetails:
    service = get_blockchain_service()
    record = service.query_verification(verification_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Verification ID '{verification_id}' is not anchored on the blockchain."
        )
    return record


@router.post(
    "/verify-hash",
    response_model=VerifyHashResponse,
    summary="Verify cryptographic integrity of a verification record",
    description="Compares a locally computed or provided SHA-256 record hash against the immutable on-chain anchor to detect tampering."
)
async def verify_record_hash(request: VerifyHashRequest) -> VerifyHashResponse:
    service = get_blockchain_service()
    return service.verify_hash_integrity(
        verification_id=request.verification_id,
        provided_record_hash=request.record_hash
    )


@router.post(
    "/anchor",
    response_model=AnchorVerificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Anchor verification record to Ethereum blockchain",
    description="Submits the canonical verification record hash to the VerificationRegistry smart contract, waits for receipt confirmation, and returns the transaction details."
)
async def anchor_verification(request: AnchorVerificationRequest) -> AnchorVerificationResponse:
    try:
        service = get_blockchain_service()
        response = service.anchor_verification(request)
        return response
    except ValueError as e:
        logger.warning(f"Validation failure during anchoring: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except ConnectionError as e:
        logger.error(f"Blockchain connection error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )
    except TimeoutError as e:
        logger.error(f"Blockchain transaction confirmation timeout: {e}")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=str(e)
        )
    except RuntimeError as e:
        logger.error(f"Blockchain runtime error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error during blockchain anchoring: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal blockchain error: {str(e)}"
        )


@router.get(
    "/audit",
    summary="List all anchored records for the Blockchain Audit Explorer",
    description="Retrieves all verification records with blockchain transactions, including block number, gas used, submitter, and Etherscan link."
)
async def get_audit_explorer_records():
    from backend.app.database.repository import list_audit_records
    records = list_audit_records()
    service = get_blockchain_service()
    status_info = service.get_status()
    return {
        "network": status_info.network,
        "chain_id": status_info.chain_id,
        "contract_address": status_info.contract_address,
        "contract_deployed": status_info.contract_deployed,
        "total_records": len(records),
        "records": records
    }


@router.get(
    "/audit/{verification_id}/compare",
    summary="Live on-chain comparison for audit verification",
    description="Compares the local SQLite record hash against the deployed Sepolia smart contract to detect tampering."
)
async def compare_on_chain_audit(verification_id: str):
    from backend.app.database.repository import get_verification_record
    local_rec = get_verification_record(verification_id)
    if not local_rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Verification record '{verification_id}' not found."
        )

    service = get_blockchain_service()
    if not service.is_connected():
        return {
            "verification_id": verification_id,
            "status": "RPC_UNAVAILABLE",
            "matched": None,
            "explanation": "Ethereum blockchain RPC is unreachable."
        }

    on_chain = service.query_verification(verification_id)
    if not on_chain or not on_chain.is_registered:
        return {
            "verification_id": verification_id,
            "status": "NOT_FOUND_ON_CHAIN",
            "matched": False,
            "explanation": f"Record '{verification_id}' has not been anchored to the smart contract."
        }

    local_hash = local_rec.get("record_hash", "").lower().replace("0x", "")
    on_chain_hash = on_chain.record_hash.lower().replace("0x", "")
    matched = (local_hash == on_chain_hash)

    return {
        "verification_id": verification_id,
        "status": "VERIFIED_MATCH" if matched else "TAMPERED_MISMATCH",
        "matched": matched,
        "local_hash": local_hash,
        "on_chain_hash": on_chain_hash,
        "submitter": on_chain.submitter,
        "block_timestamp": on_chain.block_timestamp,
        "block_datetime": on_chain.block_datetime,
        "contract_address": service.contract_address,
        "transaction_hash": local_rec.get("transaction_hash"),
        "etherscan_url": local_rec.get("etherscan_url"),
        "explanation": (
            "Cryptographic match verified! Local hash exactly matches on-chain anchor."
            if matched
            else "CRITICAL TAMPERING DETECTED: Local record hash does not match immutable on-chain record!"
        )
    }


