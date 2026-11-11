// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/**
 * @title VerificationRegistry
 * @dev Cryptographic integrity registry for FakeNewsBlockchain AI verification records.
 * 
 * IMPORTANT EPISTEMOLOGICAL PRINCIPLE:
 * This smart contract provides immutable cryptographic proof that a specific verification
 * record existed in an exact state at a specific point in time. It proves record integrity
 * and non-repudiation, NOT the empirical truthfulness or factual validity of the underlying news.
 */
contract VerificationRegistry {
    // Contract owner
    address public owner;
    
    // Emergency pause circuit-breaker
    bool public paused;

    // Structure of a stored verification record
    struct VerificationRecord {
        string verificationId;
        bytes32 recordHash;
        address submitter;
        uint256 timestamp;
        bool isRegistered;
    }

    // Mapping from verificationId to its cryptographic record
    mapping(string => VerificationRecord) private _verifications;

    // Array of all registered verification IDs for enumeration
    string[] private _verificationIds;

    // Events
    event VerificationRegistered(
        bytes32 indexed idHash,
        string verificationId,
        bytes32 indexed recordHash,
        address indexed submitter,
        uint256 timestamp
    );

    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);
    event ContractPaused(address indexed account);
    event ContractUnpaused(address indexed account);

    // Modifiers
    modifier onlyOwner() {
        require(msg.sender == owner, "Caller is not the contract owner");
        _;
    }

    modifier whenNotPaused() {
        require(!paused, "Contract execution is currently paused");
        _;
    }

    constructor() {
        owner = msg.sender;
        paused = false;
        emit OwnershipTransferred(address(0), msg.sender);
    }

    /**
     * @notice Registers a new verification record hash on the blockchain.
     * @param verificationId Unique identifier (e.g. "art-..." or UUID).
     * @param recordHash Deterministic SHA-256 hash of canonical verification data.
     */
    function registerVerification(
        string calldata verificationId,
        bytes32 recordHash
    ) external whenNotPaused returns (bool) {
        require(bytes(verificationId).length > 0, "Verification ID cannot be empty");
        require(recordHash != bytes32(0), "Record hash cannot be zero");
        require(!_verifications[verificationId].isRegistered, "Verification ID already registered");

        _verifications[verificationId] = VerificationRecord({
            verificationId: verificationId,
            recordHash: recordHash,
            submitter: msg.sender,
            timestamp: block.timestamp,
            isRegistered: true
        });

        _verificationIds.push(verificationId);

        // Emit indexing event (using keccak256(verificationId) for indexed lookup)
        emit VerificationRegistered(
            keccak256(bytes(verificationId)),
            verificationId,
            recordHash,
            msg.sender,
            block.timestamp
        );

        return true;
    }

    /**
     * @notice Retrieves a stored verification record by its unique ID.
     * @param verificationId Unique identifier of the record.
     */
    function getVerification(string calldata verificationId)
        external
        view
        returns (
            string memory id,
            bytes32 recordHash,
            address submitter,
            uint256 timestamp,
            bool isRegistered
        )
    {
        VerificationRecord memory rec = _verifications[verificationId];
        require(rec.isRegistered, "Verification record not found");

        return (
            rec.verificationId,
            rec.recordHash,
            rec.submitter,
            rec.timestamp,
            rec.isRegistered
        );
    }

    /**
     * @notice Checks whether an externally calculated SHA-256 hash matches the on-chain anchored hash.
     * @param verificationId Unique identifier of the record.
     * @param recordHash SHA-256 hash to compare against on-chain record.
     */
    function verifyHash(string calldata verificationId, bytes32 recordHash)
        external
        view
        returns (bool)
    {
        VerificationRecord memory rec = _verifications[verificationId];
        if (!rec.isRegistered) {
            return false;
        }
        return rec.recordHash == recordHash;
    }

    /**
     * @notice Returns total number of registered verification records.
     */
    function getVerificationCount() external view returns (uint256) {
        return _verificationIds.length;
    }

    /**
     * @notice Retrieves verification ID by array index for enumeration.
     * @param index Zero-based index.
     */
    function getVerificationIdByIndex(uint256 index) external view returns (string memory) {
        require(index < _verificationIds.length, "Index out of bounds");
        return _verificationIds[index];
    }

    /**
     * @notice Pause registration in case of emergency (Owner only).
     */
    function pause() external onlyOwner {
        require(!paused, "Contract is already paused");
        paused = true;
        emit ContractPaused(msg.sender);
    }

    /**
     * @notice Unpause registration (Owner only).
     */
    function unpause() external onlyOwner {
        require(paused, "Contract is not paused");
        paused = false;
        emit ContractUnpaused(msg.sender);
    }

    /**
     * @notice Transfers ownership of contract (Owner only).
     */
    function transferOwnership(address newOwner) external onlyOwner {
        require(newOwner != address(0), "New owner is zero address");
        emit OwnershipTransferred(owner, newOwner);
        owner = newOwner;
    }
}
