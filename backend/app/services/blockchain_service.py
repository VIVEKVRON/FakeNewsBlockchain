"""
backend/app/services/blockchain_service.py
Cryptographic hashing service and Ethereum smart contract client for FakeNewsBlockchain.
Anchors SHA-256 verification hashes to the VerificationRegistry smart contract.

EPISTEMOLOGICAL INTEGRITY PRINCIPLE:
This service provides immutable cryptographic proofs of verification records (anti-tampering
and non-repudiation). It anchors mathematical hashes, NOT absolute empirical truth.
"""

import json
import hashlib
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timezone

from web3 import Web3
from web3.exceptions import Web3Exception

from backend.app.config import get_settings
from backend.app.schemas.blockchain import (
    CanonicalVerificationRecord,
    VerificationHashSummary,
    OnChainRecordDetails,
    VerifyHashResponse,
    BlockchainStatusResponse,
    AnchorVerificationRequest,
    AnchorVerificationResponse
)
from backend.app.schemas.verification import TextVerificationResponse
from backend.app.schemas.article import ArticleVerificationResponse

logger = logging.getLogger(__name__)


def compute_sha256(content: str) -> str:
    """Computes a lower-case 64-character SHA-256 hex digest for UTF-8 string."""
    return hashlib.sha256(content.strip().encode("utf-8")).hexdigest()


def serialize_canonical_record(record: CanonicalVerificationRecord) -> Tuple[str, str, str]:
    """
    Deterministically serializes a canonical verification record to JSON with sorted keys
    and no extraneous whitespace (separators=(',', ':')).
    Returns:
        (canonical_json, record_hash_hex, record_hash_bytes32)
    """
    record_dict = record.model_dump()
    canonical_json = json.dumps(record_dict, sort_keys=True, separators=(",", ":"))
    record_hash_hex = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    record_hash_bytes32 = "0x" + record_hash_hex
    return canonical_json, record_hash_hex, record_hash_bytes32


def build_canonical_record(
    verification_id: str,
    original_content: str,
    primary_verdict: str,
    confidence_score: float,
    evidence_texts: Optional[List[str]] = None,
    timestamp: Optional[str] = None
) -> VerificationHashSummary:
    """
    Builds a canonical verification record and computes its deterministic SHA-256 hash.
    """
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat()

    content_hash = compute_sha256(original_content)
    
    evidence_hashes: List[str] = []
    if evidence_texts:
        for ev in evidence_texts:
            if ev and ev.strip():
                evidence_hashes.append(compute_sha256(ev.strip()))

    canonical_record = CanonicalVerificationRecord(
        schema_version="1.0",
        verification_id=verification_id,
        original_content_hash=content_hash,
        primary_verdict=str(primary_verdict),
        confidence_score=round(float(confidence_score), 4),
        evidence_hashes=evidence_hashes,
        timestamp=timestamp
    )

    canonical_json, record_hash_hex, record_hash_bytes32 = serialize_canonical_record(canonical_record)

    return VerificationHashSummary(
        schema_version="1.0",
        verification_id=verification_id,
        canonical_record=canonical_record,
        canonical_json=canonical_json,
        record_hash=record_hash_hex,
        record_hash_bytes32=record_hash_bytes32,
        blockchain_anchored=False
    )


def create_hash_summary_from_text(
    claim: str,
    response: TextVerificationResponse
) -> VerificationHashSummary:
    """Creates a cryptographic verification hash summary from TextVerificationResponse."""
    evidence_texts = [e.text for e in response.evidence] if response.evidence else []
    return build_canonical_record(
        verification_id=response.verification_id,
        original_content=claim,
        primary_verdict=response.verdict.value if hasattr(response.verdict, "value") else str(response.verdict),
        confidence_score=response.confidence_score,
        evidence_texts=evidence_texts,
        timestamp=response.created_at
    )


def create_hash_summary_from_article(
    article_text: str,
    response: ArticleVerificationResponse
) -> VerificationHashSummary:
    """Creates a cryptographic verification hash summary from ArticleVerificationResponse."""
    evidence_texts: List[str] = []
    if response.extracted_claims:
        for ec in response.extracted_claims:
            for ev in ec.evidence:
                evidence_texts.append(ev.text)

    return build_canonical_record(
        verification_id=response.article_id,
        original_content=article_text,
        primary_verdict=response.overall_verdict.value if hasattr(response.overall_verdict, "value") else str(response.overall_verdict),
        confidence_score=response.overall_confidence,
        evidence_texts=evidence_texts,
        timestamp=response.created_at
    )


class BlockchainService:
    """
    Manages Web3 connection, contract interactions, and integrity verifications.
    Designed with a resilient fallback mechanism: if the Ethereum node/RPC is unavailable,
    it continues providing offline canonical record generation and verification hashing.
    """

    def __init__(self):
        self.settings = get_settings()
        self.w3: Optional[Web3] = None
        self.contract = None
        self.contract_abi: Optional[List[Dict[str, Any]]] = None
        self.contract_address: Optional[str] = None
        self.network_name: str = "offline"
        self._load_contract_artifacts()
        self._init_web3()

    def _load_contract_artifacts(self):
        """Loads compiled contract ABI and locates the deployed contract address."""
        abi_path = self.settings.get_absolute_path(
            "blockchain/artifacts/contracts/VerificationRegistry.sol/VerificationRegistry.json"
        )
        if abi_path.exists():
            try:
                with open(abi_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.contract_abi = data.get("abi")
                    logger.info("Successfully loaded VerificationRegistry contract ABI.")
            except Exception as e:
                logger.error(f"Failed to read contract artifact from {abi_path}: {e}")

        # Try to resolve deployed contract address
        # 1. From settings/.env
        if self.settings.CONTRACT_ADDRESS and Web3.is_address(self.settings.CONTRACT_ADDRESS):
            self.contract_address = Web3.to_checksum_address(self.settings.CONTRACT_ADDRESS)
            return

        # 2. From sepolia deployment
        sepolia_dep = self.settings.get_absolute_path("blockchain/deployments/sepolia-deployment.json")
        if sepolia_dep.exists():
            try:
                with open(sepolia_dep, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    addr = data.get("contractAddress")
                    if addr and Web3.is_address(addr):
                        self.contract_address = Web3.to_checksum_address(addr)
                        self.network_name = data.get("network", "sepolia")
                        return
            except Exception as e:
                logger.warning(f"Could not read Sepolia deployment metadata: {e}")

        # 3. From localhost / hardhat local deployment
        for dep_name in ["localhost-deployment.json", "hardhat-deployment.json"]:
            dep_path = self.settings.get_absolute_path(f"blockchain/deployments/{dep_name}")
            if dep_path.exists():
                try:
                    with open(dep_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        addr = data.get("contractAddress")
                        if addr and Web3.is_address(addr):
                            self.contract_address = Web3.to_checksum_address(addr)
                            self.network_name = data.get("network", "hardhat")
                            return
                except Exception as e:
                    logger.warning(f"Could not read {dep_name} metadata: {e}")

    def _is_local_node_available(self) -> bool:
        try:
            test_w3 = Web3(Web3.HTTPProvider("http://127.0.0.1:8545", request_kwargs={"timeout": 1}))
            return test_w3.is_connected()
        except Exception:
            return False

    def _init_web3(self):
        """Initializes Web3 provider based on configuration or local fallback."""
        rpc_url = self.settings.SEPOLIA_RPC_URL
        has_private_key = bool(self.settings.SEPOLIA_PRIVATE_KEY and self.settings.SEPOLIA_PRIVATE_KEY.strip())

        connected_to_remote = False
        # If private key is configured or local node is down, prefer remote RPC
        if rpc_url and (has_private_key or not self._is_local_node_available()):
            try:
                remote_w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 5}))
                if remote_w3.is_connected():
                    self.w3 = remote_w3
                    cid = self.w3.eth.chain_id
                    self.network_name = "sepolia" if cid == 11155111 else f"chain-{cid}"
                    connected_to_remote = True
                    logger.info(f"Connected to Ethereum RPC at {rpc_url[:25]}... (chain {cid})")
            except Exception as e:
                logger.warning(f"Failed to connect to configured RPC URL: {e}")

        # Local Hardhat fallback (when no private key is set or remote RPC unavailable)
        if not connected_to_remote:
            try:
                local_w3 = Web3(Web3.HTTPProvider("http://127.0.0.1:8545", request_kwargs={"timeout": 2}))
                if local_w3.is_connected():
                    self.w3 = local_w3
                    self.network_name = "hardhat"
                    logger.info("Connected to local Ethereum Hardhat node at http://127.0.0.1:8545 (Fallback)")
            except Exception:
                pass

        # If connected and we have contract ABI + address, instantiate contract object
        if self.w3 and self.w3.is_connected() and self.contract_abi and self.contract_address:
            try:
                self.contract = self.w3.eth.contract(
                    address=self.contract_address,
                    abi=self.contract_abi
                )
                logger.info(f"Initialized contract instance at {self.contract_address}")
            except Exception as e:
                logger.error(f"Failed to initialize contract instance: {e}")

    def is_connected(self) -> bool:
        """Returns True if connected to an Ethereum RPC provider."""
        return bool(self.w3 and self.w3.is_connected())

    def get_status(self) -> BlockchainStatusResponse:
        """Returns comprehensive status of blockchain connectivity and smart contract."""
        connected = self.is_connected()
        chain_id = None
        latest_block = None
        is_paused = None
        owner = None
        total_verifications = None
        contract_deployed = False

        if connected and self.w3:
            try:
                chain_id = self.w3.eth.chain_id
                latest_block = self.w3.eth.block_number
            except Exception as e:
                logger.warning(f"Failed to query block number: {e}")

            if self.contract and self.contract_address:
                try:
                    code = self.w3.eth.get_code(self.contract_address)
                    contract_deployed = len(code) > 2  # more than '0x'
                    if contract_deployed:
                        total_verifications = self.contract.functions.getVerificationCount().call()
                        is_paused = self.contract.functions.paused().call()
                        owner = self.contract.functions.owner().call()
                except Exception as e:
                    logger.warning(f"Failed to query contract state: {e}")

        return BlockchainStatusResponse(
            enabled=self.settings.BLOCKCHAIN_ENABLED,
            connected=connected,
            network=self.network_name,
            chain_id=chain_id,
            contract_address=self.contract_address,
            contract_deployed=contract_deployed,
            is_paused=is_paused,
            owner=owner,
            total_verifications=total_verifications,
            latest_block=latest_block,
            rpc_endpoint_configured=bool(self.settings.SEPOLIA_RPC_URL)
        )

    def query_verification(self, verification_id: str) -> Optional[OnChainRecordDetails]:
        """Queries on-chain verification record by verification ID."""
        if not self.is_connected() or not self.contract:
            return None

        try:
            record = self.contract.functions.getVerification(verification_id).call()
            # (id, recordHash, submitter, timestamp, isRegistered)
            rec_id, rec_hash_bytes, submitter, ts, is_reg = record
            rec_hash_hex = rec_hash_bytes.hex()
            dt_str = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()

            return OnChainRecordDetails(
                verification_id=rec_id,
                record_hash=rec_hash_hex,
                record_hash_bytes32="0x" + rec_hash_hex,
                submitter=submitter,
                block_timestamp=ts,
                block_datetime=dt_str,
                is_registered=is_reg
            )
        except Exception as e:
            logger.info(f"Verification ID '{verification_id}' not found on-chain: {e}")
            return None

    def verify_hash_integrity(
        self,
        verification_id: str,
        provided_record_hash: Optional[str] = None
    ) -> VerifyHashResponse:
        """
        Validates whether a verification record exists on-chain and optionally compares
        a provided SHA-256 record hash against the immutable on-chain anchor.
        """
        if not self.is_connected():
            return VerifyHashResponse(
                verification_id=verification_id,
                is_registered_on_chain=False,
                hash_matched=None,
                on_chain_record=None,
                network=self.network_name,
                contract_address=self.contract_address,
                integrity_status="RPC_UNAVAILABLE",
                explanation="Ethereum blockchain RPC is currently unreachable. Integrity cannot be verified on-chain."
            )

        if not self.contract:
            return VerifyHashResponse(
                verification_id=verification_id,
                is_registered_on_chain=False,
                hash_matched=None,
                on_chain_record=None,
                network=self.network_name,
                contract_address=self.contract_address,
                integrity_status="CONTRACT_NOT_FOUND",
                explanation="VerificationRegistry smart contract is not deployed or configured on this network."
            )

        on_chain_record = self.query_verification(verification_id)
        if not on_chain_record or not on_chain_record.is_registered:
            return VerifyHashResponse(
                verification_id=verification_id,
                is_registered_on_chain=False,
                hash_matched=None,
                on_chain_record=None,
                network=self.network_name,
                contract_address=self.contract_address,
                integrity_status="NOT_FOUND_ON_CHAIN",
                explanation=f"No verification record found on-chain for ID '{verification_id}'."
            )

        # If a hash is provided to compare against
        if provided_record_hash:
            clean_hash = provided_record_hash.lower().replace("0x", "")
            matched = (clean_hash == on_chain_record.record_hash.lower())
            if matched:
                return VerifyHashResponse(
                    verification_id=verification_id,
                    is_registered_on_chain=True,
                    hash_matched=True,
                    on_chain_record=on_chain_record,
                    network=self.network_name,
                    contract_address=self.contract_address,
                    integrity_status="VERIFIED_TAMPER_FREE",
                    explanation=(
                        f"Cryptographic match verified! The record hash '{clean_hash[:16]}...' exactly matches "
                        f"the immutable on-chain anchor registered at block timestamp {on_chain_record.block_datetime}. "
                        "The verification record has not been tampered with."
                    )
                )
            else:
                return VerifyHashResponse(
                    verification_id=verification_id,
                    is_registered_on_chain=True,
                    hash_matched=False,
                    on_chain_record=on_chain_record,
                    network=self.network_name,
                    contract_address=self.contract_address,
                    integrity_status="HASH_MISMATCH_TAMPERED",
                    explanation=(
                        f"CRITICAL INTEGRITY FAILURE: The provided record hash '{clean_hash[:16]}...' "
                        f"does NOT match the on-chain anchor '{on_chain_record.record_hash[:16]}...'. "
                        "The local record contents, verdict, or evidence have been altered or tampered with."
                    )
                )

        # Record exists, no hash was supplied to compare
        return VerifyHashResponse(
            verification_id=verification_id,
            is_registered_on_chain=True,
            hash_matched=None,
            on_chain_record=on_chain_record,
            network=self.network_name,
            contract_address=self.contract_address,
            integrity_status="REGISTERED_ON_CHAIN",
            explanation=(
                f"Record '{verification_id}' exists on-chain with anchored hash '{on_chain_record.record_hash[:16]}...' "
                f"registered by {on_chain_record.submitter}."
            )
        )

    def anchor_verification(
        self,
        request: AnchorVerificationRequest
    ) -> AnchorVerificationResponse:
        """
        User-triggered cryptographic anchoring of a verification record to the Ethereum smart contract.
        Signs and submits a real blockchain transaction and waits for receipt confirmation.
        """
        # 1. Cryptographic validation if canonical record was supplied
        if request.canonical_record:
            _, recomputed_hash, _ = serialize_canonical_record(request.canonical_record)
            if recomputed_hash.lower() != request.record_hash.lower():
                raise ValueError(
                    f"Cryptographic integrity mismatch: Provided record_hash '{request.record_hash}' "
                    f"does not match deterministic hash of canonical record '{recomputed_hash}'."
                )

        # 2. Check RPC connection
        if not self.is_connected():
            raise ConnectionError(
                "Ethereum blockchain RPC is unreachable. Cannot anchor transaction."
            )

        # 3. Check contract availability
        if not self.contract or not self.contract_address:
            raise RuntimeError(
                "VerificationRegistry smart contract is not deployed or configured on this network."
            )

        # 4. Chain ID validation (strictly prohibit mainnet!)
        actual_chain_id = self.w3.eth.chain_id
        if actual_chain_id == 1:
            raise RuntimeError(
                "CRITICAL: Connected to Ethereum Mainnet (Chain ID 1). Anchoring on mainnet is strictly prohibited."
            )

        if actual_chain_id == 11155111:
            self.network_name = "sepolia"
        elif actual_chain_id in (31337, 1337):
            self.network_name = "hardhat"
        else:
            self.network_name = f"chain-{actual_chain_id}"

        if self.network_name == "sepolia" and actual_chain_id != self.settings.SEPOLIA_CHAIN_ID:
            raise RuntimeError(
                f"Network mismatch: Connected chain ID {actual_chain_id} does not match "
                f"expected Sepolia chain ID {self.settings.SEPOLIA_CHAIN_ID}."
            )

        # 5. Check circuit breaker pause
        try:
            if self.contract.functions.paused().call():
                raise RuntimeError("VerificationRegistry smart contract is currently paused by the contract owner.")
        except Exception as e:
            if "paused" in str(e).lower():
                raise RuntimeError(f"Smart contract paused check failed: {e}")

        # 6. Check for duplicate registration on-chain
        existing_record = self.query_verification(request.verification_id)
        if existing_record and existing_record.is_registered:
            etherscan_url = (
                f"https://sepolia.etherscan.io/address/{self.contract_address}"
                if actual_chain_id == 11155111
                else f"http://127.0.0.1:8545/address/{self.contract_address}"
            )
            return AnchorVerificationResponse(
                success=True,
                verification_id=request.verification_id,
                record_hash=existing_record.record_hash,
                contract_address=self.contract_address,
                block_timestamp=existing_record.block_timestamp,
                block_datetime=existing_record.block_datetime,
                submitter_address=existing_record.submitter,
                network=self.network_name,
                chain_id=actual_chain_id,
                etherscan_url=etherscan_url,
                already_registered=True,
                message=f"Verification ID '{request.verification_id}' is already registered on-chain."
            )

        # 7. Identify signing account and credentials (never leak private key in logs or errors)
        private_key = self.settings.SEPOLIA_PRIVATE_KEY.strip() if self.settings.SEPOLIA_PRIVATE_KEY else ""
        sender_account = None
        sender_address = None

        if private_key:
            try:
                sender_account = self.w3.eth.account.from_key(private_key)
                sender_address = sender_account.address
            except Exception as e:
                raise ValueError("Invalid SEPOLIA_PRIVATE_KEY format in .env.")
        elif self.w3.eth.accounts:
            # Local Hardhat node unlocked test account
            sender_address = self.w3.eth.accounts[0]
        else:
            raise ValueError(
                "No Ethereum account configured for transaction signing. Please set SEPOLIA_PRIVATE_KEY in .env."
            )

        # 8. Check balance
        balance = self.w3.eth.get_balance(sender_address)
        if balance <= 0:
            raise ValueError(
                f"Insufficient funds: Account {sender_address} has 0 ETH on {self.network_name}. "
                "Please request Sepolia test ETH from a faucet (e.g. https://sepoliafaucet.com)."
            )

        # 9. Format record hash as bytes32
        clean_hash = request.record_hash.lower().replace("0x", "")
        record_hash_bytes32 = bytes.fromhex(clean_hash)

        # 10. Gas estimation
        try:
            gas_est = self.contract.functions.registerVerification(
                request.verification_id,
                record_hash_bytes32
            ).estimate_gas({"from": sender_address})
            gas_limit = int(gas_est * 1.3)
        except Exception as e:
            logger.warning(f"Gas estimation fallback used: {e}")
            gas_limit = 250000

        nonce = self.w3.eth.get_transaction_count(sender_address, "pending")

        # 11. Transaction submission
        if sender_account:
            try:
                latest_block = self.w3.eth.get_block("latest")
                base_fee = latest_block.get("baseFeePerGas", self.w3.to_wei(2, "gwei"))
                priority_fee = self.w3.to_wei(1.5, "gwei")
                max_fee = (base_fee * 2) + priority_fee
                tx_dict = {
                    "from": sender_address,
                    "nonce": nonce,
                    "gas": gas_limit,
                    "maxFeePerGas": max_fee,
                    "maxPriorityFeePerGas": priority_fee,
                    "chainId": actual_chain_id
                }
            except Exception:
                gas_price = self.w3.eth.gas_price
                tx_dict = {
                    "from": sender_address,
                    "nonce": nonce,
                    "gas": gas_limit,
                    "gasPrice": gas_price,
                    "chainId": actual_chain_id
                }

            built_tx = self.contract.functions.registerVerification(
                request.verification_id,
                record_hash_bytes32
            ).build_transaction(tx_dict)

            signed = self.w3.eth.account.sign_transaction(built_tx, private_key=private_key)
            raw_tx = getattr(signed, "raw_transaction", getattr(signed, "rawTransaction", None))
            tx_hash_bytes = self.w3.eth.send_raw_transaction(raw_tx)
            tx_hash_str = tx_hash_bytes.hex()
        else:
            tx_hash_bytes = self.contract.functions.registerVerification(
                request.verification_id,
                record_hash_bytes32
            ).transact({"from": sender_address, "gas": gas_limit, "nonce": nonce})
            tx_hash_str = tx_hash_bytes.hex()

        if not tx_hash_str.startswith("0x"):
            tx_hash_str = "0x" + tx_hash_str

        logger.info(f"Anchoring tx submitted: {tx_hash_str}. Waiting for block confirmation...")

        # 12. Await receipt confirmation
        try:
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash_bytes, timeout=60, poll_latency=1)
        except Exception as e:
            raise TimeoutError(f"Transaction confirmation timed out for tx {tx_hash_str}: {e}")

        if receipt.status != 1:
            raise RuntimeError(f"Transaction reverted on-chain. Status: {receipt.status}, Tx: {tx_hash_str}")

        # 13. Query confirmed block timestamp
        block = self.w3.eth.get_block(receipt.blockNumber)
        block_ts = block.timestamp
        block_dt = datetime.fromtimestamp(block_ts, tz=timezone.utc).isoformat()

        etherscan_url = (
            f"https://sepolia.etherscan.io/tx/{tx_hash_str}"
            if actual_chain_id == 11155111
            else f"http://127.0.0.1:8545/tx/{tx_hash_str}"
        )

        # Update SQLite database if record exists
        try:
            from backend.app.database.repository import update_blockchain_anchoring
            update_blockchain_anchoring(
                verification_id=request.verification_id,
                transaction_hash=tx_hash_str,
                contract_address=self.contract_address,
                block_number=receipt.blockNumber,
                block_timestamp=block_ts,
                block_datetime=block_dt,
                submitter_address=sender_address,
                gas_used=receipt.gasUsed,
                network=self.network_name,
                chain_id=actual_chain_id,
                etherscan_url=etherscan_url,
                status="confirmed"
            )
        except Exception as e:
            logger.warning(f"Could not update verification record in SQLite: {e}")

        return AnchorVerificationResponse(
            success=True,
            verification_id=request.verification_id,
            record_hash=request.record_hash,
            transaction_hash=tx_hash_str,
            contract_address=self.contract_address,
            block_number=receipt.blockNumber,
            block_timestamp=block_ts,
            block_datetime=block_dt,
            submitter_address=sender_address,
            gas_used=receipt.gasUsed,
            network=self.network_name,
            chain_id=actual_chain_id,
            etherscan_url=etherscan_url,
            already_registered=False,
            message=(
                f"Verification record '{request.verification_id}' successfully anchored on-chain "
                f"at block #{receipt.blockNumber}."
            )
        )



# Global singleton instance
_blockchain_service: Optional[BlockchainService] = None


def get_blockchain_service() -> BlockchainService:
    global _blockchain_service
    if _blockchain_service is None:
        _blockchain_service = BlockchainService()
    return _blockchain_service
