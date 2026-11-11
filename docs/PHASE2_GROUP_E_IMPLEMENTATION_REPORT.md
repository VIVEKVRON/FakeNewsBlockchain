# FakeNewsBlockchain — Phase 2 / Group E Implementation Report

**Project Root:** `D:\Documents\FakeNewsBlockChain`  
**Phase / Scope:** Phase 2 — Group E Only (Google Fact Check Tools API, GDELT DOC 2.0 Gateway, Shared Persistent 200-Request GDELT Quota, Evidence Aggregation, UI Presentation)  
**Authorization Boundary:** Group E implementation completed and verified with mocked external HTTP tests. Live-quota verification against external production endpoints and any subsequent phases await user authorization.

---

## 1. Executive Summary

Phase 2 / Group E integrates two free, public external evidence channels into the existing `FakeNewsBlockchain` verification and news monitoring platform while preserving every Phase 1 safeguard, six-class verdict definition (`GENUINE`, `FAKE`, `MISLEADING`, `PARTIALLY_TRUE`, `UNVERIFIED`, `OUTDATED`), historical SQLite record, trained model file, canonical SHA-256 hash format, and Sepolia smart contract state (`0xcDa4CE06d44642Fd0034C817B5b7cB6AFC886ffb`).

Key capabilities implemented:
1. **Backend-Only Google Fact Check Tools API Client:** Queries `https://factchecktools.googleapis.com/v1alpha1/claims:search` with `GOOGLE_FACT_CHECK_API_KEY` stored exclusively in backend settings (`.env`), extracts full third-party `ClaimReview` provenance, preserves original publisher ratings **verbatim** (never inferred or collapsed), detects conflicting publisher ratings and potentially stale reviews, and scrubs API secrets from logs and error messages.
2. **Backend-Only GDELT DOC 2.0 Gateway (`ArtList`):** Consolidates news discovery across `verify_text`, `verify_article`, and Live News Monitor (`NewsService`) through one shared client (`GdeltClient`), applies canonical URL normalization + title syndication deduplication + static SSRF filtering, and explicitly separates news coverage metadata from factual proof.
3. **Shared Persistent 200-Request Hard Quota & Cache (`data/news_cache.db`):** Adds `gdelt_usage_state` and `external_evidence_cache` additively to `data/news_cache.db`. Reserves 1 quota slot atomically inside SQLite `BEGIN IMMEDIATE` **before** every outbound GDELT HTTP attempt (`WHERE id = 1 AND requests_used < ?`), retains failed attempt counts without refunds, serves cache hits at `0` quota cost, surfaces a warning at `<= 20` remaining (`requests_used >= 180`), blocks calls fail-closed at `200` or when SQLite cannot be locked, and exposes read-only usage telemetry via `GET /api/v1/news/gdelt-usage` without any unauthenticated reset endpoint.
4. **Theme-Safe UI Presentation:** Displays distinct, attribution-clear cards for **Google Fact Check Tools**, **GDELT News Coverage Discovery**, and **External API Usage & Shared GDELT Quota** across `TextVerify`, `ArticleVerify`, `LiveNews`, and `Sidebar` (readable in both dark and light themes).

---

## 2. Pre-Implementation Backups & Database Preservation

Timestamped SQLite backups were created prior to Phase 2 modifications:
- **Backup directory:** `C:\Users\ADMIN\.gemini\antigravity\brain\196b0c18-ecec-450a-83e7-f75c18a8277f\backups\pre_phase2_20261111_151108`
  - `fakenews.db` pre-Phase-2 SHA-256: `35FC2F2CC41D6B100F1D2AD81844112D9EAD2C286C95F95B45FCDED9AEE4E38F`
  - `news_cache.db` pre-Phase-2 SHA-256: `6C83243522D6F33E7944C7223401CF29359A6E425290A2EF2C35AC743D40DE84`

Post-implementation verification of production SQLite files (`data/database/fakenews.db` and `data/news_cache.db`):
- `data/database/fakenews.db` SHA-256: `35fc2f2cc41d6b100f1d2ad81844112d9ead2c286c95f95b45fcded9aee4e38f` (**bit-for-bit identical**, `verification_records` = `185`).
- `data/news_cache.db` tables after additive initialization: `['news_articles', 'news_sources', 'gdelt_usage_state', 'external_evidence_cache']`
  - `news_articles`: `279` rows (backup: `279`, unchanged)
  - `news_sources`: `5` rows (backup: `5`, unchanged)
  - `gdelt_usage_state`: `requests_used = 0`, `requests_remaining = 200`, `allowance_limit = 200`, `warning_threshold = 20`, `cache_hits = 0`, `failed_requests = 0`, `tracker_available = True`.

---

## 3. Configuration & Secret Handling

Updated `D:\Documents\FakeNewsBlockChain\.env.example` and `D:\Documents\FakeNewsBlockChain\backend\app\config.py` (`Settings`):
- `GOOGLE_FACT_CHECK_API_KEY: str = ""` (read strictly by backend `Settings` from `.env`; `.env` confirmed ignored by `.gitignore:2`)
- `GOOGLE_FACT_CHECK_TIMEOUT_SEC: float = 8.0`
- `GDELT_ENABLED: bool = True`
- `GDELT_REQUEST_LIMIT: int = 200`
- `GDELT_WARNING_THRESHOLD: int = 20`
- `GDELT_TIMEOUT_SEC: float = 8.0`
- `GDELT_MAX_RECORDS: int = 10`
- `GDELT_MAX_RETRIES: int = 1`
- `EXTERNAL_CACHE_TTL_HOURS: int = 24`

Static secret audit across `backend/app/`, `ml/`, and `frontend/src/` confirmed:
- `factchecktools.googleapis.com` appears only in `backend/app/services/external_apis/google_factcheck_client.py`.
- `GOOGLE_FACT_CHECK_API_KEY` never appears in `frontend/src/` and is scrubbed by `sanitize_secret_text()` before logging or populating `error_detail`.
- GDELT requests never include Google API credentials (`"key"` absent from GDELT query params).

---

## 4. External API Modules (`backend/app/services/external_apis/`)

### 4.1 `quota_db.py`
- `resolve_news_cache_db_path(db_path)`: Resolves default `data/news_cache.db` (and honors `FAKE_NEWS_TEST_NEWS_DB` in test isolation when `db_path` is omitted).
- `ensure_external_tables(conn, default_limit=200)`: Idempotently creates `gdelt_usage_state` (`id INTEGER PRIMARY KEY CHECK (id = 1)`) and `external_evidence_cache` without altering `news_articles` or `news_sources`.
- `sanitize_secret_text(text, secret="")`: Redacts `key=...` parameters and secret values.
- `validate_external_http_url(url)`: Permits only public `http`/`https` FQDNs; rejects loopback, link-local metadata (`169.254.169.254`), private, multicast, reserved IPs, and `.local`/`.internal`/`localhost` hosts.

### 4.2 `evidence_cache.py`
- `ExternalEvidenceCache`: Stores keyed JSON payloads (`sha256(f"{provider}:{normalized_query}")`) with `EXTERNAL_CACHE_TTL_HOURS` TTL (`24` hours default).
- Expired rows are purged on lookup; unexpired hits for `provider == "gdelt"` increment `gdelt_usage_state.cache_hits` inside `BEGIN IMMEDIATE` without incrementing `requests_used`.

### 4.3 `gdelt_usage_tracker.py`
- `GdeltUsageTracker`:
  - `reserve_request_slot(source)`: Atomically increments `requests_used` inside SQLite `BEGIN IMMEDIATE` (`WHERE id = 1 AND requests_used < ?`) **before** any outbound GDELT HTTP call leaves the process.
  - `record_request_outcome(source, status_label, failed=False)`: Updates `last_status`, `last_source`, and increments `failed_requests` without ever refunding `requests_used`.
  - Fails closed (`tracker_available=False`, `(False, status)`) on any `sqlite3.Error` or `OSError`.
  - Computes `requests_remaining = max(0, allowance_limit - requests_used)`, `limit_reached`, and `warning_active` (`requests_remaining <= warning_threshold`).

### 4.4 `google_factcheck_client.py`
- `GoogleFactCheckClient.search_claims(query, max_results=5)`:
  - Checks `GOOGLE_FACT_CHECK_API_KEY`; returns `unavailable_no_api_key` cleanly if absent.
  - Queries cache first, then calls `https://factchecktools.googleapis.com/v1alpha1/claims:search` (`languageCode="en"`, bounded 1 retry on 5xx/`Timeout`).
  - Populates `FactCheckMatch`: `claim_text`, `review_title`, `publisher_name`, `publisher_site`, `reviewer_name`, `rating_text` (exact publisher rating verbatim), `review_url`, `review_publication_date`, `claim_appearance_date`, `original_claim_author`, `language_code`, `retrieved_at`, `is_stale`, `stale_reason`, `is_conflicting`.
  - Handles `401`/`403` (`auth_error`), `429` (`rate_limited`), `5xx` (`http_error`), `Timeout` (`timeout`), malformed JSON (`invalid_response`), and empty results (`no_results`) without inferring truth.

### 4.5 `gdelt_client.py`
- `GdeltClient`:
  - Provides both `search_coverage(query, ...)` (`mode="ArtList"`, `sourcelang:eng`) and `fetch_feed_articles(feed_url, source_label="news_refresh")` so Live News Monitor shares the exact same gateway, cache, and 200-request cap.
  - Every `api.gdeltproject.org` HTTP attempt checks cache first, then atomically reserves a quota slot via `tracker.reserve_request_slot(source_label)` inside `_execute_query` (each retry also reserves its own slot cleanly within the hard cap).
  - Canonicalizes URLs via `normalize_article_url()` (strips `utm_*`, `fbclid`, `gclid`, etc.), filters private/unsafe URLs via `validate_external_http_url()`, and collapses identical/syndicated titles (`syndicated_count`, `duplicates_collapsed`).

### 4.6 `evidence_aggregator.py`
- `build_focused_claim_queries(claim_text)`: Produces short claim queries (`<= 280` chars for Google Fact Check; entity/year-focused query up to 6–7 terms for GDELT) so full multi-paragraph articles are never forwarded blindly.
- `should_query_gdelt_for_claim(...)`: Skips GDELT on static textbook assertions resolved as `GENUINE`/`FAKE` by Phase 1 (`resolved_static_reference_fact`), conserving budget for recent, temporal, entity-bearing, or `UNVERIFIED`/`MISLEADING`/`PARTIALLY_TRUE`/`OUTDATED` claims.
- `ExternalEvidenceAggregator.enrich_claims(...)`: Collects up to `max_fact_check_queries` / `max_gdelt_queries` results, detects contrasting GDELT framing (`_detect_gdelt_coverage_tension`), collects stale/conflict notes and quota warnings, and leaves Phase 1 verdicts untouched.

---

## 5. Backend Schema, Service & Route Integration

- **Pydantic Schemas:**
  - `backend/app/schemas/verification.py`: Added `FactCheckMatchSchema`, `NewsEvidenceSchema`, `GdeltUsageStatusSchema`, `ExternalSourceStatusSchema`, and optional fields (`fact_check_matches`, `news_evidence`, `external_source_status`) on `TextVerificationResponse`.
  - `backend/app/schemas/article.py`: Added the same optional external fields on `ArticleVerificationResponse`.
  - `backend/app/schemas/news.py`: Added `gdelt_usage: Optional[GdeltUsageStatusSchema] = None` on `NewsRefreshResponse`.
- **Services & API Routes:**
  - `backend/app/services/news_service.py`: Replaced raw `urllib.request.urlopen` in `_ingest_gdelt_source` with `self.gdelt_client.fetch_feed_articles(...)` backed by `resolve_news_cache_db_path(db_path)`, added `get_gdelt_usage()`, and attached `gdelt_usage` to `refresh_feeds()` responses while continuing RSS ingestion cleanly if GDELT quota is exhausted or fails.
  - `backend/app/api/routes/news.py`: Exposed `GET /api/v1/news/gdelt-usage` returning `GdeltUsageStatusSchema` (`google_fact_check_available` boolean, zero secrets). No reset route exists.
  - `backend/app/services/verification_service.py`: Added `_to_external_schemas()` and non-blocking `external_aggregator.enrich_claims()` calls to `verify_text_claim()` and `verify_article()` (passing only concise claims / up to top 2 extracted central claims). Verified Phase 1 verdicts, `evidence`, and `CanonicalVerificationRecord` SHA-256 hash generation remain unchanged.

---

## 6. Frontend Integration

- `frontend/src/types/verification.ts` & `frontend/src/api/verify.ts`: Added TypeScript interfaces matching the new backend schemas and `getExternalUsage()`.
- `frontend/src/components/ui/ExternalEvidenceSection.tsx`: Renders separate **Google Fact Check Tools** and **GDELT News Coverage Discovery** cards, verbatim publisher ratings, conflict/stale badges, attribution & discovery non-proof banners, external links, empty/error/quota-exhausted messaging, and theme-safe light/dark styles.
- `frontend/src/components/ui/ExternalApiUsageCard.tsx`: Displays shared GDELT usage progress bar (`used / allowance_limit`), cache hits (`0` cost), failed counted requests, low-budget warning banner (`warning_active`), cap-reached block banner (`limit_reached`), fail-closed warning, and backend Google Fact Check availability status.
- `frontend/src/components/ui/EvidenceCard.tsx`: Extended `source_type` provenance labels (`wikipedia_live`, `local_wikipedia`, `google_fact_check`, `gdelt`, `rss`, `fever_local`) and light/dark contrast.
- `frontend/src/components/layout/Sidebar.tsx`, `TextVerify.tsx`, `ArticleVerify.tsx`, `LiveNews.tsx`: Wired `ExternalEvidenceSection`, `ExternalApiUsageCard`, and live sidebar GDELT quota telemetry.

---

## 7. Verification, Regression & Integrity Results

### 7.1 Automated Test Results (Mocked External HTTP, Session DB Isolation)
`backend/tests/conftest.py` isolates `news_cache.db` and `fakenews.db` to temporary session copies and guards unmocked `requests.Session.get` calls targeting `factchecktools.googleapis.com` or `api.gdeltproject.org`.

1. **Targeted Group E Suite** (`.venv\Scripts\python -m pytest backend\tests\test_external_apis.py -v`):
   - **21 passed, 0 failed** (`40.43s`).
   - Covers: ClaimReview extraction & verbatim ratings, missing key, empty response, HTTP 401/403/429/503/Timeout/invalid JSON & secret scrubbing, conflict & staleness flags, GDELT URL canonicalization & title syndication collapse, SSRF blocking, zero Google key leakage to GDELT, failure quota accounting & restart persistence, warning threshold at `180` (`20` remaining), hard cap allowing request #200 and blocking #201 with 0 HTTP calls, 16-thread concurrency reservation safety (`ThreadPoolExecutor`), fail-closed tracker behavior on DB error, shared Live News + verification quota, focused query scoping, conflicting GDELT framing, `GET /api/v1/news/gdelt-usage`, absence of unauthenticated reset endpoint, and `/verify/text` + `/verify/article` six-class/canonical-hash invariance.
2. **Full Backend Regression Suite** (`.venv\Scripts\python -m pytest backend\tests -v`):
   - **97 passed, 2 skipped, 0 failed** (`179.42s`).
   - The 2 skipped tests are existing live-wallet/transaction tests in `test_blockchain_milestone2.py` (`test_wallet_balance_and_insufficient_funds_rejection`, `test_live_transaction_anchoring_and_receipt_confirmation`) that intentionally skip without spending Sepolia ETH.
3. **Frontend TypeScript & Vite Production Build** (`npm --prefix frontend run build`):
   - `tsc -b && vite build` exited with code `0`, transforming `2094` modules into `dist/assets/index-bb8yrJm-.js` (`459.50 kB`) and `dist/assets/index-5W5vzbS2.css` (`40.34 kB`) in `5.97s`.

### 7.2 Blockchain, Model Weights & Runtime Call-Site Integrity
- **Sepolia Read-Only Verification:** Connected to Sepolia (`chain_id = 11155111`, contract `0xcDa4CE06d44642Fd0034C817B5b7cB6AFC886ffb`, `total_verifications = 1`); `verif-9c524ca7b6f5` verified `VERIFIED_TAMPER_FREE` (`hash_matched = True`, hash `42007960ae4bf66cbc74dfb24ef80429fdba86ca34de3bc1a8d0ff9c16a2cc53`, 0 transactions sent, 0 Sepolia ETH spent).
- **Trained Model Files (`Requirements/`):** SHA-256 checksums and original timestamps (`2026-11-06T07:15`–`07:20Z`) confirmed unchanged across `bert_isot_temporal_v1`, `bert_liar_v1`, `fever_verifier_v1`, `wiki_fever.index`, `sentences.jsonl`, and `row_mapping.jsonl`.
- **Single-Gateway Enforcement:** Recursive scan confirmed no unguarded direct `api.gdeltproject.org` HTTP calls exist outside `gdelt_client.py` (with `news_service.py` default seed row URL executed strictly through `gdelt_client.fetch_feed_articles()`).

---

## 8. File Inventory (Phase 2 / Group E)

### Created Files
- `backend/app/services/external_apis/__init__.py`
- `backend/app/services/external_apis/quota_db.py`
- `backend/app/services/external_apis/evidence_cache.py`
- `backend/app/services/external_apis/gdelt_usage_tracker.py`
- `backend/app/services/external_apis/google_factcheck_client.py`
- `backend/app/services/external_apis/gdelt_client.py`
- `backend/app/services/external_apis/evidence_aggregator.py`
- `frontend/src/components/ui/ExternalEvidenceSection.tsx`
- `frontend/src/components/ui/ExternalApiUsageCard.tsx`
- `backend/tests/conftest.py`
- `backend/tests/test_external_apis.py`
- `docs/PHASE2_GROUP_E_IMPLEMENTATION_REPORT.md`

### Modified Files
- `.env.example`
- `backend/app/config.py`
- `backend/app/schemas/verification.py`
- `backend/app/schemas/article.py`
- `backend/app/schemas/news.py`
- `backend/app/services/news_service.py`
- `backend/app/api/routes/news.py`
- `backend/app/services/verification_service.py`
- `frontend/src/types/verification.ts`
- `frontend/src/api/verify.ts`
- `frontend/src/components/ui/EvidenceCard.tsx`
- `frontend/src/components/layout/Sidebar.tsx`
- `frontend/src/pages/TextVerify.tsx`
- `frontend/src/pages/ArticleVerify.tsx`
- `frontend/src/pages/LiveNews.tsx`

---

## 9. Completion Boundary

Phase 2 / Group E implementation and mocked verification are complete. Production GDELT quota sits at **0 / 200** (`200` remaining). No live API quota was consumed during automated testing. Further phases or live integration tests will proceed only upon explicit user authorization.
