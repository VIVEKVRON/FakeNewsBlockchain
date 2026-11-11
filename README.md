# FakeNewsBlockchain

Evidence-grounded fake news detection, claim verification, image forensics, and Ethereum Sepolia cryptographic auditability — built for local CPU execution with zero paid API requirements.

---

## Overview

**FakeNewsBlockchain** combines Retrieval-Augmented Generation (RAG), Transformer Natural Language Inference (NLI), supplementary NLP classifiers, image OCR/Error Level Analysis, and an immutable Ethereum Sepolia audit registry.

Rather than relying on black-box classification scores alone, its **Independent Evidence Verification Engine (IEVE)** performs prediction-independent multi-directional evidence retrieval, subject/predicate/temporal alignment gating, source provenance tiering, and second-pass synthesis across **six explicit verdict classes**:

`GENUINE` · `FAKE` · `MISLEADING` · `PARTIALLY_TRUE` · `OUTDATED` · `UNVERIFIED`

---

## Key Features

- **Unified Option A Web Workspace (React + Glassmorphism UI):**
  - **Home (`/`):** Landing showcase (`"Truth deserves verification."`) with quick-claim dispatch and live FastAPI / SQLite telemetry.
  - **Dashboard (`/dashboard`):** Operations monitor displaying local session metrics, FastAPI inference status, SQLite count, Sepolia contract telemetry, and shared GDELT request quota.
  - **Unified Verify Workspace (`/verify`):** Four accessible tabs — **Text Claim**, **Full Article**, **Article URL** (`source_url` metadata alongside pasted article text, or one-click cached RSS/GDELT verification), and **Image OCR/ELA** (plus preserved direct routes `/text`, `/article`, `/image`).
  - **Evidence Explorer (`/evidence` & `/history`):** Searchable SQLite verification ledger with verdict/status filtering, inspectable retrieved evidence cards, IEVE audit trails (when recorded or cached in session), and PDF certificate links.
  - **Live News Monitor (`/live`):** SSRF-safe RSS feeds (BBC, NPR, NYT, Phys.org) + GDELT DOC 2.0 ingestion with deduplication, shared SQLite quota tracking, and in-modal article verification.
  - **Blockchain Records (`/blockchain`, `/audit`, `/verify-certificate`):** Ethereum Sepolia anchored record ledger, live smart-contract hash comparison, downloadable QR-coded vector PDF certificates, and independent public tamper detection.
- **Two-Pass IEVE Engine (`ml/inference/` & `ml/rag/`):**
  - **Pass 1 ML Signals (Supplementary Only):** `BERT ISOT` (document-level binary stylistic classifier) and `BERT LIAR` (statement-level 6-class classifier) logged independently with raw logits and explicit distribution-shift disclaimers.
  - **Pass 2 Retrieval & Alignment:** Queries a normalized `126,000`-sentence FEVER FAISS index (`all-MiniLM-L6-v2`, 384d CPU), conditional read-only Wikipedia API fallback, optional Google Fact Check Tools API, and GDELT coverage before scoring claim–evidence pairs with `DeBERTa-v3` NLI (`SUPPORTS`, `REFUTES`, `NOT ENOUGH INFO`), ordinal/directional alignment checks, and source tier validation.
- **Multimodal Forensics (`ml/vision/`):**
  - Local `PaddleOCR` text extraction + OpenCV Error Level Analysis (`ELA`) compression variance maps, plus direct routing of extracted text to the claim verifier.
- **Cryptographic Proof & PDF Certificates (`blockchain/` & `backend/app/services/`):**
  - Deterministic canonical SHA-256 hashing anchored on Ethereum Sepolia via [`VerificationRegistry.sol`](blockchain/contracts/VerificationRegistry.sol), accompanied by ReportLab vector PDF certificates carrying verification QR codes.

---

## System Architecture

```text
+-----------------------------------------------------------------------------+
|                    Frontend SPA (React 19 · Vite · Tailwind)                |
|  / (Home) | /dashboard | /verify (Text / Article / URL / Image) | /live     |
|  /evidence (/history)  | /blockchain (/audit, /verify-certificate) | /about |
+-------------------------------------+---------------------------------------+
                                      | Vite proxy (/api -> http://127.0.0.1:8000)
                                      v
+-----------------------------------------------------------------------------+
|                 FastAPI Backend (backend/app/main.py · Python 3.12)         |
|  verify.py · image.py · news.py · history.py · blockchain.py · certificates |
+----------------+----------------------------------+-------------------------+
                 |                                  |
                 v                                  v
+---------------------------------+   +---------------------------------------+
|   IEVE & ML Pipeline (CPU)      |   |  Persistence & Cryptographic Layer    |
|  - DeBERTa-v3 NLI (FEVER)       |   |  - SQLite WAL: fakenews.db            |
|  - BERT ISOT & BERT LIAR        |   |  - News/Quota DB: news_cache.db       |
|  - all-MiniLM-L6-v2 + FAISS     |   |  - ReportLab PDF + QR Certificates    |
|  - Wikipedia / GDELT / FactChk  |   |  - Web3.py <-> Sepolia / Hardhat      |
|  - PaddleOCR + OpenCV ELA       |   |    VerificationRegistry.sol           |
+---------------------------------+   +---------------------------------------+
```

---

## Technology Stack

| Layer | Technologies |
| :--- | :--- |
| **Frontend** | React 19, TypeScript, Vite 8, Tailwind CSS 3.4, Motion (`motion/react`), Lucide Icons, React Router 7 |
| **Backend API** | Python 3.12, FastAPI, Uvicorn, Pydantic v2, SQLite (WAL mode) |
| **ML / NLP / RAG** | PyTorch (CPU-only, 4 threads), HuggingFace Transformers, `DeBERTa-v3` NLI, `BERT` (ISOT & LIAR), `sentence-transformers` (`all-MiniLM-L6-v2`), FAISS (`IndexFlatIP`) |
| **Vision / Ingestion** | PaddleOCR, PaddlePaddle, OpenCV (`opencv-python-headless`), Pillow, Feedparser, Trafilatura, Requests, HTTPX |
| **Blockchain & Docs** | Solidity `^0.8.24`, Hardhat + `@nomicfoundation/hardhat-toolbox`, Web3.py `8.x`, ReportLab, `qrcode` |
| **Code Quality & Tests** | `pytest`, `pytest-asyncio`, `oxlint`, TypeScript `tsc`, Hardhat/Chai |

---

## Project Structure

```text
FakeNewsBlockChain/
├── backend/
│   ├── app/
│   │   ├── api/routes/         # FastAPI endpoints (verify, image, news, history, blockchain, certificates)
│   │   ├── database/           # SQLite WAL connection & repository CRUD
│   │   ├── schemas/            # Pydantic v2 request/response contracts
│   │   ├── services/           # Orchestration, PDF certificates, Web3 service, external API clients/quota
│   │   ├── config.py           # Environment settings & validators
│   │   └── main.py             # FastAPI app entrypoint, CORS & lifespan startup
│   └── tests/                  # Automated unit & integration tests (offline + optional Sepolia suite)
├── frontend/
│   ├── src/
│   │   ├── api/                # Typed fetch helpers (/api/v1/*)
│   │   ├── components/         # Layout (TopNav Option A, mobile drawer), verify panels, evidence & audit UI
│   │   ├── hooks/              # Theme, localStorage session history, pointer/ripple hooks
│   │   ├── pages/              # Home, Dashboard, Verify, EvidenceExplorer, LiveNews, BlockchainRecords, aliases
│   │   └── types/              # TypeScript interfaces matching FastAPI schemas
│   ├── package.json
│   └── vite.config.ts          # Dev server on port 5173 proxying /api -> 127.0.0.1:8000
├── ml/
│   ├── inference/              # Claim decomposition, DeBERTa verifier, alignment, evidence quality, IEVE synthesis
│   ├── rag/                    # FAISS index retriever & read-only Wikipedia API fallback
│   └── vision/                 # PaddleOCR extractor & OpenCV ELA analyzer
├── blockchain/
│   ├── contracts/              # VerificationRegistry.sol (Solidity 0.8.24)
│   ├── deployments/            # Public contract deployment metadata JSON (hardhat, localhost, sepolia)
│   ├── scripts/                # Hardhat deployment script (deploy.js)
│   ├── test/                   # Hardhat Mocha/Chai smart contract tests
│   ├── hardhat.config.js       # Hardhat local (31337) & Sepolia (11155111) networks
│   └── package.json
├── data/                       # Runtime SQLite DBs & uploads (ignored from Git; preserves .gitkeep)
├── docs/                       # Architecture audit reports & selected application screenshots
├── scripts/                    # Asset checker (`check_assets.py`) & CLI demo scripts
├── Requirements/               # Excluded from Git: local BERT/DeBERTa weights & 126k FEVER FAISS assets
├── .env.example                # Safe environment variable template
├── .gitignore
├── ARCHITECTURE.md
├── API_SPECIFICATION.md
├── CONTRIBUTING.md
├── LICENSE
├── pyproject.toml              # Authoritative Python package manifest & CPU PyTorch index
├── requirements.txt            # Direct Python runtime dependencies synced with pyproject.toml
├── uv.lock                     # Reproducible uv lockfile
└── README.md
```

---

## Running Locally (Windows)

### 1. Prerequisites

- **Python:** `3.12.x` (`>=3.12,<3.13` as specified in [`pyproject.toml`](pyproject.toml))
- **Node.js & npm:** Node.js `v22.x` LTS and `npm` `10+`
- **Git:** Git for Windows (`git`)
- **Blockchain Tools:** Node.js / Hardhat toolchain (`hardhat` + `@nomicfoundation/hardhat-toolbox` in [`blockchain/package.json`](blockchain/package.json)) if running a local Hardhat node or smart contract tests
- **Optional:** [`uv`](https://docs.astral.sh/uv/) for lockfile-exact environment provisioning (`uv sync`)
- **Hardware:** `>= 16 GB RAM` recommended for concurrent CPU transformer inference (`TORCH_NUM_THREADS=4`)

### 2. Clone the Repository

```powershell
git clone https://github.com/VIVEKVRON/FakeNewsBlockchain.git
cd FakeNewsBlockchain
```

### 3. Create & Activate a Python Virtual Environment

Using standard Python `venv`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

*(If PowerShell blocks script activation in your session, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` first, or use `uv sync` which creates `.venv` automatically.)*

### 4. Install Python Dependencies

**Option A — Using [`requirements.txt`](requirements.txt) (`pip`, CPU-only PyTorch):**

```powershell
python -m pip install --upgrade pip
pip install "torch>=2.2.0" --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
```

To also run the automated `pytest` suites:

```powershell
pip install "pytest>=8.0.0" "pytest-asyncio>=0.23.0"
```

**Option B — Using `uv` (authoritative [`pyproject.toml`](pyproject.toml) + [`uv.lock`](uv.lock)):**

```powershell
uv sync
.\.venv\Scripts\Activate.ps1
```

### 5. Obtain & Verify ML Models and FAISS Assets (`Requirements/`)

> **Important Asset Notice:** Large ML model checkpoints (`*.safetensors`, `*.pt`, `*.bin`) and the 126,000-sentence FEVER FAISS corpus (`~4 GB+` total under `Requirements/`) are **excluded from Git** via `.gitignore`. You must obtain these assets separately and place them at the paths configured in [`.env.example`](.env.example). Without `Requirements/` assets, full NLI/FEVER fact verification and supplementary BERT inference will be limited or unavailable.

Expected directory structure:

```text
Requirements/
├── bert_isot_temporal_v1/      # BertForSequenceClassification (2-class ISOT)
├── bert_liar_v1/
│   └── final_model/            # BertForSequenceClassification (6-class LIAR)
├── fever_verifier_v1/          # DebertaV2ForSequenceClassification (3-class FEVER NLI + spm.model)
├── wiki_fever.index            # FAISS FlatIP index (384-dim vectors)
├── row_mapping.jsonl           # Vector ID -> document/sentence metadata mapping
└── sentences.jsonl             # 126,000 indexed FEVER Wikipedia sentences
```

Validate asset integrity and alignment:

```powershell
.\.venv\Scripts\python.exe scripts\check_assets.py
```

### 6. Configure Environment Variables (`.env`)

Copy [`.env.example`](.env.example) to a local `.env` file:

```powershell
Copy-Item .env.example .env
```

> **Security & Credential Rules:**
> - **`.env` must be created locally and never committed to Git** (it is protected in [`.gitignore`](.gitignore)).
> - **`SEPOLIA_RPC_URL`, `SEPOLIA_PRIVATE_KEY`, `CONTRACT_ADDRESS`, `GOOGLE_FACT_CHECK_API_KEY`, and `NEWS_API_KEY` are optional** and must never be shared or committed.
> - Core local claim verification, FAISS retrieval, SQLite persistence, and image OCR/ELA work without paid APIs or Sepolia credentials. If external API keys or Sepolia credentials are omitted, Fact Check lookups and live on-chain anchoring/audits are disabled cleanly (`BLOCKCHAIN_ENABLED=False` disables Web3 calls completely).

### 7. Install Frontend Dependencies (`npm ci`)

```powershell
cd frontend
npm ci
```

### 8. Start the FastAPI Backend (`127.0.0.1:8000`)

From the project root with `.venv` activated (default `HOST=127.0.0.1`, `PORT=8000` in [`backend/app/config.py`](backend/app/config.py)):

```powershell
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

- **Swagger UI:** `http://127.0.0.1:8000/docs`
- **Health Diagnostics:** `http://127.0.0.1:8000/api/v1/health`

### 9. Start the React / Vite Frontend (`localhost:5173`)

In a second terminal (Vite binds port `5173` and proxies `/api` to `http://127.0.0.1:8000` per [`frontend/vite.config.ts`](frontend/vite.config.ts)):

```powershell
cd frontend
npm run dev
```

Open **`http://localhost:5173`** in your browser.

### 10. Start a Local Hardhat Blockchain (Optional)

If testing smart-contract deployment or blockchain anchoring locally without Ethereum Sepolia (`http://127.0.0.1:8545`, Chain ID `31337` per [`blockchain/hardhat.config.js`](blockchain/hardhat.config.js)):

1. Install Hardhat dependencies:
   ```powershell
   cd blockchain
   npm ci
   ```
2. Start the local Hardhat JSON-RPC node (keep this terminal open):
   ```powershell
   npx hardhat node
   ```
3. In a separate terminal, deploy [`VerificationRegistry.sol`](blockchain/contracts/VerificationRegistry.sol) to the local node using [`blockchain/scripts/deploy.js`](blockchain/scripts/deploy.js):
   ```powershell
   cd blockchain
   npx hardhat run scripts/deploy.js --network localhost
   ```
4. Update your local `.env` with `BLOCKCHAIN_ENABLED=True`, `SEPOLIA_RPC_URL=http://127.0.0.1:8545`, `SEPOLIA_CHAIN_ID=31337`, `CONTRACT_ADDRESS=<printed deployed address>`, and one of the ephemeral test account keys printed by `npx hardhat node` (for local Hardhat testing only).

### 11. Run Tests & Production Builds

**Backend syntax & offline verification tests:**

```powershell
.\.venv\Scripts\python.exe -m compileall backend ml scripts
.\.venv\Scripts\python.exe -m pytest -v backend\tests\test_health.py backend\tests\test_environment.py backend\tests\test_blockchain.py backend\tests\test_ieve_engine.py
```

*(Note: `backend/tests/test_milestone3.py` writes sample records to the active SQLite DB unless isolated, and `backend/tests/test_blockchain_milestone2.py` targets live Sepolia RPC.)*

**Frontend TypeScript, lint (`oxlint`) & production build:**

```powershell
cd frontend
npx tsc --noEmit
npm run lint
npm run build
```

**Local Hardhat smart contract tests:**

```powershell
cd blockchain
npx hardhat test
```

### 12. Troubleshooting (Windows)

| Symptom | Likely Cause | Resolution |
| :--- | :--- | :--- |
| `scripts\check_assets.py` fails or health check shows missing paths | `Requirements/` models or `wiki_fever.index` missing or mislocated | Verify exact directory names under `Requirements/` and confirm `MODEL_*_PATH` / `RETRIEVAL_*_PATH` in `.env` match relative paths. |
| `Form data requires "python-multipart"` on `/api/v1/analyze/image` | Environment installed without `python-multipart` | Install via `pip install -r requirements.txt` or `uv sync` (`python-multipart>=0.0.33` is included in both [`pyproject.toml`](pyproject.toml) and [`requirements.txt`](requirements.txt)). |
| PyTorch / PaddleOCR / NumPy conflict or unexpected GPU CUDA download | `pip install torch` downloaded CUDA PyTorch instead of CPU wheel | Reinstall `torch` explicitly with `--index-url https://download.pytorch.org/whl/cpu` before `pip install -r requirements.txt`, or use `uv sync`. |
| Port `8000`, `5173`, or `8545` already in use (`WinError 10048`) | Previous server instance still bound | Inspect with `netstat -ano \| findstr ":8000"` (`5173` / `8545`) and stop the old PID (`Stop-Process -Id <PID>`), or change `PORT` in `.env` and matching Vite proxy target in [`frontend/vite.config.ts`](frontend/vite.config.ts). |
| Blockchain endpoints report disconnected or missing credentials | Missing `.env` values or `SEPOLIA_RPC_URL` unreachable | Set `BLOCKCHAIN_ENABLED=False` in `.env` for offline usage, or configure a valid RPC URL / local Hardhat node (`http://127.0.0.1:8545`). |
| `Activate.ps1 cannot be loaded because running scripts is disabled` | Windows PowerShell execution policy | Run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` in the active PowerShell window before activating `.venv`. |

---

## Blockchain Sepolia Setup & Certificate Verification

- Smart contract [`VerificationRegistry.sol`](blockchain/contracts/VerificationRegistry.sol) stores `(verificationId, recordHash, submitter, timestamp)` events and state on-chain.
- Deployment metadata for Sepolia is recorded in [`blockchain/deployments/sepolia-deployment.json`](blockchain/deployments/sepolia-deployment.json) (contract `0xcDa4CE06d44642Fd0034C817B5b7cB6AFC886ffb`, chain ID `11155111`).
- Read-only verification only requires `BLOCKCHAIN_ENABLED=True`, `SEPOLIA_RPC_URL`, and `CONTRACT_ADDRESS` in `.env` (leave `SEPOLIA_PRIVATE_KEY` empty unless explicitly authorizing new test-ETH anchor transactions).
- Existing QR certificate verification (`/verify-certificate?id=...&hash=...` or `/blockchain`) compares any user-supplied verification ID and SHA-256 digest directly against the deployed Sepolia record to surface `MATCH`, `MISMATCH`, or `NOT_FOUND`.

---

## Limitations & Responsible-Use Disclaimer

1. **No Arbitrary URL Scraping Endpoint:** For strict SSRF safety and zero-cost operation, `/verify` (`Article URL` tab) pairs an optional `source_url` reference with pasted article text (`POST /api/v1/verify/article`) or verifies already-ingested cached feeds (`POST /api/v1/news/{article_id}/verify`).
2. **Tier 2 & Tier 3 Evidence Boundaries:** Built-in knowledge sources (`fever_local`, `wikipedia_live`, `google_fact_check`, `gdelt`) represent encyclopedic or journalistic reviews rather than official first-party government/regulatory registries (`Tier 1`). Claims strictly requiring primary official records abstain conservatively as `UNVERIFIED` unless corroborated by independent ClaimReview refutations.
3. **ML Signals Are Non-Authoritative:** `BERT ISOT` and `BERT LIAR` reflect linguistic patterns in historical datasets and carry known temporal/domain shifts; they never establish factual truth by themselves.
4. **Image Forensics (`ELA` / `OCR`):** Recompression artifacts (`ELA`) can arise from ordinary social-media resizing or saving and never prove forgery; image analysis always reports factual verdict `UNVERIFIED`.
5. **Blockchain Integrity != Empirical Truth:** Sepolia anchoring proves **what verdict hash existed at a given block timestamp**, not that the underlying real-world claim is infallible.

For architecture and API details, see [`ARCHITECTURE.md`](ARCHITECTURE.md), [`API_SPECIFICATION.md`](API_SPECIFICATION.md), and [`CONTRIBUTING.md`](CONTRIBUTING.md).

---

## License

This project is licensed under the **MIT License** — see [`LICENSE`](LICENSE) for details (replace the copyright holder placeholder in `LICENSE` prior to publishing if needed).
