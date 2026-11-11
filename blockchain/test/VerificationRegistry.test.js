const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("VerificationRegistry Smart Contract", function () {
  let registry;
  let owner;
  let submitter1;
  let submitter2;

  // Sample SHA-256 hashes (32 bytes)
  const sampleHash1 = ethers.sha256(ethers.toUtf8Bytes("canonical-verification-record-001"));
  const sampleHash2 = ethers.sha256(ethers.toUtf8Bytes("canonical-verification-record-002"));
  const zeroHash = ethers.ZeroHash;

  beforeEach(async function () {
    [owner, submitter1, submitter2] = await ethers.getSigners();
    const VerificationRegistryFactory = await ethers.getContractFactory("VerificationRegistry");
    registry = await VerificationRegistryFactory.deploy();
    await registry.waitForDeployment();
  });

  describe("Deployment & Initialization", function () {
    it("Should deploy with correct owner and unpaused state", async function () {
      expect(await registry.owner()).to.equal(owner.address);
      expect(await registry.paused()).to.equal(false);
      expect(await registry.getVerificationCount()).to.equal(0);
    });
  });

  describe("Verification Registration", function () {
    it("Should successfully register a new verification record", async function () {
      const vId = "art-uuid-1001";
      const tx = await registry.connect(submitter1).registerVerification(vId, sampleHash1);
      const receipt = await tx.wait();

      // Check count
      expect(await registry.getVerificationCount()).to.equal(1);
      expect(await registry.getVerificationIdByIndex(0)).to.equal(vId);

      // Check stored data
      const record = await registry.getVerification(vId);
      expect(record.id).to.equal(vId);
      expect(record.recordHash).to.equal(sampleHash1);
      expect(record.submitter).to.equal(submitter1.address);
      expect(record.isRegistered).to.equal(true);
      expect(record.timestamp).to.be.gt(0);
    });

    it("Should emit VerificationRegistered event with correct parameters", async function () {
      const vId = "art-uuid-1002";
      const expectedIdHash = ethers.keccak256(ethers.toUtf8Bytes(vId));

      await expect(registry.connect(submitter1).registerVerification(vId, sampleHash1))
        .to.emit(registry, "VerificationRegistered")
        .withArgs(
          expectedIdHash,
          vId,
          sampleHash1,
          submitter1.address,
          (timestamp) => timestamp > 0
        );
    });

    it("Should reject duplicate registration of the same verification ID", async function () {
      const vId = "art-uuid-dupe";
      await registry.connect(submitter1).registerVerification(vId, sampleHash1);

      // Attempting to register again with same ID must revert
      await expect(
        registry.connect(submitter2).registerVerification(vId, sampleHash2)
      ).to.be.revertedWith("Verification ID already registered");
    });

    it("Should reject empty verification ID", async function () {
      await expect(
        registry.connect(submitter1).registerVerification("", sampleHash1)
      ).to.be.revertedWith("Verification ID cannot be empty");
    });

    it("Should reject zero hash bytes32(0)", async function () {
      await expect(
        registry.connect(submitter1).registerVerification("art-valid-id", zeroHash)
      ).to.be.revertedWith("Record hash cannot be zero");
    });
  });

  describe("Hash Verification & Integrity Checks", function () {
    beforeEach(async function () {
      await registry.connect(submitter1).registerVerification("art-verify-01", sampleHash1);
    });

    it("Should return true when hash exactly matches on-chain record", async function () {
      const matches = await registry.verifyHash("art-verify-01", sampleHash1);
      expect(matches).to.equal(true);
    });

    it("Should return false when hash does not match (tampered/different record)", async function () {
      const alteredHash = ethers.sha256(ethers.toUtf8Bytes("altered-record-contents"));
      const matches = await registry.verifyHash("art-verify-01", alteredHash);
      expect(matches).to.equal(false);
    });

    it("Should return false for unregistered verification ID", async function () {
      const matches = await registry.verifyHash("unregistered-id-404", sampleHash1);
      expect(matches).to.equal(false);
    });

    it("Should revert getVerification for non-existent record", async function () {
      await expect(
        registry.getVerification("non-existent-id")
      ).to.be.revertedWith("Verification record not found");
    });
  });

  describe("Enumeration & Indexing", function () {
    it("Should allow iterating through all registered IDs", async function () {
      const ids = ["art-01", "art-02", "art-03"];
      for (const id of ids) {
        await registry.registerVerification(id, sampleHash1);
      }

      expect(await registry.getVerificationCount()).to.equal(3);
      for (let i = 0; i < ids.length; i++) {
        expect(await registry.getVerificationIdByIndex(i)).to.equal(ids[i]);
      }

      await expect(registry.getVerificationIdByIndex(3)).to.be.revertedWith("Index out of bounds");
    });
  });

  describe("Access Control & Circuit Breaker (Pause/Unpause)", function () {
    it("Should allow owner to pause and prevent further registrations", async function () {
      await expect(registry.connect(owner).pause())
        .to.emit(registry, "ContractPaused")
        .withArgs(owner.address);

      expect(await registry.paused()).to.equal(true);

      // Registration should now revert
      await expect(
        registry.connect(submitter1).registerVerification("art-paused", sampleHash1)
      ).to.be.revertedWith("Contract execution is currently paused");

      // Unpause
      await expect(registry.connect(owner).unpause())
        .to.emit(registry, "ContractUnpaused")
        .withArgs(owner.address);

      expect(await registry.paused()).to.equal(false);

      // Now registration works
      await expect(
        registry.connect(submitter1).registerVerification("art-paused", sampleHash1)
      ).to.emit(registry, "VerificationRegistered");
    });

    it("Should reject non-owner attempts to pause or unpause", async function () {
      await expect(
        registry.connect(submitter1).pause()
      ).to.be.revertedWith("Caller is not the contract owner");

      await registry.connect(owner).pause();

      await expect(
        registry.connect(submitter1).unpause()
      ).to.be.revertedWith("Caller is not the contract owner");
    });

    it("Should allow transferring ownership to a new valid address", async function () {
      await expect(registry.connect(owner).transferOwnership(submitter1.address))
        .to.emit(registry, "OwnershipTransferred")
        .withArgs(owner.address, submitter1.address);

      expect(await registry.owner()).to.equal(submitter1.address);

      // Old owner cannot pause anymore
      await expect(
        registry.connect(owner).pause()
      ).to.be.revertedWith("Caller is not the contract owner");

      // New owner can pause
      await expect(registry.connect(submitter1).pause()).to.emit(registry, "ContractPaused");
    });

    it("Should reject transferring ownership to zero address", async function () {
      await expect(
        registry.connect(owner).transferOwnership(ethers.ZeroAddress)
      ).to.be.revertedWith("New owner is zero address");
    });
  });
});
