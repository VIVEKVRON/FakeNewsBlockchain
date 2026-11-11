# API SPECIFICATION
**Project:** FakeNewsBlockchain – Real-Time Multimodal Fake News Detection & Fact Verification  
**API Version:** `v1`  
**Base URL:** `http://127.0.0.1:8000/api/v1`  
**Interactive Docs:** Swagger UI at `http://127.0.0.1:8000/docs`, ReDoc at `http://127.0.0.1:8000/redoc`

---

## 1. Global Specifications

### Headers
- `Content-Type: application/json` (or `multipart/form-data` for image uploads)
- `Accept: application/json`

### Standard Error Responses
HTTP errors (`400`, `404`, `413`, `422`, `500`, `503`, `504`) follow FastAPI's JSON format (`{"detail": "..."}`).

### Six-Class Verdict Enum (`VerdictEnum`)
- `GENUINE`: Substantiated by qualifying primary or independent corroborated evidence without unresolved conflicts.
- `FAKE`: Directly refuted by Tier 1 / independent corroborated contradictions or explicit symbolic refutation / multi-publisher ClaimReviews.
- `MISLEADING`: Subject-aligned entity/broadcaster swap or absolute framing distortion contradicted by aligned evidence.
- `PARTIALLY_TRUE`: Compound claim or multi-claim article combining verified and refuted sub-claims.
- `OUTDATED`: Present-tense assertion whose historical tenure, status, or name has explicitly closed in aligned documentary evidence.
- `UNVERIFIED`: Insufficient, irrelevant, uncorroborated single Tier 2, conflicting, primary-record-gated, or stale-2017-only evidence.
- *(Legacy aliases `LIKELY_GENUINE` and `LIKELY_FAKE` remain accepted only when querying/deserializing pre-audit SQLite and Sepolia records.)*

---

## 2. Verification Endpoints

### 2.1 Verify Text Claim
Evaluates an individual or compound claim using Pass 1 separate linguistic signals (`BERT LIAR` / `BERT ISOT` availability flags), prediction-independent bidirectional retrieval (126k FEVER FAISS + conditional Wikipedia fallback + Google Fact Check + neutral GDELT), post-retrieval `DeBERTa-v3` NLI, and `SecondPassEvaluator` synthesis.

- **Method / Path:** `POST /api/v1/verify/text`
- **Request Body (`TextVerificationRequest`):**
```json
{
  "claim": "19 Kids and Counting is an American reality television show featuring the Duggar family.",
  "top_k": 5
}
```
- **Response (`200 OK`, `TextVerificationResponse`):**
```json
{
  "verification_id": "verif-a8f3b2e94f11",
  "claim": "19 Kids and Counting is an American reality television show featuring the Duggar family.",
  "verdict": "GENUINE",
  "confidence_score": 0.85,
  "explanation": "...",
  "uncertainty_explanation": "...",
  "conflicting_evidence_detected": false,
  "strongest_evidence_page": "19 Kids and Counting",
  "evidence": [
    {
      "rank": 1,
      "page": "19 Kids and Counting",
      "sentence_id": 0,
      "doc_id": "19_Kids_and_Counting_0",
      "text": "19 Kids and Counting is an American reality television show...",
      "retrieval_similarity": 0.84,
      "nli_label": "SUPPORTS",
      "nli_confidence": 0.99,
      "nli_probabilities": {
        "supports": 0.99,
        "refutes": 0.01,
        "not_enough_info": 0.0
      },
      "source_type": "fever_local",
      "source_url": "https://en.wikipedia.org/wiki/19_Kids_and_Counting",
      "publication_date": "2017-06 (FEVER Wikipedia Corpus)",
      "evidence_role": "supporting",
      "retrieval_direction": "support_oriented"
    }
  ],
  "claim_verdicts": [],
  "fact_check_matches": [],
  "news_evidence": [],
  "external_source_status": {
    "google_fact_check_status": "no_results",
    "gdelt_status": "ok"
  },
  "evidence_audit_trail": {
    "initial_ml_signals": {
      "liar_signal": { "applicable": true },
      "isot_signal": { "applicable": false }
    },
    "nli_evaluation": {
      "evaluation_stage": "post_retrieval_claim_evidence_pair",
      "pairs_evaluated": 8
    },
    "second_pass_decision": "confirmed_initial",
    "final_verdict": "GENUINE",
    "final_confidence": 0.85
  },
  "limitations": ["..."],
  "blockchain_hash": {
    "schema_version": "1.0",
    "verification_id": "verif-a8f3b2e94f11",
    "record_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
  },
  "created_at": "2026-11-11T12:00:00Z"
}
```

---

### 2.2 Verify Full Article
Evaluates full article text using `BERT ISOT` (as an exploratory Pass 1 signal), decomposes factual claims (`max_claims` `1..5`), isolates retrieval and audit trails per claim, enforces a max-2 GDELT query cap per article, and synthesizes an overall six-class verdict.

- **Method / Path:** `POST /api/v1/verify/article`
- **Request Body (`ArticleVerificationRequest`):**
```json
{
  "title": "Duggar Reality Show Run",
  "text": "19 Kids and Counting is an American reality television show featuring the Duggar family. However, 19 Kids and Counting was cancelled in 2030.",
  "max_claims": 3,
  "source_url": "https://example.org/article"
}
```
- **Response (`200 OK`, `ArticleVerificationResponse`):** Returns `article_id`, `title`, `overall_verdict`, `overall_confidence`, `summary_explanation`, `uncertainty_explanation`, `article_classifier`, `claims_analyzed`, `extracted_claims[]` (with per-claim isolated `evidence`, `liar_signal`, and `evidence_audit_trail`), `fact_check_matches[]`, `news_evidence[]`, `external_source_status`, article-level `evidence_audit_trail`, `limitations[]`, `created_at`, and `blockchain_hash`.

---

### 2.3 Analyze Multimodal Image (OCR + ELA)
Extracts embedded text via `PaddleOCR` and runs compression artifact forensics via Error Level Analysis (`ELA`).

- **Method / Path:** `POST /api/v1/analyze/image`
- **Request:** `multipart/form-data`
  - `file`: Image file (`JPG`, `PNG`, or `WEBP`, max `10 MB`)
- **Response (`200 OK`, `ImageAnalysisResponse`):**
```json
{
  "analysis_id": "img-9a3b4e11ab12",
  "verification_id": "img-9a3b4e11ab12",
  "record_hash": "abc123...",
  "verdict": "UNVERIFIED",
  "factual_verification_status": "UNVERIFIED",
  "metadata": {
    "filename": "news_sample.png",
    "content_type": "image/png",
    "format": "PNG",
    "width": 640,
    "height": 360,
    "aspect_ratio": 1.78,
    "file_size_bytes": 42100
  },
  "ocr": {
    "has_text": true,
    "full_text": "Apollo 11 landed on the Moon in 1969",
    "word_count": 8,
    "average_confidence": 0.96,
    "text_blocks": [
      {
        "text": "Apollo 11 landed on the Moon in 1969",
        "confidence": 0.96,
        "box": [[10, 10], [450, 10], [450, 40], [10, 40]]
      }
    ]
  },
  "ela": {
    "mean_error": 4.12,
    "max_error": 68,
    "std_error": 7.45,
    "variance_score": 55.5,
    "quality_tested": 90,
    "potential_compression_anomalies": false,
    "anomaly_regions_detected": 0,
    "ela_image_base64": "data:image/jpeg;base64,..."
  },
  "observations": ["..."],
  "limitations": ["Standalone OCR and ELA do not prove empirical truth or forgery..."],
  "created_at": "2026-11-11T12:00:00Z"
}
```

---

## 3. Live News & URL Extraction Endpoints

*(SSRF-guarded `Trafilatura` URL extraction operates through cached feed verification rather than an unguarded arbitrary-URL verification endpoint.)*

- **`GET /api/v1/news`**: List paginated cached news articles (`keyword`, `publisher`, `category`, `limit`, `offset`) -> `NewsListResponse`.
- **`GET /api/v1/news/sources`**: List configured RSS/GDELT feeds -> `NewsSourcesResponse`.
- **`POST /api/v1/news/refresh`**: Fetch feeds, deduplicate canonical URLs, update SQLite cache -> `NewsRefreshResponse`.
- **`GET /api/v1/news/gdelt-usage`**: Return shared GDELT quota usage, remaining allowance, cache hits, and Google Fact Check availability -> `GdeltUsageStatusSchema`.
- **`POST /api/v1/news/{article_id}/verify`**: Validate article URL against SSRF rules (`is_safe_url`), extract full text via `Trafilatura`, and execute `verify_article` -> `ArticleVerificationResponse`.

---

## 4. Verification History Endpoints

- **`GET /api/v1/history`**: List persisted SQLite verification records (`content_type`, `verdict`, `blockchain_status`, `search`, `limit`, `offset`, `sort_by`, `order`) -> `HistoryListResponse`. Supports both six-class verdict values and legacy aliases (`LIKELY_GENUINE`, `LIKELY_FAKE`).
- **`GET /api/v1/history/{verification_id}`**: Retrieve full saved verification record, evidence snapshot, canonical hash, and transaction metadata.

---

## 5. Blockchain Integrity & Audit Endpoints

- **`GET /api/v1/blockchain/status`**: Return RPC connectivity, `network`, `chain_id`, `contract_address`, `contract_deployed`, `is_paused`, `total_verifications`, `latest_block`, and `epistemological_disclaimer` (`BlockchainStatusResponse`).
- **`GET /api/v1/blockchain/records/{verification_id}`**: Query [`VerificationRegistry.sol`](blockchain/contracts/VerificationRegistry.sol) directly -> `OnChainRecordDetails`.
- **`POST /api/v1/blockchain/verify-hash`**: Body `{"verification_id": "...", "record_hash": "..."}` -> compares hash against on-chain anchor (`VerifyHashResponse`: `VERIFIED_TAMPER_FREE`, `HASH_MISMATCH_TAMPERED`, `NOT_FOUND_ON_CHAIN`, or `RPC_UNAVAILABLE`).
- **`POST /api/v1/blockchain/anchor`**: Anchor a verified canonical record hash on-chain -> `AnchorVerificationResponse`.
- **`GET /api/v1/blockchain/audit`**: List all blockchain-anchored records for Audit Explorer (`network`, `chain_id`, `contract_address`, `contract_deployed`, `total_records`, `records`).
- **`GET /api/v1/blockchain/audit/{verification_id}/compare`**: Compare stored SQLite hash against live on-chain hash (`VERIFIED_MATCH`, `TAMPERED_MISMATCH`, `NOT_FOUND_ON_CHAIN`, or `RPC_UNAVAILABLE`).

---

## 6. Verification Certificate Endpoints

- **`GET /api/v1/certificates/{verification_id}/download`**: Generate and download an `application/pdf` verification certificate with embedded QR code (`FakeNewsBlockchain_Certificate_{id}.pdf`). Requires the record to be confirmed on-chain (`400` otherwise).
- **`POST /api/v1/certificates/verify`**: Body `{"verification_id": "verif-9c524ca7b6f5", "record_hash": "..."}` -> `PublicCertificateVerifyResponse` (`status`: `MATCH`, `MISMATCH`, `NOT_FOUND`, or `NETWORK_UNAVAILABLE`; `is_authentic`; `block_number`; `etherscan_url`; `epistemological_disclaimer`).

---

## 7. System & Health Endpoints

- **`GET /`**: Returns basic API metadata (`project`, `version`, `status`, `docs`, `health`).
- **`GET /api/v1/health`**: Returns `status`, `version`, `environment`, `runtime` (`device`, `torch_threads`, `models_loaded`), and `asset_paths_verified` (`fever_verifier`, `bert_isot`, `bert_liar`, `faiss_index`).
