# Contributing to FakeNewsBlockchain

Thank you for your interest in contributing to **FakeNewsBlockchain**. Please read these guidelines to keep code quality, reproducibility, scientific integrity, and repository security consistent across all contributions.

---

## 1. Security & Hygiene First

- **Never commit secrets:** Keep `.env`, API keys (`GOOGLE_FACT_CHECK_API_KEY`, `NEWS_API_KEY`), RPC keys, and Ethereum private keys (`SEPOLIA_PRIVATE_KEY`) strictly out of commits. Update [`.env.example`](.env.example) using placeholder values only when introducing new settings.
- **Never commit large binaries or runtime data:** Keep `Requirements/` model checkpoints/FAISS indexes, `.venv/`, `node_modules/`, SQLite databases (`*.db`), `logs/*.log`, and ad-hoc files in `scratch/` untracked.
- **Do not run unapproved live testnet transactions:** Contract tests must run locally via Hardhat (`npx hardhat test`) rather than sending transactions to public Sepolia.

---

## 2. Development Environment Setup (Windows)

Ensure the following tools are installed:

- **Python:** `3.12.x` (`uv` optional; `.venv` virtual environment recommended)
- **Node.js:** `22.x` LTS (with `npm` `10+`)
- **Model & Corpus Assets:** Place the required models and FAISS corpus under `Requirements/` and run `python scripts/check_assets.py` to validate asset shapes and paths.

See [README.md](README.md) for step-by-step installation and startup instructions.

---

## 3. Branching & Commit Conventions

### Branch Naming
- `feat/<short-description>` — new features or UI/API capabilities
- `fix/<short-description>` — bug fixes and regression patches
- `docs/<short-description>` — documentation improvements
- `refactor/<short-description>` — internal restructuring without functional changes
- `test/<short-description>` — automated test additions or harness improvements

### Commit Messages
Follow clear imperative [Conventional Commits](https://www.conventionalcommits.org/):

- `feat(frontend): add cached news lookup in Article URL tab`
- `fix(ml): preserve outdated verdict precedence in second-pass synthesizer`
- `docs(readme): add Windows setup and Requirements asset verification steps`
- `test(backend): add regression coverage for directional orbital conflicts`

---

## 4. Scientific & Epistemological Guidelines

All changes touching verification logic or UI labels must preserve core design invariants:

1. **ML Classification != Proof of Truth:** Linguistic models (`BERT LIAR`, `BERT ISOT`) are recorded as supplementary signals only and never suppress independent evidence retrieval.
2. **Evidence-Grounded Abstention:** Missing or unrelated evidence resolves safely to `UNVERIFIED`—never infer `FAKE` from retrieval absence.
3. **Visual Forensics Separation:** Image `OCR` and Error Level Analysis (`ELA`) never certify empirical truth (`verdict = UNVERIFIED`).
4. **Honest Blockchain Scope:** Ethereum Sepolia anchoring proves timestamped cryptographic hash integrity of a verification output, not absolute ground truth.

---

## 5. Required Verification Before Opening a Pull Request

Run offline checks covering every layer touched by your changes:

### Backend (Offline Suite & Syntax)
```powershell
.\.venv\Scripts\python.exe -m compileall backend ml scripts
.\.venv\Scripts\python.exe -m pytest backend\tests\test_environment.py backend\tests\test_blockchain.py backend\tests\test_ieve_engine.py -v
```
*(Exclude `backend/tests/test_blockchain_milestone2.py` unless intentionally running funded Sepolia integration checks, and avoid hitting live external APIs in unit tests.)*

### Frontend
```powershell
cd frontend
npx tsc --noEmit
npm run lint
npm run build
```

### Smart Contracts
```powershell
cd blockchain
npx hardhat compile
npx hardhat test
```

Ensure `git status` shows no untracked `.env`, `.db`, `logs/`, `scratch/`, or binary checkpoint artifacts before committing.
