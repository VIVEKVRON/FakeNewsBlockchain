# FakeNewsBlockchain — GDELT Remediation Implementation Report

**Project Root:** `D:\Documents\FakeNewsBlockChain`  
**Implementation Date (IST / UTC):** `2026-11-11 16:02 IST` / `2026-11-11T10:32Z`  
**Scope:** Controlled source-code remediation based on [GDELT_OFFLINE_DIAGNOSTIC_REPORT.md](file:///D:/Documents/FakeNewsBlockChain/docs/GDELT_OFFLINE_DIAGNOSTIC_REPORT.md) covering GDELT timeouts, exception distinction, quota conservation (`GDELT_MAX_RETRIES=0`), concise query & `1month` timespan validation, SQLite schema-init optimization, FastAPI event-loop offloading (`run_in_threadpool`), and bounded ML CPU inference concurrency.

---

## 1. Initial Diagnostic Findings Confirmed or Disproved

Every root finding documented in [GDELT_OFFLINE_DIAGNOSTIC_REPORT.md](file:///D:/Documents/FakeNewsBlockChain/docs/GDELT_OFFLINE_DIAGNOSTIC_REPORT.md) was confirmed against the live codebase prior to editing:
1. **Confirmed — Hardcoded 5s Connect/TLS Clamp:** [`gdelt_client.py`](file:///D:/Documents/FakeNewsBlockChain/backend/app/services/external_apis/gdelt_client.py#L260) clamped the tuple connect timeout via `min(5.0, timeout_sec)`, constraining both TCP connect and TLS handshake in `urllib3 2.8.0` (`_validate_conn`) to `5.0`s even when `GDELT_TIMEOUT_SEC` was `8.0`s. *(Fixed)*
2. **Confirmed — Collapsed Timeout Telemetry & Retry Quota Burn:** `requests.ConnectTimeout`, `requests.ReadTimeout`, and `requests.Timeout` all collapsed into `"timeout"`, and default `GDELT_MAX_RETRIES=1` permitted 2x quota burn on transient timeouts/429/5xx. *(Fixed)*
3. **Confirmed — Heavy `3months` Window & Temporal Noise in GDELT Queries:** `search_coverage` defaulted to `timespan="3months"`, and `build_focused_claim_queries()` allowed month names, 4-digit years, and up to 6–7 terms in GDELT AND queries. *(Fixed)*
4. **Confirmed — FastAPI Event-Loop Starvation in `verify.py`:** `verify_text` and `verify_article` were `async def` handlers calling synchronous CPU PyTorch inference and blocking external HTTP directly on the asyncio event loop. *(Fixed via `run_in_threadpool` + bounded inference semaphore)*
5. **Confirmed — Repeated `ensure_external_tables()` DDL:** Every quota/cache DB operation ran `CREATE TABLE IF NOT EXISTS` / `INSERT OR IGNORE`. *(Fixed safely via inode-keyed `ensure_external_tables_once()` + startup hook)*
6. **Preserved Unchanged — Google Fact Check Timeout:** Per remediation rules, `google_factcheck_client.py` timeouts were left untouched (`(min(5.0, timeout_sec), timeout_sec)`).

---

## 2. Files Modified & Exact Changes

1. [`backend/app/config.py`](file:///D:/Documents/FakeNewsBlockChain/backend/app/config.py) & [`.env.example`](file:///D:/Documents/FakeNewsBlockChain/.env.example)
   - Added [`validate_gdelt_timespan()`](file:///D:/Documents/FakeNewsBlockChain/backend/app/config.py#L26-L50) validating `<N><min|h|d|days|w|week|m|month>` formats with safe unit bounds (`min <= 1440`, `h <= 168`, `d <= 365`, `w <= 52`, `m <= 12`).
   - Added `GDELT_CONNECT_TIMEOUT_SEC: float = 8.0`, updated `GDELT_TIMEOUT_SEC: float = 12.0`, set `GDELT_MAX_RETRIES: int = 0`, added `GDELT_DEFAULT_TIMESPAN: str = "1month"`.
   - Added Pydantic `@field_validator` checks rejecting negative, zero, non-finite, or `> 60.0`s timeouts, invalid retry counts (`0..2`), and invalid default timespans.
2. [`backend/app/services/external_apis/gdelt_client.py`](file:///D:/Documents/FakeNewsBlockChain/backend/app/services/external_apis/gdelt_client.py)
   - Added `_resolve_timeouts(settings)` validating finite `(connect_t, read_t)` in `(0.0, 60.0]`; removed hardcoded `min(5.0, timeout_sec)` clamp and passed `timeout=(connect_timeout, read_timeout)` explicitly to `self._session.get()`.
   - Separated exception handlers in inheritance order (`requests.ConnectTimeout` -> `"connect_timeout"`, `requests.ReadTimeout` -> `"read_timeout"`, `requests.Timeout` -> `"timeout"`, `HTTP 429` -> `"rate_limited"`, non-2xx/5xx -> `"http_error"`, `RequestException` -> `"network_error"`).
   - Removed automatic retries on `ConnectTimeout`, `ReadTimeout`, generic `Timeout`, `HTTP 429`, and non-5xx `RequestException`; defaulted `GDELT_MAX_RETRIES` to `0` (preserving optional bounded 5xx retry only if configured `> 0`, reserving 1 quota slot per attempt).
   - Updated `search_coverage(timespan: Optional[str] = None)` to use `GDELT_DEFAULT_TIMESPAN` (`"1month"`), validate timespans via `validate_gdelt_timespan()`, and reject invalid timespans safely (`status="invalid_timespan"`, `0` HTTP calls, `0` quota). Also validated `feed_url` `timespan` in `fetch_feed_articles()`.
3. [`backend/app/services/external_apis/evidence_aggregator.py`](file:///D:/Documents/FakeNewsBlockChain/backend/app/services/external_apis/evidence_aggregator.py)
   - Updated [`build_focused_claim_queries()`](file:///D:/Documents/FakeNewsBlockChain/backend/app/services/external_apis/evidence_aggregator.py) while keeping Google Fact Check `fc_query` unchanged.
   - Filtered month names, weekday names, leading phrase determiners (`The`, `On`, `In`, etc.), and generic temporal filler (`currently`, `regular`, `recent`, etc.); preserved multi-word entities, uppercase acronyms, and subject terms cleanly within `3–5` high-signal GDELT terms (using 4-digit years only as fallback if fewer than `3` non-temporal terms exist).
4. [`backend/app/schemas/verification.py`](file:///D:/Documents/FakeNewsBlockChain/backend/app/schemas/verification.py)
   - Updated `NewsEvidenceSchema.search_window` default from `"3months"` to `"1month"`.
5. [`backend/app/services/external_apis/quota_db.py`](file:///D:/Documents/FakeNewsBlockChain/backend/app/services/external_apis/quota_db.py), [`gdelt_usage_tracker.py`](file:///D:/Documents/FakeNewsBlockChain/backend/app/services/external_apis/gdelt_usage_tracker.py), [`evidence_cache.py`](file:///D:/Documents/FakeNewsBlockChain/backend/app/services/external_apis/evidence_cache.py), & [`backend/app/main.py`](file:///D:/Documents/FakeNewsBlockChain/backend/app/main.py)
   - Added thread-safe inode-keyed [`ensure_external_tables_once()`](file:///D:/Documents/FakeNewsBlockChain/backend/app/services/external_apis/quota_db.py) and `GdeltUsageTracker.ensure_schema()` called once during FastAPI `lifespan`, preserving fail-closed behavior and fresh/temporary DB creation in tests without repeating DDL on every read/write.
6. [`ml/inference/model_loader.py`](file:///D:/Documents/FakeNewsBlockChain/ml/inference/model_loader.py), [`claim_verifier.py`](file:///D:/Documents/FakeNewsBlockChain/ml/inference/claim_verifier.py), [`article_classifier.py`](file:///D:/Documents/FakeNewsBlockChain/ml/inference/article_classifier.py), [`claim_classifier.py`](file:///D:/Documents/FakeNewsBlockChain/ml/inference/claim_classifier.py), [`ml/rag/retriever.py`](file:///D:/Documents/FakeNewsBlockChain/ml/rag/retriever.py), [`verification_service.py`](file:///D:/Documents/FakeNewsBlockChain/backend/app/services/verification_service.py), & [`backend/app/api/routes/verify.py`](file:///D:/Documents/FakeNewsBlockChain/backend/app/api/routes/verify.py)
   - Converted `verify_text` and `verify_article` handlers to offload synchronous work off the asyncio event loop via `await run_in_threadpool(...)` and added `threading.Lock()` double-checked locking around `get_verification_service()`.
   - Added `get_ml_inference_semaphore()` (`threading.BoundedSemaphore(1)`) around local CPU PyTorch forward passes / SentenceTransformer+FAISS search inside `ClaimVerifier.verify()`, `ArticleClassifier.classify()`, `ClaimClassifier.classify()`, and `FAISSRetriever.retrieve()`—never holding locks across Wikipedia, Google Fact Check, or GDELT network requests, and never blocking `/api/v1/health`, `/api/v1/history`, or `/api/v1/news/gdelt-usage`.
7. [`backend/tests/test_external_apis.py`](file:///D:/Documents/FakeNewsBlockChain/backend/tests/test_external_apis.py)
   - Updated mock settings defaults and added `TestGdeltRemediationImprovements` covering all timeout, retry, timespan, query, inference concurrency, and off-event-loop tests.

---

## 3. Timeout Configuration Before & After

| Parameter / Behavior | Before Remediation | After Remediation |
|---|---|---|
| `GDELT_CONNECT_TIMEOUT_SEC` | Not configurable (hardcoded `min(5.0, GDELT_TIMEOUT_SEC)`) | **`8.0`s** configurable & validated `(0.0, 60.0]` |
| `GDELT_TIMEOUT_SEC` *(read timeout)* | `8.0`s | **`12.0`s** configurable & validated `(0.0, 60.0]` |
| HTTP `timeout=` passed | `(5.0, 8.0)` *(TLS handshake clamped to `5.0`s)* | **`(8.0, 12.0)`** *(decoupled connect/TLS & read budgets)* |
| Timeout validation | Silent clamping (`max(2.0, ...)`) | Strict `ValueError` / `ValidationError` on invalid config |
| Timeout telemetry distinction | Single `"timeout"` bucket for all `requests.Timeout` | Explicit `"connect_timeout"`, `"read_timeout"`, `"timeout"` |

---

## 4. Retry & Quota Behavior Before & After

| Scenario | Before Remediation (`GDELT_MAX_RETRIES=1`) | After Remediation (`GDELT_MAX_RETRIES=0`) |
|---|---|---|
| Normal default outbound attempts / search | Up to `2` attempts on error | **`1` attempt max** |
| `ConnectTimeout` / `ReadTimeout` / `Timeout` | Retried (`2` slots burned, ~16s block) | **No retry (`1` slot consumed, non-refunded)** |
| `HTTP 429` rate limit | Retried (`2` slots burned) | **No retry (`1` slot consumed, non-refunded)** |
| `HTTP 5xx` server error | `2` attempts (`2` slots) | **`1` attempt by default** (bounded `1 + retries` only if `GDELT_MAX_RETRIES > 0`) |
| Cache hit / Quota exhausted (`200`) / Invalid timespan | Cache `0` / Exhausted `0` *(no timespan check)* | Cache `0` / Exhausted `0` fail-closed / Invalid timespan `0` |
| Shared hard allowance | `200` requests | **`200` requests (unchanged)** |

---

## 5. Query & Timespan Behavior Before & After

| Aspect | Before Remediation | After Remediation |
|---|---|---|
| Default `search_coverage` `timespan` | `"3months"` | **`"1month"`** (`GDELT_DEFAULT_TIMESPAN`, validated) |
| Explicit valid timespan (e.g. `"1week"`, `"24h"`) | Used unvalidated | **Validated & preserved** (`validate_gdelt_timespan`) |
| Invalid timespan (e.g. `"0days"`, `"bad&x=1"`) | Sent raw to GDELT | **Rejected pre-request (`status="invalid_timespan"`, 0 HTTP/quota)** |
| `build_focused_claim_queries()` GDELT terms | Up to 6–7 terms + appended 4-digit years + months + `"The ..."` phrases | **Concise 3–5 high-signal entity/topic terms**, month/weekday/temporal noise stripped unless `< 3` terms exist; `fc_query` unchanged |

---

## 6. FastAPI Concurrency Changes

- `POST /api/v1/verify/text` and `POST /api/v1/verify/article` remain `async def` endpoints in [`verify.py`](file:///D:/Documents/FakeNewsBlockChain/backend/app/api/routes/verify.py) while delegating [`get_verification_service()`](file:///D:/Documents/FakeNewsBlockChain/backend/app/services/verification_service.py#L720) initialization (thread-safe double-checked locking) and execution through `await run_in_threadpool(...)`.
- Simultaneous CPU PyTorch inference (`ClaimVerifier`, `ArticleClassifier`, `ClaimClassifier`) and `FAISSRetriever.retrieve()` vector encoding/search are bounded by `_ML_INFERENCE_SEMAPHORE = threading.BoundedSemaphore(1)` in [`model_loader.py`](file:///D:/Documents/FakeNewsBlockChain/ml/inference/model_loader.py), preventing RAM exhaustion on the 16 GB machine without ever acquiring locks during Wikipedia, Google Fact Check, or GDELT HTTP I/O.
- Lightweight endpoints (`/api/v1/health`, `/api/v1/news/gdelt-usage`, `/api/v1/history`) stay completely unblocked while slow external verification requests run.

---

## 7. Tests Executed & Exact Results (All Mocked / Offline HTTP)

1. **Targeted External APIs & Remediation Suite** (`.venv\Scripts\python -m pytest backend\tests\test_external_apis.py -v`):
   - **27 passed, 0 failed** (`38.32s`).
   - Verified all 17 required offline cases: decoupled `(8.0, 12.0)` / custom `(9.5, 15.0)` timeouts, invalid timeout rejection, `connect_timeout` / `read_timeout` / generic `timeout` distinction, zero retry on HTTP 429 & timeouts even if `GDELT_MAX_RETRIES=1`, 1 call max default on `500`, failed-slot non-refund, 0-cost cache hit, fail-closed quota cap, `"1month"` default + explicit timespan preservation + invalid timespan rejection (`0` calls), concise entity-preserving queries, Google Fact Check compatibility, `BoundedSemaphore(1)` ML cap, and off-event-loop execution of `/verify/text` & `/verify/article` leaving `/api/v1/health` and `/api/v1/news/gdelt-usage` responsive (`< 0.5`s).
2. **Full Backend Regression Suite** (`.venv\Scripts\python -m pytest backend\tests -v`):
   - **103 passed, 2 skipped, 0 failed** (`143.78s`).
   - The 2 skipped cases remain existing live-wallet/live-transaction tests in `test_blockchain_milestone2.py`.
3. **Frontend Production Build** (`npm --prefix frontend run build`):
   - `tsc -b && vite build` exited with code `0`, `2094` modules built (`4.82s`).

---

## 8. Production Database, Model & Blockchain Integrity Checks

| Check | Pre-Remediation / Baseline | Post-Remediation Verified | Status |
|---|---|---|---|
| `data/database/fakenews.db` SHA-256 | `35fc2f2cc41d6b100f1d2ad81844112d9ead2c286c95f95b45fcded9aee4e38f` | `35fc2f2cc41d6b100f1d2ad81844112d9ead2c286c95f95b45fcded9aee4e38f` | **UNCHANGED** |
| Production history records (`verification_records`) | `185` | `185` | **UNCHANGED** |
| `data/news_cache.db` `news_articles` / `news_sources` | `279` / `5` | `279` / `5` | **UNCHANGED** |
| Shared GDELT quota (`gdelt_usage_state`) | `(200, 1, 0, 1, 'live_smoke_test', 'network_error')` (`199` left) | `(200, 1, 0, 1, 'live_smoke_test', 'network_error')` (`199` left) | **UNCHANGED** |
| `external_evidence_cache` rows | `1` Google Fact Check row (`0` GDELT rows) | `1` Google Fact Check row (`0` GDELT rows) | **INTACT** |
| Certificate PDF (`FakeNewsBlockchain_Certificate_verif-9c524ca7b6f5.pdf`) SHA-256 | `6fd922813127302e458157caeea5498e246ba6e69099d4235f635529a7d603db` | `6fd922813127302e458157caeea5498e246ba6e69099d4235f635529a7d603db` | **UNCHANGED** |
| Sepolia contract (`0xcDa4CE06d44642Fd0034C817B5b7cB6AFC886ffb`) | `total_verifications = 1` (`0` new tx) | `total_verifications = 1` (`latest_block = 12111178`, `0` new tx) | **UNCHANGED** |
| Certificate `verif-9c524ca7b6f5` on-chain match | `VERIFIED_TAMPER_FREE` (`hash_matched = True`) | `VERIFIED_TAMPER_FREE` (`hash_matched = True`) | **VALID** |
| Trained model & FAISS SHA-256 (`Requirements/`) | Recorded pre-Phase-2 | All 4 core binary checksums identical | **UNCHANGED** |
| Secret exposure (`SECRET_IN_LOGS` / `SECRET_IN_DOCS`) | `False` | `False` (`.env` untouched) | **CLEAN** |

---

## 9. Confirmation: No Live HTTP Calls & Zero Quota Consumed

- All tests executed through mocked HTTP `requests.Session` instances and `backend/tests/conftest.py` database/HTTP isolation guards.
- **Zero live HTTP requests** were sent to GDELT, Google Fact Check, Wikipedia, or any external news source during remediation or testing.
- **Zero GDELT quota units** were consumed (`requests_used` remains `1 / 200`; `199` remaining).

---

## 10. Unresolved Risks & Deferred Changes

1. **Google Fact Check Timeout Clamp Untouched:** [`google_factcheck_client.py:244`](file:///D:/Documents/FakeNewsBlockChain/backend/app/services/external_apis/google_factcheck_client.py#L244) still uses `timeout=(min(5.0, timeout_sec), timeout_sec)` as instructed to preserve Google Fact Check timeout behavior in this remediation scope; it can be aligned cleanly in a future change if slow Google TLS handshakes are observed.
2. **Synchronous Inline External Calls on Verification Latency:** While FastAPI no longer freezes the event loop, an individual `/verify/text` or `/verify/article` call still waits synchronously on its worker thread for external enrichment (up to `8s` connect + `12s` read worst case if GDELT stalls), trading per-request tail latency for complete response completeness.
3. **Live GDELT Connectivity Re-Verification Deferred:** Live confirmation that `GDELT_CONNECT_TIMEOUT_SEC=8.0` and `GDELT_TIMEOUT_SEC=12.0` resolve the upstream `api.gdeltproject.org` latency awaits user approval if/when a single controlled live check is authorized.
