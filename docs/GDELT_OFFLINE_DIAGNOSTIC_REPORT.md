# FakeNewsBlockchain — GDELT DOC 2.0 Offline Diagnostic Report

**Project Root:** `D:\Documents\FakeNewsBlockChain`  
**Diagnostic Date (IST / UTC):** `2026-11-11 15:45 IST` / `2026-11-11T10:15Z`  
**Mode:** Read-only code inspection + 100% offline mocked / local-loopback diagnostics (0 live HTTP calls, 0 GDELT quota consumed, 0 source edits).

---

## Executive Finding

The live smoke test failure against GDELT DOC 2.0:

> `GDELT request error: HTTPSConnectionPool(host='api.gdeltproject.org', port=443): Read timed out. (read timeout=5.0)`

occurred even though [`config.py`](file:///D:/Documents/FakeNewsBlockChain/backend/app/config.py#L58) sets `GDELT_TIMEOUT_SEC = 8.0`.  
Offline inspection and local loopback reproduction identified the exact mechanism: [`gdelt_client.py`](file:///D:/Documents/FakeNewsBlockChain/backend/app/services/external_apis/gdelt_client.py#L260) passes `timeout=(min(5.0, timeout_sec), timeout_sec)` = `(5.0, 8.0)`, and **`urllib3 2.8.0` (`HTTPSConnectionPool._make_request`) reuses the `5.0`s `connect` timeout across the TLS/SSL handshake inside `_validate_conn()` and translates a TLS handshake `SocketTimeout` into `ReadTimeoutError("Read timed out. (read timeout=5.0)")`** before `conn.timeout` is ever promoted to `8.0`s for HTTP response reading.

Additionally, inspecting [`verify.py`](file:///D:/Documents/FakeNewsBlockChain/backend/app/api/routes/verify.py#L28-L51) exposed a major concurrency bottleneck: `/api/v1/verify/text` and `/api/v1/verify/article` are declared `async def` yet call synchronous blocking verification and HTTP I/O directly on the FastAPI asyncio event loop.

---

## 1. Root Cause of the Observed Timeout (`(read timeout=5.0)`)

### Exact Runtime Chain Observed in `urllib3 2.8.0` / `requests 2.34.2`
1. [`gdelt_client.py:233`](file:///D:/Documents/FakeNewsBlockChain/backend/app/services/external_apis/gdelt_client.py#L233) resolves `timeout_sec = 8.0` from `Settings.GDELT_TIMEOUT_SEC`.
2. [`gdelt_client.py:260`](file:///D:/Documents/FakeNewsBlockChain/backend/app/services/external_apis/gdelt_client.py#L260) passes `timeout=(min(5.0, 8.0), 8.0)` = `(5.0, 8.0)` to `self._session.get(...)`.
3. `requests.adapters.HTTPAdapter.send()` converts that tuple into `urllib3.util.Timeout(connect=5.0, read=8.0)`.
4. Inside `urllib3.connectionpool.HTTPSConnectionPool._make_request()` (`urllib3/connectionpool.py`):
   - **Line 465:** `conn.timeout = Timeout.resolve_default_timeout(timeout_obj.connect_timeout)` sets **`conn.timeout = 5.0`**.
   - **Line 470:** `self._validate_conn(conn)` invokes `HTTPSConnection.connect()` (`urllib3/connection.py:792-895`), which:
     1. Opens the TCP socket via `_new_conn()` (`240-251`) using `self.timeout = 5.0`. If TCP SYN fails here, `urllib3` raises `ConnectTimeoutError`.
     2. Immediately runs **TLS handshake** (`_ssl_wrap_socket_and_match_hostname()`, line `878`) on the same socket **still set to `conn.timeout = 5.0`**.
   - **Lines 471-472:** When `SocketTimeout` occurs during `_validate_conn(conn)` (e.g., TLS ServerHello or certificate negotiation stalls beyond `5.0`s), `urllib3` calls:
     `self._raise_timeout(err=e, url=url, timeout_value=conn.timeout)`
     which unconditionally raises `ReadTimeoutError(self, url, "Read timed out. (read timeout=5.0)")`, converted by `requests` into `requests.exceptions.ReadTimeout`.
   - Only *after* `_validate_conn(conn)` succeeds does line `536` set `conn.timeout = read_timeout` (`8.0`). Therefore, a post-handshake HTTP read timeout would display `(read timeout=8.0)`, whereas a TLS-handshake stall (or proxy tunnel setup at line `781`) displays **`(read timeout=5.0)`**.

### Offline Loopback Reproduction Proof
Executed locally on `127.0.0.1` ephemeral sockets (zero external network traffic):
- **Stalled TLS handshake (`https://127.0.0.1`, `timeout=(0.25, 1.0)`):** Raised `ReadTimeout` with message:
  `HTTPSConnectionPool(host='127.0.0.1', port=57299): Read timed out. (read timeout=0.25)` *(Connect timeout value reported as `read timeout=`!)*.
- **Post-connect HTTP body stall (`http://127.0.0.1`, `timeout=(0.25, 0.45)`):** Raised `ReadTimeout` with message:
  `HTTPConnectionPool(host='127.0.0.1', port=57301): Read timed out. (read timeout=0.45)` *(Read timeout value reported)*.

*Note on smoke-test status label:* In [`live_api_smoke_test.py`](C:/Users/ADMIN/.gemini/antigravity/brain/196b0c18-ecec-450a-83e7-f75c18a8277f/scratch/live_api_smoke_test.py), the single-attempt wrapper caught `ReadTimeout` and re-raised `SmokeAbortNoRetry(requests.RequestException)` to guarantee zero retries, causing [`gdelt_client.py:328`](file:///D:/Documents/FakeNewsBlockChain/backend/app/services/external_apis/gdelt_client.py#L328-L331) to log `last_status = "network_error"`. In normal production execution without the wrapper, `requests.ReadTimeout` hits [`gdelt_client.py:321`](file:///D:/Documents/FakeNewsBlockChain/backend/app/services/external_apis/gdelt_client.py#L321) and records `last_status = "timeout"`.

---

## 2. Exact Timeout Configuration Path

| Stage | Location | Value Observed | Notes |
|---|---|---|---|
| 1. Environment file | `.env` | `GDELT_TIMEOUT_SEC` unset | Only `GDELT_ENABLED=true`, `GDELT_REQUEST_LIMIT=200`, `GDELT_WARNING_THRESHOLD=20` present in `.env`. |
| 2. Settings model | [`backend/app/config.py:58`](file:///D:/Documents/FakeNewsBlockChain/backend/app/config.py#L58) | `GDELT_TIMEOUT_SEC = 8.0` | Confirmed via `get_settings().GDELT_TIMEOUT_SEC -> 8.0`. |
| 3. Client resolution | [`gdelt_client.py:233`](file:///D:/Documents/FakeNewsBlockChain/backend/app/services/external_apis/gdelt_client.py#L233) | `timeout_sec = max(2.0, 8.0) = 8.0` | Floor-clamped to `>= 2.0`s. |
| 4. HTTP call tuple | [`gdelt_client.py:260`](file:///D:/Documents/FakeNewsBlockChain/backend/app/services/external_apis/gdelt_client.py#L260) | `timeout=(min(5.0, 8.0), 8.0) = (5.0, 8.0)` | Passed accurately into `self._session.get()` (verified in offline test #1). *(Note: [`google_factcheck_client.py:244`](file:///D:/Documents/FakeNewsBlockChain/backend/app/services/external_apis/google_factcheck_client.py#L244) uses the exact same `min(5.0, timeout_sec)` pattern.)* |
| 5. Transport adapter | `requests/adapters.py:50-51` -> `urllib3/connectionpool.py:465,536` | `connect=5.0`, `read=8.0` | `connect=5.0` covers both TCP connect and TLS handshake; `read=8.0` begins only after `_validate_conn()`. |

---

## 3. Intentional vs. Unintended Behavior

- **Intentional:** Clamping TCP `connect` timeout (`min(5.0, timeout_sec)`) was intentionally written to avoid waiting the full read budget when a remote host is completely unreachable.
- **Unintended:**
  1. `urllib3` applies the `5.0`s `connect` timeout to the entire **TLS handshake**, so `GDELT_TIMEOUT_SEC=8.0` (or setting it to `15.0`) **never increases the TLS handshake budget beyond `5.0`s**.
  2. Misleading error reporting (`(read timeout=5.0)`) makes TLS handshake timeouts indistinguishable from slow HTTP response reads in logs.
  3. [`gdelt_client.py:321-334`](file:///D:/Documents/FakeNewsBlockChain/backend/app/services/external_apis/gdelt_client.py#L321-L334) catches `requests.Timeout` broadly rather than separating `ConnectTimeout` and `ReadTimeout`, masking connection-stage stalls from read-stage stalls.

---

## 4. Query Construction & `timespan` Analysis

Examined [`build_focused_claim_queries()`](file:///D:/Documents/FakeNewsBlockChain/backend/app/services/external_apis/evidence_aggregator.py#L59-L108) and [`GdeltClient.search_coverage()`](file:///D:/Documents/FakeNewsBlockChain/backend/app/services/external_apis/gdelt_client.py#L379-L412):

1. **Parameter Encoding:**
   For the smoke test, `params` sent was:
   `{"query": "2026 Artemis NASA lunar mission November sourcelang:eng", "mode": "ArtList", "maxrecords": 5, "timespan": "1week", "sort": "DateDesc", "format": "json"}`.
   Parameters are valid GDELT DOC 2.0 `ArtList` arguments and encoded safely by `requests`; `"key"` parameters are stripped before sending.
2. **`timespan=1week` vs. Default `3months`:**
   - `timespan=1week` in the smoke test is **much narrower and less expensive** on GDELT's backend than `search_coverage`'s built-in default `timespan="3months"` (~90 days of global full-text indexing + `sort=DateDesc`).
   - Under `3months`, production `verify_text` / `verify_article` calls ask GDELT to scan ~13x more history than `1week`.
3. **Term Conjunction & Density:**
   - The query `"2026 Artemis NASA lunar mission November sourcelang:eng"` requires all 6 unquoted content tokens simultaneously AND sorts by `DateDesc`. Overly specific calendar/month tokens (`2026`, `November`) plus 4 other mandatory terms shrink recall and do extra full-text index intersections, whereas 3–5 high-signal entities/keywords (e.g., `"Artemis" NASA lunar mission`) give faster, cleaner coverage lookup.

---

## 5. Offline Mocked & Loopback Test Results

All 10 requested GDELT scenarios ran offline against temporary SQLite DBs and mocked `requests.Session` objects (zero live HTTP requests; zero production quota change):

| # | Scenario | Status Returned | HTTP Calls Made | Quota Used / Failed | Notes |
|---:|---|---|---:|---:|---|
| 1 | **Fast successful response** | `"ok"` | `1` | `1` / `0` | Returned `1` deduplicated article, stripped `utm_source`, confirmed `timeout=(5.0, 8.0)`. |
| 2 | **Slow response (`0.15s` delay < timeout)** | `"ok"` | `1` | `1` / `0` | Completed cleanly within timeout budget without retry (`0.187s`). |
| 3 | **Connection timeout (`ConnectTimeout`)** | `"timeout"` | `1` | `1` / `1` | Caught cleanly under `requests.Timeout`; slot remained counted (not distinguished from `ReadTimeout`). |
| 4 | **Read timeout (`ReadTimeout`, `5.0s`)** | `"timeout"` | `1` | `1` / `1` | Caught cleanly; slot remained counted; not written to cache. |
| 5 | **HTTP 429 (`Too Many Requests`)** | `"rate_limited"` | `1` | `1` / `1` | Counted toward failed requests and blocked cleanly. |
| 6 | **HTTP 500 (`max_retries=1` default)** | `"http_error"` | `2` | `2` / `2` | Retry loop bounded at 2 attempts; each attempt reserved and consumed its own SQLite quota slot. |
| 7 | **Malformed JSON (`ValueError`)** | `"invalid_response"` | `1` | `1` / `1` | Handled without crash or retry; counted as failed request. |
| 8 | **Empty article list (`{"articles": []}`)** | `"no_results"` | `1` | `1` / `0` | Returned empty list cleanly (`failed_requests=0`); cached properly so repeats don't spend quota. |
| 9 | **Cache hit (repeat query)** | `"ok_cached"` | `0` extra (`1` total) | `1` (`cache_hits=1`) | Returned cached response at `0` quota cost and `0` outbound HTTP calls. |
| 10 | **Quota exhaustion (`requests_used == limit`)** | `"quota_exhausted"` | `0` | `1` / `0` | Failed closed before HTTP socket call; `limit_reached=True`. |

**Production Integrity Verified After Diagnostic:**
- `data/database/fakenews.db` SHA-256: `35fc2f2cc41d6b100f1d2ad81844112d9ead2c286c95f95b45fcded9aee4e38f` (unchanged).
- `data/news_cache.db` `gdelt_usage_state`: `[200, 1, 0, 1, 'live_smoke_test', 'network_error']` (**`199` of `200` remaining, completely preserved**).

---

## 6. Potential Performance Bottlenecks & Concurrency Findings

1. **CRITICAL — Asyncio Event Loop Blocking in [`backend/app/api/routes/verify.py`](file:///D:/Documents/FakeNewsBlockChain/backend/app/api/routes/verify.py#L28-L51):**
   - Both `verify_text` (`line 28`) and `verify_article` (`line 48`) are defined as **`async def`**, but synchronously execute CPU-heavy DeBERTa inference *and* blocking `requests` HTTP calls (Wikipedia, Google Fact Check, GDELT).
   - A slow GDELT request (e.g. `8–17` seconds with retries) blocks the entire FastAPI asyncio event loop, stalling `/api/v1/health`, `/api/v1/news/gdelt-usage`, `/api/v1/history`, and concurrent requests until completion. *(Contrast with [`news.py`](file:///D:/Documents/FakeNewsBlockChain/backend/app/api/routes/news.py), which uses synchronous `def` routes so FastAPI dispatches them off the event loop via AnyIO worker threads.)*
2. **2x Quota Burn & Latency Amplification Under `GDELT_MAX_RETRIES = 1`:**
   - Retrying immediately on `ReadTimeout` (`~8s + 0.4s + ~8s`) or HTTP `429` (`~0.5s` backoff) doubles tail latency and burns **2** of the `200` shared GDELT slots per stalled query. For a `200`-request lifetime cap, retrying `429` or full timeouts is counter-productive.
3. **Heavy Default Lookback Window (`timespan="3months"`):**
   - `search_coverage` defaults to `"3months"` (`90` days) with `DateDesc` sorting on GDELT, whereas `"1month"` or `"2weeks"` covers current news much faster.
4. **Sequential Inline Execution in Verification:**
   - Currently `ExternalEvidenceAggregator.enrich_claims()` runs sequentially *after* Phase 1 (`FAISS + Wikipedia + DeBERTa`) and runs Google Fact Check and GDELT serially inside the HTTP handler.
5. **Minor SQLite DDL Repetition:**
   - `ensure_external_tables()` (`CREATE TABLE IF NOT EXISTS` / `INSERT OR IGNORE`) executes inside `BEGIN IMMEDIATE` on every `get_status()`, `reserve_request_slot()`, `record_request_outcome()`, and cache read/write. Initializing schema once per process (or on init) avoids repetitive catalog checks under concurrent load.

---

## 7. Recommended Configuration & Code Improvements (For Approval Only — Not Yet Implemented)

1. **Separate & Widen GDELT Connect/TLS vs. Read Timeouts:**
   - Add `GDELT_CONNECT_TIMEOUT_SEC` (recommended default **`8.0`**–`10.0`s so TLS handshakes are NOT artificially capped at `5.0`s by `min(5.0, timeout_sec)`) and increase `GDELT_TIMEOUT_SEC` (`read` timeout) default to **`12.0`**s (or **`10.0`**–`15.0`s), and pass `(connect_timeout, read_timeout)` explicitly in `gdelt_client.py` (and `google_factcheck_client.py`).
2. **Distinguish `ConnectTimeout` vs. `ReadTimeout`:**
   - Catch `requests.ConnectTimeout` separately from `requests.ReadTimeout` in [`gdelt_client.py`](file:///D:/Documents/FakeNewsBlockChain/backend/app/services/external_apis/gdelt_client.py#L321) so telemetry (`connect_timeout` vs `read_timeout`) clearly identifies TCP/TLS vs HTTP response stalls.
3. **Conserve the 200-Request Budget (`GDELT_MAX_RETRIES = 0` or Selective Retry):**
   - Set default `GDELT_MAX_RETRIES = 0` (recommended while hard cap = `200`) or restrict retries strictly to HTTP `502/503/504` only, never retrying `429` or `Timeout` when quota is precious.
4. **Narrow Default Verification `timespan` & Query Terms:**
   - Change `search_coverage` default `timespan` from `"3months"` to `"1month"` (configurable via `GDELT_TIMESPAN`), and refine [`build_focused_claim_queries`](file:///D:/Documents/FakeNewsBlockChain/backend/app/services/external_apis/evidence_aggregator.py#L59) to keep GDELT queries concise (`3–5` core entity/topic terms, excluding stray temporal noise words unless needed).
5. **Prevent Event-Loop Freezing in `verify.py`:**
   - Change `async def verify_text` and `async def verify_article` in [`verify.py`](file:///D:/Documents/FakeNewsBlockChain/backend/app/api/routes/verify.py#L28-L51) to synchronous `def` (matching [`news.py`](file:///D:/Documents/FakeNewsBlockChain/backend/app/api/routes/news.py)) or dispatch via `starlette.concurrency.run_in_threadpool`, plus enforce a clean external enrichment budget so `/api/v1/health` and other routes remain responsive.

---

## 8. Files That Would Need Modification

- [`backend/app/config.py`](file:///D:/Documents/FakeNewsBlockChain/backend/app/config.py) & [`.env.example`](file:///D:/Documents/FakeNewsBlockChain/.env.example) — Add `GDELT_CONNECT_TIMEOUT_SEC`, raise `GDELT_TIMEOUT_SEC`, set `GDELT_MAX_RETRIES=0`, optionally add `GDELT_DEFAULT_TIMESPAN`.
- [`backend/app/services/external_apis/gdelt_client.py`](file:///D:/Documents/FakeNewsBlockChain/backend/app/services/external_apis/gdelt_client.py) (and optionally [`google_factcheck_client.py`](file:///D:/Documents/FakeNewsBlockChain/backend/app/services/external_apis/google_factcheck_client.py)) — Remove hardcoded `min(5.0, ...)` clamp, separate `ConnectTimeout` vs `ReadTimeout`, refine retry policy & default timespan.
- [`backend/app/services/external_apis/evidence_aggregator.py`](file:///D:/Documents/FakeNewsBlockChain/backend/app/services/external_apis/evidence_aggregator.py) — Keep focused GDELT queries concise (`3–5` terms) when temporal/entity tokens over-constrain `ArtList`.
- [`backend/app/api/routes/verify.py`](file:///D:/Documents/FakeNewsBlockChain/backend/app/api/routes/verify.py) — Convert `verify_text` / `verify_article` from blocking `async def` to worker-threadpool `def` (or `run_in_threadpool`).
- [`backend/tests/test_external_apis.py`](file:///D:/Documents/FakeNewsBlockChain/backend/tests/test_external_apis.py) — Update/add mocked assertions for decoupled connect/read timeouts and `ConnectTimeout` vs `ReadTimeout` handling.

---

## 9. Expected Risks of Proposed Fixes

| Proposed Change | Expected Risk & Mitigation |
|---|---|
| Raising `connect` (`8–10s`) and `read` (`12–15s`) timeouts | Slightly longer worst-case `/verify/text` & `/verify/article` response latency (`+5s` to `+7s`) when GDELT is degraded. Mitigated by disabling `Timeout` retries (`GDELT_MAX_RETRIES=0`) so total worst-case GDELT wait drops from `~16.4s` (`2 x 8s`) down to `12s` once! |
| Setting `GDELT_MAX_RETRIES=0` on `Timeout`/`429` | Single transient HTTP 5xx or packet loss fails without an immediate retry. Mitigated because each retry costs 1 slot against the `200`-request hard cap; failing fast saves quota. |
| Shortening default `timespan` (`3months` -> `1month`) | Fewer older news articles returned when verifying 2–3-month-old events (Wikipedia & Google Fact Check still cover historical claims cleanly). |
| Changing `verify.py` `async def` -> `def` (threadpool) | Concurrent `/verify/*` requests can execute in parallel worker threads rather than serializing on the event loop, slightly increasing simultaneous RAM usage if multiple requests invoke DeBERTa NLI at the exact same moment. Mitigated by Python GIL/PyTorch `TORCH_NUM_THREADS=4` and low local concurrency, while eliminating total UI/health-check freezes. |

---

## Stop Notice

Read-only offline inspection and diagnostic tests are complete. **No source code, configuration, `.env`, models, databases, or blockchain state were modified**, and the shared GDELT allowance remains untouched at **`1 / 200` used (`199` remaining)**. Waiting for user approval before applying any changes.
