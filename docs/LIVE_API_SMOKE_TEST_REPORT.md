# FakeNewsBlockchain — Controlled Live API Smoke Test Report

**Project Root:** `D:\Documents\FakeNewsBlockChain`  
**Test Execution Window (UTC):** `2026-11-11T10:09:19.930659+00:00` to `2026-11-11T10:09:29.648615+00:00`  
**Local Time (IST, +05:30):** `2026-11-11 15:39:19` to `15:39:29`  
**Execution Harness:** Read-only/controlled scratch harness calling the existing backend components ([`GoogleFactCheckClient`](file:///D:/Documents/FakeNewsBlockChain/backend/app/services/external_apis/google_factcheck_client.py#L70), [`GdeltClient`](file:///D:/Documents/FakeNewsBlockChain/backend/app/services/external_apis/gdelt_client.py#L75), [`GdeltUsageTracker`](file:///D:/Documents/FakeNewsBlockChain/backend/app/services/external_apis/gdelt_usage_tracker.py#L70), [`ExternalEvidenceCache`](file:///D:/Documents/FakeNewsBlockChain/backend/app/services/external_apis/evidence_cache.py#L22)) wrapped with a strict single-attempt guard (maximum 1 outbound request per provider, zero retries).

---

## Provider Status Summary

| Provider | Outcome Label | Outbound HTTP Requests | Retries Attempted | HTTP Status / Exception | Cache State After Call |
|---|---|---:|---:|---|---|
| **Google Fact Check Tools API** | **SUCCESS** | `1` | `0` | `HTTP 200` (`status="no_results"`) | Fresh retrieval (`from_cache=false`), cached in SQLite |
| **GDELT DOC 2.0 (`ArtList`)** | **FAILED** | `1` | `0` | `ReadTimeout` (`status="network_error"`, no HTTP response) | Cache miss (`from_cache=false`), failure NOT cached |

---

## 1. Test Date & Time

- **Started (UTC):** `2026-11-11T10:09:19.930659+00:00`
- **Finished (UTC):** `2026-11-11T10:09:29.648615+00:00`

---

## 2. Google Fact Check Tools API Result — **SUCCESS**

- **Provider Outcome:** **SUCCESS** (live endpoint reached cleanly; API credentials valid; returned valid JSON response).
- **API Key Configuration:** Configured in backend `.env` (`GOOGLE_FACT_CHECK_API_KEY` present; secret value never displayed).
- **Submitted Query:** `NASA Space Shuttle currently flies regular astronaut missions to the International Space Station` (`max_results = 5`, `languageCode = "en"`).
- **Outbound HTTP Requests Made:** `1` (0 retries).
- **Reached Google:** `True` (`HTTP 200`).
- **Client Status:** `no_results`
- **Number of Reviews Returned:** `0`
- **Publisher Names:** None returned for this query.
- **Original Rating Text:** None returned for this query.
- **Review Dates:** None returned for this query.
- **Review URLs:** None returned for this query.
- **Conflicting / Stale Reviews Detected:** `has_conflicting_reviews = False`, `has_stale_reviews = False`.
- **Cache vs. Fresh Retrieval:** Freshly retrieved (`from_cache = False`), then cached in `external_evidence_cache`.
- **Epistemic Discipline:** Per verification policy, an empty response (`no_results`) was **never** converted into `GENUINE` or `FAKE` and does not alter local/Wikipedia verification verdicts.

---

## 3. GDELT DOC 2.0 Result — **FAILED**

- **Provider Outcome:** **FAILED** (`ReadTimeout` during live outbound HTTP request; safely failed without retry and remained counted in SQLite quota).
- **Submitted Query:** `2026 Artemis NASA lunar mission November` (`mode = "ArtList"`, `timespan = "1week"`, `maxrecords = 5`, `sourcelang:eng`, `max_retries = 0`).
- **Pre-Request Cache Lookup:** Checked first; cache miss (`from_cache = False`).
- **Pre-HTTP Quota Reservation Confirmed:** Inside `HardSingleAttemptSession.get()` immediately prior to the outbound socket call, SQLite `gdelt_usage_state.requests_used` already measured **`1`** (incremented from `0` via atomic `BEGIN IMMEDIATE` before network I/O).
- **Outbound HTTP Requests Made:** `1` (0 retries).
- **HTTP Status / Error:** No HTTP status code received; timed out with exception `ReadTimeout`:
  `GDELT request error: HTTPSConnectionPool(host='api.gdeltproject.org', port=443): Read timed out. (read timeout=5.0)`
- **Client Status:** `network_error`
- **Number of Articles Returned:** `0` (`raw_count = 0`)
- **Titles, Domains, Publication Dates, URLs:** None returned due to upstream timeout.
- **Duplicates Removed:** `0`
- **Cache vs. Fresh Attempt:** `from_cache = False`; failed attempt was NOT written to `external_evidence_cache`.
- **Request Counted Toward Quota:** **Yes (`True`)** — remained counted (`requests_used = 1`, `failed_requests = 1`) and was never refunded.

---

## 4. Actual Request Counts

- **Google Fact Check Tools API:** `1` outbound HTTP request (`<= 1` limit respected; 0 retries).
- **GDELT DOC 2.0:** `1` outbound HTTP request (`<= 1` limit respected; 0 retries; no fallback refresh run).
- **Total Sepolia Transactions:** `0` (read-only status and integrity calls only; `0` Sepolia ETH spent).

---

## 5. Before / After GDELT Quota (`data/news_cache.db`)

Verified directly from `gdelt_usage_state` (`id = 1`):

| Metric | Before Smoke Test | During Pre-HTTP Check | After Smoke Test |
|---|---:|---:|---:|
| `allowance_limit` | `200` | `200` | `200` |
| `requests_used` | `0` | `1` *(atomic pre-flight)* | `1` |
| `requests_remaining` | `200` | `199` | `199` |
| `warning_threshold` | `20` | `20` | `20` |
| `warning_active` | `False` | `False` | `False` |
| `limit_reached` | `False` | `False` | `False` |
| `cache_hits` | `0` | `0` | `0` |
| `failed_requests` | `0` | `0` | `1` |
| `last_source` | `None` | — | `"live_smoke_test"` |
| `last_status` | `None` | — | `"network_error"` |
| `last_request_at` | `None` | — | `2026-11-11T10:09:20.900400+00:00` |
| `tracker_available` | `True` | `True` | `True` |

---

## 6. Sample Returned Evidence & Attribution

- **Google Fact Check Tools:** `0` ClaimReview items matched the verbatim sentence `"NASA Space Shuttle currently flies regular astronaut missions to the International Space Station"` (`status = "no_results"`). No sample reviews to attribute for this query.
- **GDELT DOC 2.0:** `0` articles returned due to upstream `ReadTimeout` (`status = "network_error"`). No sample articles to display.

---

## 7. Cache Status (`data/news_cache.db` → `external_evidence_cache`)

Inspected `external_evidence_cache` directly after the smoke test:
- **Rows stored:** `1`
  - Provider: `google_fact_check`
  - Normalized query: `nasa space shuttle currently flies regular astronaut missions to the international space station`
  - `fetched_at`: `2026-11-11T10:09:20.882927+00:00`
  - `expires_at`: `2026-11-12T10:09:20.882927+00:00` (`24`h TTL)
  - `hit_count`: `0`
- **GDELT cache rows:** `0` (timed-out GDELT requests are intentionally never cached).

---

## 8. Errors & Observed Limitations

1. **GDELT Upstream Latency (`ReadTimeout`):** `api.gdeltproject.org` did not finish sending its response payload within the enforced read timeout during this single-attempt probe, confirming both the client's graceful `network_error` degradation and non-refunded failure quota accounting (`requests_used = 1`, `failed_requests = 1`).
2. **Google Fact Check Query Specificity:** Sending a full multi-clause claim sentence (`NASA Space Shuttle currently flies regular astronaut missions to the International Space Station`) returned `HTTP 200` with `0` ClaimReview matches (`no_results`), illustrating that Google Claim Search often matches shorter entity/event keywords better than full declarative sentences and confirming that absence of ClaimReviews is handled conservatively (`no_results`) without inferring truth values.

---

## 9. Credential-Safety Result

- `key_in_logs`: `False` (runtime logging handler clean)
- `secret_in_log_files`: `False` (checked all `2` files in `logs/`)
- `key_in_output`: `False` (serialized test JSON clean)
- `secret_sent_to_gdelt`: `False` (verified neither `key` param nor API secret value existed in GDELT HTTP request `url`, `params`, or `headers`)
- Google `.env` credential value was never printed or exposed anywhere.

---

## 10. Database, Model & Blockchain Integrity Result

| Asset / Check | Pre-Smoke / Baseline Value | Post-Smoke Value | Status |
|---|---|---|---|
| `data/database/fakenews.db` SHA-256 | `35fc2f2cc41d6b100f1d2ad81844112d9ead2c286c95f95b45fcded9aee4e38f` | `35fc2f2cc41d6b100f1d2ad81844112d9ead2c286c95f95b45fcded9aee4e38f` | **UNCHANGED** |
| `verification_records` row count | `185` | `185` | **UNCHANGED** |
| `FakeNewsBlockchain_Certificate_verif-9c524ca7b6f5.pdf` SHA-256 | `6fd922813127302e458157caeea5498e246ba6e69099d4235f635529a7d603db` | `6fd922813127302e458157caeea5498e246ba6e69099d4235f635529a7d603db` | **UNCHANGED** |
| `data/news_cache.db` `news_articles` / `news_sources` | `279` / `5` | `279` / `5` | **UNCHANGED** |
| Sepolia contract (`0xcDa4CE06d44642Fd0034C817B5b7cB6AFC886ffb`) | `total_verifications = 1` | `total_verifications = 1` (`latest_block = 12111065`) | **READ-ONLY / 0 TX** |
| Certificate `verif-9c524ca7b6f5` on-chain match | `VERIFIED_TAMPER_FREE` (`hash_matched = True`) | `VERIFIED_TAMPER_FREE` (`hash_matched = True`, `42007960ae4bf66c...`) | **VALIDATED** |
| `Requirements/wiki_fever.index` SHA-256 | `1c8eb578608f2f15b97f74f718d72ffed8f470b643cbd330ceba6c25fd014a6d` | `1c8eb578608f2f15b97f74f718d72ffed8f470b643cbd330ceba6c25fd014a6d` | **UNCHANGED** |
| `Requirements/fever_verifier_v1/model.safetensors` SHA-256 | `8c0dc00dd3c39c0879c6e751de63d870ca21305906df2add67e546f060d2209e` | `8c0dc00dd3c39c0879c6e751de63d870ca21305906df2add67e546f060d2209e` | **UNCHANGED** |
| `Requirements/bert_isot_temporal_v1/model.safetensors` SHA-256 | `ca9eccc3b08f9c1d75ba5b4f9c67ef5a40a1ff6c8c1badd8e2081cf4fe125cad` | `ca9eccc3b08f9c1d75ba5b4f9c67ef5a40a1ff6c8c1badd8e2081cf4fe125cad` | **UNCHANGED** |
| `Requirements/bert_liar_v1/final_model/model.safetensors` SHA-256 | `d75c183e2fca1e6d31cc077bd074ef12834d2a1fd705394e3e67885f77f5ed87` | `d75c183e2fca1e6d31cc077bd074ef12834d2a1fd705394e3e67885f77f5ed87` | **UNCHANGED** |
| Project source files | — | Zero edits made during smoke test | **UNCHANGED** |

---

## Stop Notice

Controlled live API smoke test completed with strict 1-request bounds (`1` Google request, `1` GDELT request, `199` remaining GDELT allowance). Stopping cleanly as instructed; no additional live requests or source modifications will run without explicit authorization.
