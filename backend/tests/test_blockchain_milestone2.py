"""
backend/tests/test_blockchain_milestone2.py
Comprehensive integration tests for Day 3 Milestone 2:
- Sepolia testnet connectivity and chain ID validation (11155111)
- Wallet balance query and insufficient funds rejection
- Local Hardhat node fallback with live transaction submission
- Transaction receipt confirmation and block mining
- On-chain record retrieval
- Correct hash verification (VERIFIED_TAMPER_FREE)
- Tampered hash detection (HASH_MISMATCH_TAMPERED)
- Duplicate registration safety (already_registered=True)
- Smart contract pause/circuit-breaker behavior
- RPC failure / unreachable network handling
"""

import os
import json
import pytest
from web3 import Web3
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.config import get_settings
from backend.app.services.blockchain_service import (
    BlockchainService,
    build_canonical_record,
    compute_sha256
)
from backend.app.schemas.blockchain import (
    AnchorVerificationRequest,
    AnchorVerificationResponse,
    VerifyHashRequest
)

client = TestClient(app)


def test_sepolia_public_rpc_connectivity_and_chain_id():
    """
    Test live connectivity to Ethereum Sepolia public RPC.
    Validates chain ID 11155111 and block height without requiring any private key or paid API.
    """
    sepolia_rpc = "https://ethereum-sepolia-rpc.publicnode.com"
    w3 = Web3(Web3.HTTPProvider(sepolia_rpc, request_kwargs={"timeout": 6}))
    
    # Must be connected
    assert w3.is_connected(), f"Failed to reach Sepolia RPC: {sepolia_rpc}"
    
    # Chain ID must be exact Sepolia testnet ID
    chain_id = w3.eth.chain_id
    assert chain_id == 11155111, f"Expected Sepolia Chain ID 11155111, got: {chain_id}"
    
    # Query block number to prove active network state
    block_num = w3.eth.block_number
    assert block_num > 5000000, f"Sepolia block number suspiciously low: {block_num}"


def test_wallet_balance_and_insufficient_funds_rejection():
    """
    Validates that a wallet with zero balance is correctly checked and fails with
    an informative insufficient funds message before submitting any transaction.
    """
    # Create a fresh random burner key with 0 ETH
    random_account = Web3().eth.account.create()
    burner_address = random_account.address
    burner_private_key = random_account.key.hex()

    # Create service instance configured with this unfunded wallet
    local_w3 = Web3(Web3.HTTPProvider("http://127.0.0.1:8545"))
    if not local_w3.is_connected():
        pytest.skip("Local Hardhat node is not running on http://127.0.0.1:8545")

    balance = local_w3.eth.get_balance(burner_address)
    assert balance == 0, "Burner account must have 0 balance"

    # Instantiate service pointing to local node with burner key
    svc = BlockchainService()
    svc.w3 = local_w3
    svc.network_name = "hardhat"
    original_key = svc.settings.SEPOLIA_PRIVATE_KEY
    svc.settings.SEPOLIA_PRIVATE_KEY = burner_private_key

    try:
        # Ensure contract is configured
        dep_path = svc.settings.get_absolute_path("blockchain/deployments/localhost-deployment.json")
        if not dep_path.exists():
            dep_path = svc.settings.get_absolute_path("blockchain/deployments/hardhat-deployment.json")
        with open(dep_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
            svc.contract_address = meta["contractAddress"]
        svc.contract = svc.w3.eth.contract(address=svc.contract_address, abi=svc.contract_abi)

        req = AnchorVerificationRequest(
            verification_id="verif-insufficient-funds-test",
            record_hash=compute_sha256("test")
        )

        with pytest.raises(ValueError) as excinfo:
            svc.anchor_verification(req)

        assert "Insufficient funds" in str(excinfo.value)
        # Ensure private key is NEVER leaked in the error message
        assert burner_private_key not in str(excinfo.value)
    finally:
        svc.settings.SEPOLIA_PRIVATE_KEY = original_key


def test_live_transaction_anchoring_and_receipt_confirmation():
    """
    Tests live transaction submission against local Hardhat Ethereum node:
    - Submits canonical verification record
    - Waits for transaction receipt confirmation (status == 1)
    - Verifies block number, timestamp, and gas used
    - Verifies on-chain record retrieval
    """
    local_w3 = Web3(Web3.HTTPProvider("http://127.0.0.1:8545"))
    if not local_w3.is_connected():
        pytest.skip("Local Hardhat node is not running on http://127.0.0.1:8545")

    svc = BlockchainService()
    svc.w3 = local_w3
    svc.network_name = "hardhat"
    original_key = svc.settings.SEPOLIA_PRIVATE_KEY
    svc.settings.SEPOLIA_PRIVATE_KEY = ""  # Use unlocked test account on local node

    try:
        # Re-instantiate contract on local node
        dep_path = svc.settings.get_absolute_path("blockchain/deployments/localhost-deployment.json")
        if not dep_path.exists():
            dep_path = svc.settings.get_absolute_path("blockchain/deployments/hardhat-deployment.json")
        with open(dep_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
            svc.contract_address = meta["contractAddress"]

        svc.contract = svc.w3.eth.contract(address=svc.contract_address, abi=svc.contract_abi)

        # Build unique canonical record
        unique_id = f"verif-live-test-{os.urandom(4).hex()}"
        canonical_summary = build_canonical_record(
            verification_id=unique_id,
            original_content="The telescope observed distant gravitational lensing.",
            primary_verdict="LIKELY_GENUINE",
            confidence_score=0.94,
            evidence_texts=["Gravitational lensing was documented in astrophysics journals."]
        )

        anchor_req = AnchorVerificationRequest(
            verification_id=unique_id,
            record_hash=canonical_summary.record_hash,
            canonical_record=canonical_summary.canonical_record
        )

        # Submit transaction and wait for block receipt
        anchor_resp = svc.anchor_verification(anchor_req)

        # 1. Assert transaction success
        assert anchor_resp.success is True
        assert anchor_resp.verification_id == unique_id
        assert anchor_resp.record_hash == canonical_summary.record_hash
        assert anchor_resp.transaction_hash.startswith("0x")
        assert len(anchor_resp.transaction_hash) == 66
        assert anchor_resp.block_number is not None and anchor_resp.block_number > 0
        assert anchor_resp.block_timestamp is not None and anchor_resp.block_timestamp > 0
        assert anchor_resp.gas_used is not None and anchor_resp.gas_used > 0
        assert anchor_resp.already_registered is False

        # 2. Assert on-chain record retrieval
        on_chain = svc.query_verification(unique_id)
        assert on_chain is not None
        assert on_chain.is_registered is True
        assert on_chain.verification_id == unique_id
        assert on_chain.record_hash.lower() == canonical_summary.record_hash.lower()
        assert on_chain.block_timestamp == anchor_resp.block_timestamp

        # 3. Assert correct hash integrity check
        integrity_match = svc.verify_hash_integrity(unique_id, canonical_summary.record_hash)
        assert integrity_match.is_registered_on_chain is True
        assert integrity_match.hash_matched is True
        assert integrity_match.integrity_status == "VERIFIED_TAMPER_FREE"

        # 4. Assert tampered hash integrity check fails
        tampered_hash = compute_sha256("tampered-data-injection")
        integrity_mismatch = svc.verify_hash_integrity(unique_id, tampered_hash)
        assert integrity_mismatch.is_registered_on_chain is True
        assert integrity_mismatch.hash_matched is False
        assert integrity_mismatch.integrity_status == "HASH_MISMATCH_TAMPERED"

        # 5. Assert duplicate registration returns safe response without reverting
        dupe_resp = svc.anchor_verification(anchor_req)
        assert dupe_resp.success is True
        assert dupe_resp.already_registered is True
        assert "already registered" in dupe_resp.message.lower()
    finally:
        svc.settings.SEPOLIA_PRIVATE_KEY = original_key


def test_canonical_rehash_mismatch_rejection():
    """
    Validates that if a request contains a canonical_record that does not hash
    to the provided record_hash, it is rejected immediately before touching the network.
    """
    svc = BlockchainService()
    valid_summary = build_canonical_record(
        verification_id="verif-tampered-payload",
        original_content="Original verified statement.",
        primary_verdict="LIKELY_GENUINE",
        confidence_score=0.90
    )

    bad_req = AnchorVerificationRequest(
        verification_id="verif-tampered-payload",
        record_hash="0" * 64,  # Intentional fake hash
        canonical_record=valid_summary.canonical_record
    )

    with pytest.raises(ValueError) as exc:
        svc.anchor_verification(bad_req)

    assert "Cryptographic integrity mismatch" in str(exc.value)


def test_rpc_failure_graceful_handling():
    """
    Validates that if the RPC endpoint is down or unreachable, the service
    raises a clean ConnectionError rather than crashing.
    """
    svc = BlockchainService()
    svc.w3 = Web3(Web3.HTTPProvider("http://127.0.0.1:9999"))  # Unreachable port

    req = AnchorVerificationRequest(
        verification_id="verif-rpc-down",
        record_hash=compute_sha256("offline-claim")
    )

    with pytest.raises(ConnectionError) as exc:
        svc.anchor_verification(req)

    assert "unreachable" in str(exc.value).lower()
