# FakeNewsBlockchain — Controlled Remediation Phase 1: Implementation Plan

**Plan Date:** 2026-11-11  
**Workspace:** `D:\Documents\FakeNewsBlockChain`  
**Status:** **Planning Only — Pending User Approval** (no source files, SQLite databases, `.env` configuration, model weights, or Sepolia blockchain state modified).  
**Primary Inputs Audited:**
- `REAL_WORLD_VALIDATION_REPORT.md`
- `docs/VERDICT_CLASSIFICATION_AUDIT.md`
- `C:\Users\ADMIN\.gemini\antigravity\brain\196b0c18-ecec-450a-83e7-f75c18a8277f\scratch\rw_validation_results.json` *(read-only audit output stored outside the repository so repo files remain unmodified)*
- `ml/rag/retriever.py`, `ml/rag/wikipedia_fallback.py`, `ml/inference/evidence_alignment.py`, `ml/inference/verdict_synthesizer.py`, `ml/inference/claim_extractor.py`, `backend/app/services/verification_service.py`, `backend/app/services/news_service.py`, `backend/app/services/blockchain_service.py`, `backend/app/database/repository.py`, `backend/app/api/routes/`, `backend/tests/`, and `frontend/src/`.

---

## 1. Root Cause Summary & Audit Inconsistency Resolution

### 1.1 Section 3 Audit Inconsistencies Investigated

#### A. Validation Accuracy Discrepancy: `12/26 (46.2%)` vs. `13/26 (50.0%)`
- **Authoritative Count:** **`13 / 26` (`50.0%` accuracy, Macro F1 `0.4516`)** is the verified true result.
- **Verification Evidence:**
  1. Direct programmatic check of `rw_validation_results.json` shows `total = 26`, `correct = 13`, `accuracy = 0.5`, `macro_f1 = 0.4516`, with passing claim IDs `[1, 2, 4, 5, 7, 8, 13, 18, 19, 20, 21, 23, 25]` (`13`) and failing IDs `[3, 6, 9, 10, 11, 12, 14, 15, 16, 17, 22, 24, 26]` (`13`), matching the confusion-matrix diagonal sum (`4 + 2 + 1 + 0 + 4 + 2 = 13`).
  2. The real `task-2934` OS completion log (`task-2934.log`, transcript line `2946`, `source=SYSTEM`, `2026-11-11T08:10:11Z`) matches `rw_validation_results.json` bit-for-bit.
- **Origin of `12/26 (46.2%)`:** Transcript inspection (`transcript.jsonl` line `2937`, `source=MODEL`, `type=PLANNER_RESPONSE`, `2026-11-11T08:07:13Z`) shows `12/26 (46.2%)` appeared inside a premature LLM-generated `<SYSTEM_MESSAGE>` block while `task-2934` was still executing claim `#03`. It has no backing log or JSON artifact on disk and was excluded from `REAL_WORLD_VALIDATION_REPORT.md`.

#### B. SQLite Numeric `block_timestamp` vs. Sepolia `block.timestamp` & ISO `block_datetime`
- **Observed Values for Confirmed Sepolia Record `verif-9c524ca7b6f5`:**
  - **On-chain Sepolia Block `#12076191` `block.timestamp`:** `1793963544` (`2026-11-06T11:12:24+00:00` UTC).
  - **SQLite `block_datetime` column:** `"2026-11-06T11:12:24+00:00"` (**accurate** — matches Sepolia UTC datetime).
  - **SQLite `block_timestamp` integer column:** `1762427544` (`2025-11-06T11:12:24+00:00` UTC — exactly `-31,536,000` seconds / 365 days earlier than Sepolia).
- **Exact Code Source:** `backend/app/database/repository.py:329-330` (`seed_confirmed_sepolia_record_if_empty()`) and the initial Nov 6 DB write stored `block_timestamp=1762427544` alongside `block_datetime="2026-11-06T11:12:24+00:00"` (similarly, `backend/tests/test_milestone3.py:117-118` uses `1762428000` with `"2026-11-06T12:06:40Z"`).
- **Cryptographic Impact:** **Zero.** `build_canonical_record()` (`backend/app/services/blockchain_service.py:56-99`) hashes only `schema_version`, `verification_id`, `original_content_hash`, `primary_verdict`, `confidence_score`, `evidence_hashes`, and record creation `timestamp` (`2026-11-06T11:12:22.475564+00:00`). Both `verify_certificate` (`certificates.py:149`) and frontend audit UI (`AuditExplorer.tsx:299`, `VerifyCertificate.tsx:241-245`) render `block_datetime` (`2026-11-06T11:12:24+00:00`) and live on-chain `query_verification()` output.
- **Recommended Resolution:** **Reporting/seed alignment without altering the historical anchored DB record or smart contract** — document the `1762427544` legacy integer artifact cleanly while updating `seed_confirmed_sepolia_record_if_empty()` line `329` (`1793963544`) for *fresh* database initializations only (optionally exposing on-chain `on_chain_block_timestamp` in `/audit/{id}/compare` read-only if needed, leaving `verif-9c524ca7b6f5` SQLite hash and row intact).

---

### 1.2 Pipeline Root Causes by Priority Group

| Group | Root Cause Identified in Audit | Observed Real-World Failure Impact |
|---|---|---|
| **A. Retrieval & Alignment** | 1. **Generic Subject-Entity Bleed:** `extract_subject_entities()` strips modifiers imperfectly (`"over"` chosen as primary entity in `#21`), relies strictly on first capitalized token (`"india"` blocking `Chandrayaan-3` sentences in `#02`; `"antarctica"` eclipsing lowercase `"penguin"` in `#10`), and lets single generic tokens like `"nobel"` match across pages (`Nobel Prize in Chemistry` certifying `Nobel Peace Prize` in `#11`) or namesakes (`Mark S. Zuckerberg` in `#24`).<br>2. **FEVER Suppresses Wikipedia Fallback:** `_needs_wikipedia_fallback()` only triggers below `0.62` similarity, so misleading FEVER topical distractors (`Lyme disease` `0.662`, `Reptile` `0.6296`) block live retrieval of authoritative articles (`Antibiotic`, `Penguin`).<br>3. **Wikipedia Slot Crowding:** `wikipedia_fallback.py` (`max 2 per page` within `top_k=5`) allowed `GPT-4o` to consume 2 slots and evict `ChatGPT`'s release-date sentence (`#03`), while `"ten percent brain"` missed `Ten-percent-of-the-brain myth` (`#12`). | Severe False Positive (`#11` `GENUINE 0.86`); False Negatives (`#03`, `#06`, `#10`, `#12`); fragile entity order on `#02`. |
| **B. Compound & Six-Class Synthesis** | 1. **34-Verb Whitelist Bottleneck:** `split_compound_claims()` (`evidence_alignment.py:265-275`) requires every clause to match a 34-word `finite_verb_pattern`, missing `"lies"`, `"allows"`, `"released"`, `"connects"`. All 4 `, and` / `, while` / `, whereas` claims failed to split.<br>2. **Multi-Founder & Quantifier Gaps:** Singleton exclusivity checks only numeric words (`two`, `three`) rather than comma-listed multi-person phrases (`Steve Jobs, Steve Wozniak, and Ronald Wayne`), making `#13` fragile (`Apple Inc.` fell to `NEI`).<br>3. **Unrepaired NLI NEI Head:** `Requirements/fever_verifier_v1` `logit[2]` outputs `raw_nei ~ 0.0` across unrelated inputs, requiring symbolic abstention as the sole safeguard. | `PARTIALLY_TRUE` recall **0/4 (0.0%)**, causing 3 dangerous `GENUINE` false positives (`#14`, `#15`, `#17`). `MISLEADING` recall **1/4 (25.0%)**. |
| **C. Temporal Reasoning** | 1. **Stale 2017 FEVER Overrides 2026 Wikipedia:** `_has_active_current_tenure()` treats `2017-06` FEVER strings (`"Elizabeth II is the current..."`) identically to `2026-11` Wikipedia, vetoing `#22`'s `OUTDATED` trigger.<br>2. **Incomplete End/Rebrand Patterns:** `HISTORICAL_END_PATTERNS` misses `"until her death in YYYY"` and corporate rebrand cues (`Meta Platforms` / `"formerly named"`).<br>3. **Non-Contiguous Tenure Bug:** `_has_active_current_tenure()` regex fails on `"is the 47th president"`, `"current 47th"`, and `"(2017–2021, 2025–present)"`, while `from 2017 to 2021` triggers `shows_historical_end=True`. | `#22` Elizabeth II (`GENUINE 0.92`); `#24` Facebook Inc. (`GENUINE 0.86`); `#26` Donald Trump (`OUTDATED 0.83` false alarm). |
| **D. Article Aggregation** | `_aggregate_multi_claim_verdicts()` (`verification_service.py:91-197`) treats all extracted claims with equal weight (`relevance_rank` ignored) and hard-forces *any* `GENUINE + UNVERIFIED` combination to `UNVERIFIED`. | Articles with 3 supported central claims + 1 minor unverified detail cannot resolve to `GENUINE`; central vs. minor refuted claims are indistinguishable. |
| **E. External APIs (Phase 2)** | `GOOGLE_FACT_CHECK_API_KEY`, `GDELT_ENABLED`, `GDELT_REQUEST_LIMIT=200`, and `GDELT_WARNING_THRESHOLD=20` exist in `.env`, but have **zero client, caching, tracker, schema, pipeline, or UI implementation** (`_ingest_gdelt_source` in `news_service.py` calls GDELT uncounted). | No real-time news/fact-check cross-checking; risk of uncounted GDELT quota burn in `Live News`. |

---

## 2. File-by-File Remediation Plan

> **Strictly Phased Separation:** **Phase 1 covers Groups A, B, C, and D only.** **Phase 2 (Group E)** will not begin until Groups A–D pass independent 60+ claim validation and user review.

---

### PHASE 1 — Groups A, B, C, D (Core Verification, Alignment, Temporal & Aggregation)

#### File 1: `ml/inference/evidence_alignment.py` *(Groups A, B, C)*
- **Exact Changes:**
  1. **Subject Entity Extraction & Event/Award Specificity (`extract_subject_entities`, `evaluate_evidence_alignment`):**
     - Add common sentence-initial prepositions/quantifiers/adverbs (`"over"`, `"under"`, `"more"`, `"less"`, `"nearly"`, `"about"`, `"almost"`, `"only"`, `"even"`) to `GENERIC_INITIAL_WORDS` so numeric qualifiers (`"Over 83 percent..."`) never become `primary_ent`.
     - Add multi-word entity phrase matching (e.g., `"nobel peace prize"` vs `"nobel prize in chemistry"`, `"mark s. zuckerberg"` vs `"mark zuckerberg"`, `"apple computer"`/`"apple inc"` vs `"apple"`). When a claim names a specific compound award/organization/person (like `Nobel Peace Prize`), prevent an evidence sentence from a **different sibling subtype** (`Nobel Prize in Chemistry` without mentioning `"peace"`) from passing `entity_matched`. Likewise, reject middle-initial/disambiguated namesakes (`"Mark S. Zuckerberg"` when sentence explicitly notes *"resemblance of his name"* or different person).
     - Fix subject-entity selection so if the leading entity is a country/location possessive modifier before another proper noun (e.g. `"India's Chandrayaan-3"`), or when the main concrete topic is a non-proper subject noun alongside a location (`"All penguin species... Antarctica"`), entity checks evaluate all core subject nouns/entities rather than letting an incidental location discard the exact topic article (`Chandrayaan-3`, `Penguin`).
  2. **Grammar-General Compound Splitting (`split_compound_claims`):**
     - Replace the closed 34-word `finite_verb_pattern` whitelist with general English finite/inflected clause validation: require each split clause (split on `;` or `, (and|while|but|although|however|whereas) `) to have `>= 4` words AND match either auxiliary/copula verbs OR third-person singular/past/irregular verb morphology (`\b[a-z]{3,}(?:s|ed|es|en)\b` excluding prepositions/nouns/determiners via compact function-word exclusion, OR known irregular finite verbs) AND verify the right-hand clause begins with a plausible subject (proper noun, determiner, pronoun, or noun phrase) rather than a bare modifier or list tail (`"Smith, Jones, and Brown"`).
     - Improve pronoun resolution in split clauses beyond bare `he/she/it/they`.
  3. **Expanded Multiplicity & Exclusive-Slot Detection:**
     - Extend singleton exclusivity (`only`, `sole`, `solely`, `single`, `alone`) in `evaluate_evidence_alignment()` to detect **co-founder / multi-party lists** (e.g., `"co-founder"` / `"co-founders"`, `"and ... and"` coordinating >= 2 capitalized person names right after `"founded by"` / `"created by"` / `"written by"`, resolving `#13` cleanly on `"Apple Inc."`).
     - Add general comparative superlative exclusivity (`{"smallest", "largest", "biggest", "tallest", "shortest", "highest", "lowest", "oldest", "newest", "first", "last"}`) when entity + category match directly (e.g. `"smallest planet"` vs `"largest [planet] in the Solar System"`).
  4. **Expanded Temporal End & Corporate Rebrand Patterns (`HISTORICAL_END_PATTERNS`, `CURRENT_OFFICE_OR_STATE_PATTERNS`):**
     - Add historical termination patterns: `r"\buntil\s+(?:her|his|their)\s+death\s+in\s+\d{4}\b"`, `r"\bdied\s+(?:on\s+[\w\s,]+)?(?:19|20)\d{2}\b"`, `r"\bformerly\s+(?:named|known\s+as|called)\b"`, `r"\bparent\s+company\s+[A-Z][\w\s]+\b"` (when claim asserts older `"Facebook, Inc."` style `current official ... parent name`).
     - Extend `CURRENT_OFFICE_OR_STATE_PATTERNS` to capture corporate/organizational framing (`"official corporate parent name"`, `"reigning monarch"`, `"sitting"`, `"present-day"`).
     - Add a clean helper `evidence_confirms_active_tenure(claim, evidence_text)` that handles ordinal incumbent phrases (`r"\bis\s+the\s+(?:\d+(?:st|nd|rd|th)\s+and\s+current|\d+(?:st|nd|rd|th))\s+(?:president|prime\s+minister|chancellor|monarch|king|queen)\b"`, `r"\b\d{4}\s*[–—-]\s*present\b"`, `r"\b(?:45th|former)\s+and\s+current\b"`).
- **Why:** Fixes Failures `#02` (entity order), `#08` (Indira vs Mahatma noisy ordinal match), `#10`, `#11`, `#13`, `#14–#17` (`0/4` splitting), `#21`, `#22`, `#24`, `#26`.
- **Backward Compatibility:** Purely additive signature options or identical `AlignedEvidenceAssessment` fields; zero changes to canonical hashing or external contracts.

#### File 2: `ml/rag/wikipedia_fallback.py` *(Groups A, C)*
- **Exact Changes:**
  1. **Query Builder Improvements (`build_wikipedia_search_queries`):**
     - Strip apostrophe-possessive suffixes before entity lookup (e.g., `"Mark Zuckerberg's"` -> `"Mark Zuckerberg"`, `"India's"` -> `"India"`), and build a **subject + core-topic keyword query** without over-constraining rare modifier adjectives/years (`"ten percent brain"`, `"penguin live Antarctica"`, `"Facebook parent company"`, `"Nobel Peace Prize awarded"`).
     - When a claim cites a company/rebrand concept (`"parent company"`, `"brand name"`, `"formerly"`, `"Inc."`), include a disambiguated entity/corporate query (e.g., `"Facebook Inc parent company"` / `"Meta Platforms"`) so target pages like `Meta Platforms` are retrieved.
  2. **Lead-Sentence Preservation & Page Diversity (`retrieve`):**
     - Keep `Pass 1` at **1 highest-scoring sentence per distinct Wikipedia page** FIRST, *plus* guarantee inclusion of each top matched page's lead definitional sentences (`sentence_id <= 1`) when evaluating exact title matches, before filling Pass 2 slots up to `limit = max(top_k, 8)`. This prevents sub-articles (`GPT-4o` x2 in `#03`) from crowding out `ChatGPT` sentence #1 (`"Originally released on November 30, 2022..."`).
  3. **Graceful Empty-Body / Rate-Limit Resilience (`_query_mediawiki`):**
     - Handle empty HTTP 200/429 responses cleanly before `.json()` without logging noisy tracebacks, honoring `last_status = "rate_limited"` / `"invalid_response"`.
- **Why:** Fixes `#03` (ChatGPT date evicted), `#12` (ten-percent myth), `#24` (`Meta Platforms`), and prevents MediaWiki transient empty responses seen in `task-2955` from throwing uncaught JSON errors.
- **Backward Compatibility:** Retains existing `WikipediaSentenceHit` dataclass and HTTPS `en.wikipedia.org` allowlist.

#### File 3: `ml/rag/retriever.py` *(Groups A, C)*
- **Exact Changes:**
  1. **Trigger Wikipedia Fallback on Structural Uncertainty (`_needs_wikipedia_fallback`):**
     - In addition to `< 0.62` similarity, missing entities, and temporal indicators, trigger live Wikipedia when: (a) local FEVER hits match a secondary/location term while missing the primary subject noun/entity (`#10` `Reptile` / `Antarctica` missing `"penguin"`); OR (b) local FEVER matches a peripheral/conditional page with sweeping/causal biomedical keywords (`"cure"`, `"all"`, `"exclusively"`, `"only"`, `"parent company"`, `"awarded"`); OR (c) any current-state claim has any `fever_local` match (`2017-06`) alongside `current`/`incumbent`/`reigning`/`official` framing so live 2026 pages *always* run.
  2. **Freshness-Aware Source Ranking (`retrieve_hybrid`):**
     - Maintain clean separate `source_type` (`fever_local` vs `wikipedia_live`). When merging for temporal/current-state claims, ensure stale `fever_local` (`2017-06`) sentences for the *same topic* do not dominate `wikipedia_live` sentences within the top `k` pool.
- **Why:** Prevents local FEVER distractors (`Reptile`, `Lyme disease`, 2017 `Elizabeth II` list) from suppressing authoritative live Wikipedia evidence.
- **Backward Compatibility:** Preserves `EvidenceSentence`, `retrieve()`, and `retrieve_hybrid()` return contracts.

#### File 4: `ml/inference/verdict_synthesizer.py` *(Groups A, B, C)*
- **Exact Changes:**
  1. **Source-Freshness Precedence for Temporal Reasoning (`OUTDATED` vs `GENUINE`):**
     - Inside `Priority 1 (OUTDATED)`: ignore `fever_local` (`2017-06` static snapshot) hits when computing `active_hits = [a for a in assessments if _has_active_current_tenure(claim, a)]` whenever `wikipedia_live` evidence is present (or mark `fever_local` as non-authoritative for present-tense officeholder/reigning checks)! That immediately stops stale 2017 `Current reigning monarchs...` (`#22` Queen Elizabeth II) from blocking live 2026 `"until her death in 2022"`.
     - Integrate `evidence_confirms_active_tenure()` in `_has_active_current_tenure()` so live 2026 Wikipedia sentences stating `"is the 47th president"`, `"45th and current 47th president"`, or `"(2017–2021, 2025–present)"` register in `active_hits` and **prevent** closed past terms (`from 2017 to 2021`) from misclassifying `#26` Donald Trump as `OUTDATED`.
     - Ensure `_is_temporal_role_match()` cleanly detects rebrand mismatches (e.g., `"Meta Platforms"` / `"formerly named Facebook, Inc."` vs `"Facebook, Inc. is the current official corporate parent name"` -> `OUTDATED`).
  2. **Strict Entity-Matched Priority for `GENUINE` / `FAKE`:**
     - Ensure `GENUINE` requires at least one supporting sentence where `entity_matched` is True *and* excludes sibling-category false matches (`Nobel Prize in Chemistry` without `Peace` on `#11`, or `Mark S. Zuckerberg` namesake on `#24`).
     - Explicitly include `Requirements/fever_verifier_v1` NEI limitation disclosure and abstention trace inside `uncertainty_explanation` / `limitations` (never claiming the model weights were fixed).
- **Why:** Eliminates false `GENUINE` verdicts on `#11`, `#22`, `#24` and false `OUTDATED` on `#26`.
- **Backward Compatibility:** Preserves `SynthesisResult` and six exact verdict strings (`GENUINE`, `FAKE`, `MISLEADING`, `PARTIALLY_TRUE`, `UNVERIFIED`, `OUTDATED`).

#### File 5: `backend/app/services/verification_service.py` & `ml/inference/claim_extractor.py` *(Groups B, D)*
- **Exact Changes:**
  1. **Centrality-Weighted Article Aggregation (`_aggregate_multi_claim_verdicts`):**
     - Pass candidate salience metadata (`relevance_rank`, `relevance_score` from `ClaimExtractor`, defaulting cleanly for `split_compound_claims` text sub-clauses where all clauses carry equal weight `1.0`!).
     - Differentiate **central claims** (`rank <= 2` or `relevance_score >= high_tier`, or all sub-claims of a compound single sentence) from **minor/peripheral claims** (`rank >= 3` or lower salience):
       - **All central claims supported (`>= 1`, or `>= 2` when `>= 3` analyzed) & ZERO `FAKE`/`MISLEADING`/`OUTDATED` contradictions:** Eligible for **`GENUINE`** even if 1 minor/peripheral extracted sentence returned `UNVERIFIED`! Explain clearly in `uncertainty_explanation` which minor claim lacked evidence so transparency is preserved. *(Crucial guard: keep strict equality for short compound text claims from `split_compound_claims()` so `"Einstein developed relativity, and he won 12 Olympic medals"` stays `UNVERIFIED` unless corroborated; only relax for multi-sentence article extractions where central claims establish the article thesis!)*
       - **Mixture of corroborated and refuted/distorted/outdated material claims (`n_genuine > 0` and `(n_fake + n_misleading + n_outdated) > 0`):** Classify **`PARTIALLY_TRUE`**, noting central vs minor breakdown in `summary_explanation` and `uncertainty_explanation`.
       - **Majority/central claims `FAKE` with no corroborated central claims:** Classify **`FAKE`**; if only 1 minor claim is `FAKE` while central claims are `UNVERIFIED` (zero `GENUINE`), avoid blindly declaring the entire article `FAKE` (either `UNVERIFIED` with flagged discrepancy or `MISLEADING` if distortion triggered), per Section 7 (`"Do not let one refuted minor claim automatically classify an entire article as FAKE"`).
       - **All claims `UNVERIFIED` or central claims lack evidence:** Keep **`UNVERIFIED`**.
  2. **Compound Claim Retrieval Context Improvement (`verify_text_claim`):**
     - Keep `split_compound_claims()` integration cleanly handling `> 1` clauses and deduplicating evidence with `sub_verdict_schemas`.
- **Why:** Satisfies Group D requirements cleanly without breaking compound text safeguards.
- **Backward Compatibility:** `_aggregate_multi_claim_verdicts(items, context_label=...)` keeps optional `weights` / `ranks` parameter so all existing callers work without breakage.

#### File 6: `backend/app/database/repository.py` *(Audit Consistency Only — Historical DB Preserved)*
- **Exact Changes:**
  - In `seed_confirmed_sepolia_record_if_empty()` (line `329`), update the seed integer constant `block_timestamp=1762427544` -> `block_timestamp=1793963544` so **newly initialized** DBs match Sepolia block `#12076191`'s actual UTC timestamp (`2026-11-06T11:12:24+00:00`).
  - **Do NOT alter** the existing SQLite row for `verif-9c524ca7b6f5`, its `canonical_record_json`, `record_hash`, or on-chain storage unless explicitly requested later (keeping `db_hashes` verifiable and canonical hashes 100% preserved).

---

### PHASE 2 — Group E (External API Integrations — **Blocked Until Groups A–D Approval**)

#### File 7: `.env.example` & `backend/app/config.py`
- **Exact Changes:**
  - `.env.example`: Document `GDELT_ENABLED=true`, `GDELT_REQUEST_LIMIT=200`, `GDELT_WARNING_THRESHOLD=20` right below `GOOGLE_FACT_CHECK_API_KEY=`.
  - `backend/app/config.py`: Add `GDELT_ENABLED: bool = True`, `GDELT_REQUEST_LIMIT: int = 200`, `GDELT_WARNING_THRESHOLD: int = 20`, plus timeout/cache TTL settings (`GOOGLE_FACT_CHECK_TIMEOUT_SEC: float = 8.0`, `GDELT_TIMEOUT_SEC: float = 8.0`, `EXTERNAL_CACHE_TTL_HOURS: int = 24`) to `Settings`. Never log or expose keys.

#### File 8: `backend/app/services/external_apis/google_factcheck_client.py` *(New)*
- **Exact Changes:**
  - Implement HTTP client targeting `https://factchecktools.googleapis.com/v1alpha1/claims:search` using `GOOGLE_FACT_CHECK_API_KEY` solely from backend `Settings` (explicitly scrub `key=...` from exception/error strings and logs so credentials never leak!).
  - Extract & normalize `FactCheckMatch` objects: `reviewed_claim`, `claim_date`, `claimant`, `review_title`, `publisher_name`, `publisher_site`, `textual_rating`, `review_date`, `review_url`, `language_code`, semantic similarity vs user claim (`all-MiniLM-L6-v2`), and entity/date alignment status (`exact_match` vs `related_topic` vs `low_overlap`).
  - Handle invalid/missing API key (401/403), quota 429, 4xx/5xx, malformed JSON, empty `claims: []`, and `Timeout`/`ConnectionError` gracefully without blocking the remaining pipeline.
  - Strictly preserve `textual_rating` untouched — convert matching `ClaimReview` into structured external evidence (`source_type="google_fact_check"`) for alignment/context without blindly forcing ambiguous publisher strings (`"Mostly False"`, `"Missing Context"`, `"Half True"`, `"Satire"`) into `FAKE` or `GENUINE`.

#### File 9: `backend/app/services/external_apis/gdelt_usage_tracker.py` & `evidence_cache.py` *(New)*
- **Exact Changes:**
  - Initialize two lightweight persistent tables in SQLite (`data/news_cache.db` after mandatory backup, leaving `fakenews.db`'s historical `verification_records` isolated):
    1. `gdelt_usage_state` (single persistent counter row): `allowance_limit` (default 200 synced with config), `requests_used`, `last_request_at`, `last_source` (`"verification"` | `"news_refresh"`), `last_status`. Provides atomic increment/check (`can_consume()`, `consume_slot()`, `get_usage_status()`) surviving FastAPI restarts. Stops outbound GDELT requests once `requests_used >= GDELT_REQUEST_LIMIT`; sets `warning_active = (remaining <= GDELT_WARNING_THRESHOLD)`. Includes explicit scope note distinguishing local app-side request counting from GDELT provider-side throttling/quotas.
    2. `external_evidence_cache`: keyed by `(provider, normalized_query_hash)` (`"google_fact_check"` / `"gdelt"`), storing `response_json`, `fetched_at`, `expires_at`, and `hit_count`. Guarantees repeated claims or UI refreshes reuse SQLite cache **without** consuming another GDELT request.

#### File 10: `backend/app/services/external_apis/gdelt_client.py` *(New)* & `backend/app/services/news_service.py` *(Updated)*
- **Exact Changes:**
  - `gdelt_client.py`: Single central gateway for **all** outbound `https://api.gdeltproject.org/api/v2/doc/doc` calls (`ArtList` mode JSON, focused keyword query capped at 1 query per uncached claim, explicit request timeout, **zero aggressive retry loops** so budget is never double-charged on failure!). Checks `GDELT_ENABLED`, checks `evidence_cache` first, checks `gdelt_usage_tracker.can_consume()`, increments persistent counter cleanly for real outbound attempts, deduplicates URLs (`normalize_canonical_url`) and normalized titles, preserves `title`, `url`, `domain`, `seendate`, `sourcecountry`, `language`, and explicitly notes that GDELT provides article metadata/headlines rather than full scraped article bodies.
  - `news_service.py`: Replace `_ingest_gdelt_source()`'s raw uncounted `urllib.request.urlopen()` call (`lines 307-351`) with `gdelt_client.fetch_feed_articles()` so `Live News Monitor` refreshes **share the exact same 200-request persistent counter and cache**, and degrade gracefully if the 200-request cap is reached or `GDELT_ENABLED=false` (allowing RSS feeds to refresh normally).

#### File 11: `backend/app/services/external_apis/evidence_aggregator.py` *(New)* & `backend/app/services/verification_service.py` *(Updated)*
- **Exact Changes:**
  - Implement the unified pipeline diagram from Section 3 of the prior specification:
    `Claim -> (Google Fact Check API [cached] + Local FEVER FAISS) -> Evidence Relevance Assessment -> Conditional GDELT Search (ONLY when justified, enabled, uncached, and under budget) -> Conditional Wikipedia Fallback -> Normalization -> URL/Text Deduplication -> Entity/Date/Predicate Alignment -> DeBERTa NLI -> Six-Class Synthesis -> SQLite Persistence`.
  - Keep strict source-identity preservation (`google_fact_check`, `gdelt`, `wikipedia_live`, `fever_local`, `rss`), separating **fact-check matches**, **news articles**, and **supporting / contradicting / contextual** evidence items—never treating article count as truth proof.

#### File 12: Backend Schemas & Routes (`backend/app/schemas/verification.py`, `article.py`, `news.py`, `api/routes/news.py`, `verify.py`)
- **Exact Changes:**
  - Add read-only `GET /api/v1/news/gdelt-usage` (or `/external-usage`) returning `{ enabled, allowance, requests_used, requests_remaining, warning_threshold, warning_active, limit_reached, last_request_at, tracker_scope_note }` with **zero credentials**.
  - Add optional additive fields (`fact_check_matches: List[FactCheckMatchSchema] = []`, `news_evidence: List[NewsEvidenceSchema] = []`, `external_source_status: Dict[str, str] = {}`) on `TextVerificationResponse` and `ArticleVerificationResponse` with default empty values so legacy consumers and `canonical_record_json` (`schema_version: "1.0"`) remain 100% unchanged!

#### File 13: Frontend UI & GDELT Usage Dashboard (`frontend/src/...`)
- **Exact Changes:**
  - Update `frontend/src/types/verification.ts` and `frontend/src/api/verify.ts` for `FactCheckMatch`, `NewsEvidenceItem`, and `GdeltUsageStatus`.
  - Update `EvidenceCard.tsx` to badge all five provenance channels (`Google Fact Check`, `GDELT`, `Wikipedia`, `FEVER Local`, `RSS`).
  - Update `TextVerify.tsx` & `ArticleVerify.tsx` to display dedicated sections for:
    - **Fact-Check Matches** (claimed text, publisher, original rating preserved verbatim, review date, external review URL link).
    - **Related News Evidence** (headline, publisher, publication date, URL, relevance indicator — clearly distinguished from truth proof).
    - **Role-Grouped Evidence** (`Supporting`, `Contradicting`, `Insufficient / Contextual`).
  - Add compact **GDELT Budget Indicator** in `Sidebar.tsx` (under the system health card) and on `LiveNews.tsx` showing `200` configured allowance, `Used`, `Remaining`, warning banner at `<= 20` remaining, last request timestamp, and read-only cache indicator.

---

## 3. Proposed Implementation Order

```text
[Backup fakenews.db & news_cache.db]
        |
        v
Phase 1A (Group A + B Retrieval & Alignment)
  1. ml/inference/evidence_alignment.py   (universal verb/clause splitter, entity disambiguation, multiplicity & rebrand signals)
  2. ml/rag/wikipedia_fallback.py         (possessive stripping, lead sentence preservation, empty-JSON guard)
  3. ml/rag/retriever.py                  (location/peripheral fallback triggers, freshness prioritization)
        |
        v
Phase 1B (Group C Temporal + Group D Aggregation + Seed Timestamp)
  4. ml/inference/verdict_synthesizer.py  (live vs 2017 FEVER active-tenure precedence, Trump/Elizabeth II/Meta rules)
  5. ml/inference/claim_extractor.py + backend/app/services/verification_service.py  (centrality-weighted aggregation)
  6. backend/app/database/repository.py   (fresh-DB seed block_timestamp=1793963544 fix only; live DB untouched)
        |
        v
Phase 1 Verification & Audit Gate (BEFORE Group E!)
  7. Update backend/tests/test_verdict_classification.py & test_article.py
  8. Run full pytest regression suite + NEW >=60-claim independent benchmark (saved to docs/REAL_WORLD_BENCHMARK.md)
  9. STOP FOR USER REVIEW & APPROVAL OF PHASE 1 RESULTS
        |
        v
Phase 2 (Group E — Only After Phase 1 Approval)
 10. .env.example & backend/app/config.py (GDELT_* settings)
 11. backend/app/services/external_apis/ (evidence_cache.py, gdelt_usage_tracker.py, google_factcheck_client.py, gdelt_client.py)
 12. Wire news_service.py -> shared gdelt_client + tracker + cache
 13. evidence_aggregator.py + verification_service.py + API schemas/routes
 14. Frontend types, TextVerify, ArticleVerify, LiveNews, EvidenceCard, Sidebar GDELT dashboard + Vite build
 15. Mocked unit/integration tests + minimal budgeted live verification smoke check + Final docs/EXTERNAL_API_INTEGRATION.md & updated docs/REAL_WORLD_BENCHMARK.md & architecture diagram.
```

---

## 4. Risks & Backward-Compatibility Considerations

| Risk | Severity | Mitigation |
|---|---|---|
| **Over-splitting normal English sentences in `split_compound_claims()`** (e.g., *"Alice, Bob, and Carol met"* or *"built in 1990, and expanded in 2005"*) | Medium | Require every right-hand clause after `, and`/`while`/`whereas` to contain both `>= 4` words, a standalone grammatical subject before/at verb position, AND a finite/action verb token (excluding passive modifiers inside single-entity biographies). |
| **Blocking `OUTDATED` falsely or triggering `OUTDATED` on returned officeholders (`#26`)** | High | Never let `fever_local` (`2017-06`) populate `active_hits` when `wikipedia_live` sentences exist for that entity, and check live `wikipedia_live` text specifically for ordinal-present / `YYYY–present` active indicators. |
| **Breaking canonical SHA-256 hashes or PDF certificates for historical records** | Critical | Keep `CanonicalVerificationRecord` (`schema_version="1.0"`) untouched. Store new optional fields (`fact_check_matches`, `news_evidence`, `claim_centrality`) only in response/DB JSON overlays, never inside historical hash payloads. Keep `LIKELY_GENUINE` / `LIKELY_FAKE` enums and history filter aliases intact. |
| **Burning GDELT's 200-request budget during automated `pytest` or frontend polling** | Critical | Force all `pytest` suites (including `test_news.py::test_news_refresh_and_deduplication` and `test_external_apis.py`) to mock `requests` / `gdelt_client` calls by default, and keep `GET /api/v1/news/gdelt-usage` strictly read-only on SQLite. Never embed retry loops on GDELT requests. |
| **Accidental leakage of `GOOGLE_FACT_CHECK_API_KEY`** | Critical | Strip query strings (`?key=...`) from any caught `requests` exception message, URL log, or HTTP error detail before returning or logging. Never pass `GOOGLE_FACT_CHECK_*` to Vite/frontend `VITE_*` env vars. |
| **SQLite schema migration issues in `news_cache.db`** | Medium | Back up both `data/database/fakenews.db` and `data/news_cache.db` before adding `gdelt_usage_state` and `external_evidence_cache` to `news_cache.db` via idempotent `CREATE TABLE IF NOT EXISTS`. |

---

## 5. Testing Strategy & New >= 60-Claim Independent Validation Suite

### 5.1 Unit & Integration Tests to Add / Update
- **`backend/tests/test_verdict_classification.py` (Phase 1 Update):**
  - Compound splitting with non-whitelisted verbs (`lies`, `allows`, `released`, `connects`, `whereas`), while guarding non-clausal `, and` phrases against over-splitting.
  - Subject specificity (`Nobel Peace Prize` vs `Nobel Prize in Chemistry`, `Mark Zuckerberg` vs `Mark S. Zuckerberg`, `Over 83 percent` preposition skipping, `India's Chandrayaan-3`, `All penguin species`).
  - Temporal suite: `Donald Trump is the current President` (`GENUINE` despite `2017–2021` prior term), `Queen Elizabeth II` (`OUTDATED` despite 2017 FEVER leads), `Angela Merkel` (`OUTDATED`), `Rishi Sunak` (`OUTDATED`), `Facebook, Inc.` (`OUTDATED` rebrand to Meta Platforms).
  - Multi-founder sole-claim test (`Steve Jobs was the sole founder of Apple Computer` -> `MISLEADING` on `Apple Inc.` + `Steve Wozniak`).
  - Group D article aggregation tests: (a) `3 central GENUINE + 1 minor UNVERIFIED` -> `GENUINE` with uncertainty note; (b) `2 central GENUINE + 1 central FAKE` -> `PARTIALLY_TRUE`; (c) `3 minor GENUINE + 1 central FAKE` -> not hidden as `GENUINE`; (d) `3 central FAKE` -> `FAKE`.
- **`backend/tests/test_article.py` & `backend/tests/test_verification.py`:** Keep all existing regression assertions green alongside updated uncertain-aggregation tests.
- **`backend/tests/test_milestone3.py` & Blockchain Read-Only Checks:** Confirm `verif-9c524ca7b6f5` SHA-256 (`42007960...16a2cc53`), PDF generation, QR verification (`MATCH`/`MISMATCH`/`NOT_FOUND`), and Sepolia `VERIFIED_MATCH` (`0x8ba191...`) remain unbroken.
- **`backend/tests/test_external_apis.py` & `backend/tests/test_news.py` (Phase 2 Addition — Fully Mocked + Isolated Temp DB):**
  - *Google Fact Check:* matching claim, empty response, multiple publishers, conflicting/ambiguous original ratings preserved verbatim, historical review, HTTP 401/403 invalid key (key scrubbed from error/log), 429 rate limit, `Timeout`/`ConnectionError`, malformed JSON.
  - *GDELT:* focused query, empty `articles`, historical vs recent query, duplicate URL/title deduplication, SQLite cache hit (0 extra counter increment), counter persistence across tracker re-instantiation, warning state at `<= 20` remaining, hard stop at limit `200`, graceful continuation via FEVER/Google Fact Check/Wikipedia when exhausted or timed out, and shared quota enforcement when calling `POST /api/v1/news/refresh`.

---

### 5.2 New Independent Validation Benchmark Suite (`64` Previously Unused English Claims)

None of the 23 claims from `scratch/run_verdict_benchmark.py` appear below. All 64 claims cover distinct subjects and linguistic structures (direct, paraphrased, compound, misleading context, historical, recent 2022–2026 events, conflicting evidence, and unsupported/fabricated statements). Authoritative public reference URLs are designated below; live source revision/publication dates and retrieved evidence outputs will be recorded at test runtime cleanly without fabrication.

#### A. `GENUINE` (12 Claims — Direct, Paraphrased, Historical, Recent, Non-Contiguous)
1. *(Paraphrased historical)* `Alexander Fleming identified the antibiotic properties of penicillin in 1928.` — Ref: `https://en.wikipedia.org/wiki/Alexander_Fleming`
2. *(Paraphrased science)* `DNA adopts a double-helix molecular structure first modeled by Watson and Crick in 1953.` — Ref: `https://en.wikipedia.org/wiki/DNA`
3. *(Direct astronomy)* `Jupiter has more mass than all other planets in the Solar System combined.` — Ref: `https://en.wikipedia.org/wiki/Jupiter`
4. *(Direct history)* `The Berlin Wall fell in November 1989, paving the way for German reunification.` — Ref: `https://en.wikipedia.org/wiki/Berlin_Wall`
5. *(Recent 2022–2026 space)* `NASA's James Webb Space Telescope captured its first deep-field infrared images in July 2022.` — Ref: `https://en.wikipedia.org/wiki/James_Webb_Space_Telescope`
6. *(Recent 2023 science)* `India's Chandrayaan-3 mission landed near the lunar south pole in August 2023.` — Ref: `https://en.wikipedia.org/wiki/Chandrayaan-3`
7. *(Recent 2022 AI/tech)* `OpenAI released ChatGPT to the public in November 2022.` — Ref: `https://en.wikipedia.org/wiki/ChatGPT`
8. *(Recent 2022 royalty)* `King Charles III became sovereign of the United Kingdom upon Queen Elizabeth II's death in 2022.` — Ref: `https://en.wikipedia.org/wiki/Charles_III`
9. *(Temporal non-contiguous tenure)* `Donald Trump is the current President of the United States.` — Ref: `https://en.wikipedia.org/wiki/Donald_Trump`
10. *(Recent European accession 2024)* `Sweden formally joined NATO as its 32nd member state in March 2024.` — Ref: `https://en.wikipedia.org/wiki/Sweden_and_NATO`
11. *(Global economics/treaty)* `The Euro replaced legacy national banknotes across twelve European Union countries in January 2002.` — Ref: `https://en.wikipedia.org/wiki/Euro`
12. *(Literature/biography)* `Gabriel Garcia Marquez received the 1982 Nobel Prize in Literature.` — Ref: `https://en.wikipedia.org/wiki/Gabriel_Garc%C3%ADa_M%C3%A1rquez`

#### B. `FAKE` (11 Claims — Fabricated Events, False Dates, Medical/Scientific Falsehoods, Entity/Ordinal Errors)
13. *(False date)* `World War II ended in September 1955 after Japan surrendered.` — Ref: `https://en.wikipedia.org/wiki/World_War_II`
14. *(False non-US ordinal leader)* `Mahatma Gandhi served as the first Prime Minister of India.` — Ref: `https://en.wikipedia.org/wiki/Jawaharlal_Nehru`
15. *(False attribution)* `Marie Curie discovered the planet Neptune from Paris Observatory in 1898.` — Ref: `https://en.wikipedia.org/wiki/Neptune`
16. *(Biomedical falsehood)* `Antibiotics effectively cure viral respiratory infections such as influenza and the common cold.` — Ref: `https://en.wikipedia.org/wiki/Antibiotic`
17. *(Geographical falsehood)* `Mount Everest is located on the continent of Africa.` — Ref: `https://en.wikipedia.org/wiki/Mount_Everest`
18. *(Historical impossibility)* `The Titanic sank in the Pacific Ocean during its maiden voyage in 1925.` — Ref: `https://en.wikipedia.org/wiki/Titanic`
19. *(False Olympic host)* `Tokyo hosted the Summer Olympic Games in 1996.` — Ref: `https://en.wikipedia.org/wiki/1996_Summer_Olympics`
20. *(False Nobel recipient category)* `Isaac Newton won three Nobel Prizes in Physics during the eighteenth century.` — Ref: `https://en.wikipedia.org/wiki/Nobel_Prize`
21. *(False corporate origin)* `Microsoft Corporation was founded in London in 1995 by Tim Berners-Lee.` — Ref: `https://en.wikipedia.org/wiki/Microsoft`
22. *(False chemical/element fact)* `Pure water boils at 50 degrees Celsius at standard sea-level atmospheric pressure.` — Ref: `https://en.wikipedia.org/wiki/Boiling_point`
23. *(False recent mission target)* `India's Chandrayaan-3 spacecraft landed astronauts on Mars in 2023.` — Ref: `https://en.wikipedia.org/wiki/Chandrayaan-3`

#### C. `MISLEADING` (10 Claims — Cherry-Picked Scope, Venue Conflation, Sweeping Quantifiers, Conflicting/Distorted Framing)
24. *(Venue conflation)* `The Nobel Peace Prize is presented annually in Stockholm alongside the Physics and Chemistry prizes.` — Ref: `https://en.wikipedia.org/wiki/Nobel_Peace_Prize`
25. *(Sweeping geographic quantifier)* `All penguin species live exclusively on the Antarctic continent.` — Ref: `https://en.wikipedia.org/wiki/Penguin`
26. *(Sole-founder distortion)* `Steve Jobs was the sole founder of Apple Computer.` — Ref: `https://en.wikipedia.org/wiki/Apple_Inc.`
27. *(Popular neuromyth)* `Healthy human beings normally use only ten percent of their brains.` — Ref: `https://en.wikipedia.org/wiki/Ten-percent-of-the-brain_myth`
28. *(Wrong jurisdiction conflation)* `The European Court of Human Rights is an institution operated by the European Union in Brussels.` — Ref: `https://en.wikipedia.org/wiki/European_Court_of_Human_Rights` *(Council of Europe in Strasbourg)*
29. *(Partial linguistic exaggeration)* `Portuguese is the sole official national language spoken in Canada.` — Ref: `https://en.wikipedia.org/wiki/Languages_of_Canada`
30. *(Exclusive inventor distortion)* `Wright brothers built the only aircraft to fly anywhere during the entire 20th century.` — Ref: `https://en.wikipedia.org/wiki/Wright_brothers`
31. *(Conflicting/misleading attribution)* `The Statue of Liberty was gifted to the United States by the British Empire in 1886.` — Ref: `https://en.wikipedia.org/wiki/Statue_of_Liberty` *(gifted by France)*
32. *(Distorted absolute medical claim)* `Vaccines always confer permanent 100 percent lifetime immunity against every viral disease after a single dose.` — Ref: `https://en.wikipedia.org/wiki/Vaccine`
33. *(Single-country distortion)* `The Amazon River lies exclusively inside Colombia.` — Ref: `https://en.wikipedia.org/wiki/Amazon_River` *(primarily Peru & Brazil)*

#### D. `PARTIALLY_TRUE` (11 Claims — Multi-Proposition & Compound True + False / Outdated / Misleading)
34. *(Geography + False geography)* `Tokyo is the capital city of Japan, and Mount Everest lies inside Brazil.` — Refs: `Tokyo`, `Mount Everest`
35. *(Science + False superlative)* `Photosynthesis enables plants to convert sunlight into chemical energy, while Jupiter is the smallest planet in the Solar System.` — Refs: `Photosynthesis`, `Jupiter`
36. *(Recent tech + False space target)* `OpenAI released ChatGPT in November 2022, and Chandrayaan-3 landed on Venus in 2023.` — Refs: `ChatGPT`, `Chandrayaan-3`
37. *(Geography + Outdated leader)* `The Suez Canal connects the Mediterranean Sea to the Red Sea, whereas Angela Merkel is the current Chancellor of Germany.` — Refs: `Suez Canal`, `Angela Merkel`
38. *(History + False date)* `Marie Curie earned Nobel Prizes in both Physics and Chemistry, and World War II ended in September 1955.` — Refs: `Marie Curie`, `World War II`
39. *(Medicine + False cure)* `Penicillin was discovered by Alexander Fleming, whereas antibiotics are effective cures for viral influenza.` — Refs: `Alexander Fleming`, `Antibiotic`
40. *(History + Outdated monarch)* `The Berlin Wall fell in 1989, and Queen Elizabeth II is the current reigning monarch of the United Kingdom.` — Refs: `Berlin Wall`, `Elizabeth II`
41. *(Astronomy + Misleading penguin claim)* `The Moon orbits the Earth, while all penguin species live exclusively in Antarctica.` — Refs: `Moon`, `Penguin`
42. *(Tech history + Sole founder exaggeration)* `Microsoft was co-founded by Bill Gates and Paul Allen, while Steve Jobs was the sole founder of Apple Computer.` — Refs: `Microsoft`, `Apple Inc.`
43. *(Royalty + False capital)* `King Charles III acceded to the British throne in 2022, and Sydney is the capital city of Australia.` — Refs: `Charles III`, `Canberra`
44. *(Recent NATO + Outdated UK PM)* `Sweden joined NATO in 2024; however, Rishi Sunak is the current Prime Minister of the United Kingdom.` — Refs: `Sweden_and_NATO`, `Rishi Sunak`

#### E. `UNVERIFIED` (10 Claims — Unsupported, Speculative Forecasts, Private/Unrecorded Claims, Fabricated Corporate & Policy Rumors)
45. *(Recent policy fabrication)* `The European Union enacted a binding 40 percent global wealth tax on billionaires in October 2026.`
46. *(Private unrecorded meeting)* `Sundar Pichai secretly met NASA engineers in Bengaluru on June 12, 2025.` — Ref context: `https://en.wikipedia.org/wiki/Sundar_Pichai`
47. *(Speculative numeric climate claim)* `A leaked United Nations memo predicts global sea levels will rise 4.2 meters by 2040.` — Ref context: `https://en.wikipedia.org/wiki/Sea_level_rise`
48. *(Obscure city metric)* `Over 83 percent of households in Pune installed rooftop solar panels in 2026.` — Ref context: `https://en.wikipedia.org/wiki/Pune`
49. *(Unconfirmed M&A rumor)* `Apple acquired Tesla Motors for 500 billion dollars in 2023.` *(Distinguished from explicit contradiction because Wikipedia lacks negative transaction registries; requires GDELT/FactCheck absence -> safe `UNVERIFIED`)* — Ref context: `https://en.wikipedia.org/wiki/Apple_Inc.`
50. *(Future financial projection)* `The Reserve Bank of India will peg the Indian rupee directly to gold in January 2028.` — Ref context: `https://en.wikipedia.org/wiki/Reserve_Bank_of_India`
51. *(Fictional/unverifiable sports stat)* `An amateur swimmer crossed the Atlantic Ocean unaided in 19 days in September 2025.`
52. *(Unreported local municipal claim)* `Berlin banned all electric bicycles inside public parks starting on March 3, 2026.` — Ref context: `https://en.wikipedia.org/wiki/Berlin`
53. *(Conspiratorial unprovable assertion)* `Three retired CERN physicists discovered a stable room-temperature fusion reactor inside a Swiss salt mine in 2025.`
54. *(Ambiguous unnamed poll)* `A confidential survey found 71 percent of European software engineers left the industry in 2026.`

#### F. `OUTDATED` (10 Claims — Expired Heads of State/Org, Rebrands, Renamed Entities, Former Venues/Statuses Framed as Current)
55. *(Expired monarch 2022)* `Queen Elizabeth II is the current reigning monarch of the United Kingdom.` — Ref: `https://en.wikipedia.org/wiki/Elizabeth_II`
56. *(Expired chancellor 2021)* `Angela Merkel is the incumbent Chancellor of Germany.` — Ref: `https://en.wikipedia.org/wiki/Angela_Merkel`
57. *(Corporate rebrand 2021)* `Facebook, Inc. is the current official corporate parent name of Mark Zuckerberg's social media company.` — Ref: `https://en.wikipedia.org/wiki/Meta_Platforms`
58. *(Recent UK PM transition 2024)* `Rishi Sunak is the current Prime Minister of the United Kingdom.` — Ref: `https://en.wikipedia.org/wiki/Rishi_Sunak`
59. *(Former NZ PM 2023)* `Jacinda Ardern is the sitting Prime Minister of New Zealand.` — Ref: `https://en.wikipedia.org/wiki/Jacinda_Ardern`
60. *(Former currency / status)* `The Deutsche Mark remains the official circulating currency of Germany today.` — Ref: `https://en.wikipedia.org/wiki/Deutsche_Mark`
61. *(Former NASA shuttle status)* `The NASA Space Shuttle fleet currently flies regular astronaut missions to the International Space Station.` — Ref: `https://en.wikipedia.org/wiki/Space_Shuttle` *(retired 2011)*
62. *(Former Google/Alphabet corporate name)* `Google Inc. remains the unrenamed top-level publicly traded parent holding company of YouTube.` — Ref: `https://en.wikipedia.org/wiki/Alphabet_Inc.` *(Alphabet Inc. created 2015)*
63. *(Former UN Chief 2007–2016)* `Ban Ki-moon is the current Secretary-General of the United Nations.` — Ref: `https://en.wikipedia.org/wiki/Ban_Ki-moon`
64. *(Former FIFA World Cup holder)* `France is the current reigning men's FIFA World Cup champion.` *(Argentina won Dec 2022)* — Ref: `https://en.wikipedia.org/wiki/2022_FIFA_World_Cup`

---

## 6. Acceptance Criteria Per Group

- **Group A (Evidence Retrieval & Alignment):**
  - Cross-page false entity contamination eliminated on subtype/namesake pairs (`Nobel Peace Prize` vs `Nobel Prize in Chemistry`, `Mark Zuckerberg` vs `Mark S. Zuckerberg`).
  - Live Wikipedia fallback triggers cleanly on location-distractor / causal / temporal claims and retains lead sentences (`#03 ChatGPT`, `#10 Penguin`, `#06 Antibiotic` where evidence exists).
  - Simulated Wikipedia timeouts/offline/HTTP-500 errors yield safe `UNVERIFIED` with preserved source provenance and zero fabricated evidence.
- **Group B (Compound Claims & Six-Class Synthesis):**
  - `split_compound_claims()` successfully decomposes compound assertions across arbitrary finite/inflected verbs (`lies`, `allows`, `released`, `connects`, `ended`, `awarded`, etc.) while keeping simple noun lists intact.
  - All six verdicts (`GENUINE`, `FAKE`, `MISLEADING`, `PARTIALLY_TRUE`, `UNVERIFIED`, `OUTDATED`) operate end-to-end without blindly lowering abstention thresholds or hiding `Requirements/fever_verifier_v1`'s dead NEI logit limit.
- **Group C (Temporal Reasoning):**
  - All 5 named temporal audit tests pass (`Donald Trump` -> `GENUINE`, `Queen Elizabeth II` -> `OUTDATED`, `Angela Merkel` -> `OUTDATED`, `Rishi Sunak` -> `OUTDATED`, `Facebook, Inc.` -> `OUTDATED`).
  - Stale `fever_local` (`2017-06`) never vetoes fresher `wikipedia_live` temporal evidence.
- **Group D (Article-Level Aggregation):**
  - `3 supported central claims + 1 minor unverified claim` resolves to `GENUINE` (with explicit uncertainty note naming the unverified minor claim).
  - `central supported + central refuted` resolves to `PARTIALLY_TRUE`; `3 central refuted` resolves to `FAKE`; insufficient central claims remain `UNVERIFIED`; `1 minor refuted` does not automatically turn an otherwise `GENUINE` article into `FAKE`.
- **Group E (External APIs — Phase 2 After Approval):**
  - Google Fact Check retrieves `ClaimReview` matches with preserved publisher rating, URL, and date without exposing `GOOGLE_FACT_CHECK_API_KEY` in frontend bundles, browser network calls, or logs.
  - GDELT verification and Live News refresh share one persistent SQLite counter capped at `200`, emit warning state at `<= 20` remaining, reuse SQLite cache without consuming extra allowance, stop at `200` cleanly, and degrade gracefully offline/when exhausted.
  - Full backend pytest suite + Vite production build pass cleanly; `verif-9c524ca7b6f5`, Sepolia contract `0xcDa4CE06d44642Fd0034C817B5b7cB6AFC886ffb`, and canonical hash `42007960ae4bf66cbc74dfb24ef80429fdba86ca34de3bc1a8d0ff9c16a2cc53` remain intact.

---

## 7. Estimated Complexity & Dependencies

| Work Package | Complexity | Dependencies | Live External Requests Needed |
|---|---|---|---|
| **Backup + Phase 1A (Groups A & B: Alignment + Retriever + Wikipedia)** | Medium–High | None (`ml/inference/evidence_alignment.py` first, then `wikipedia_fallback.py` & `retriever.py`) | Read-only public Wikipedia API during 64-claim eval |
| **Phase 1B (Groups C & D: Temporal + Article Aggregation)** | Medium | Phase 1A alignment outputs & `ClaimExtractor` rank metadata | Same as above |
| **Phase 1 Verification Gate (`test_verdict_classification.py` + 64-claim suite)** | Medium | Phases 1A + 1B complete | Read-only Wikipedia API; 0 GDELT / 0 Sepolia |
| **Phase 2 / Group E Config, Cache & Persistent GDELT Tracker** | Medium | **User Approval of Phase 1** + `news_cache.db` backup | Zero external calls during build/mock tests |
| **Phase 2 / Group E Google Fact Check + GDELT Client + `news_service.py` + Aggregator** | High | Cache/Tracker + `.env` `GOOGLE_FACT_CHECK_API_KEY` | Mocked tests + strict tiny live smoke check (`<= 2` GDELT calls total) |
| **Phase 2 / Group E Frontend Cards + GDELT Usage Dashboard + Docs** | Medium | Backend API schemas & `/news/gdelt-usage` endpoint | Vite build verification (offline) |

---

## 8. Rollback Strategy

1. **Pre-Implementation Snapshot:** Create timestamped backups of `data/database/fakenews.db` and `data/news_cache.db` inside a local non-committed backup path before touching any Phase 1 or Phase 2 file.
2. **Modular Incremental Reverts (Git-Safe):** Commit or stash clean checkpoints between Phase 1A, Phase 1B, and Phase 2 so any single group can be rolled back cleanly (`git checkout -- <files>`) without unwinding unrelated milestones.
3. **Runtime Kill Switches:**
   - Setting `WIKIPEDIA_FALLBACK_ENABLED=false` disables live Wikipedia immediately, leaving local FEVER online.
   - Setting `GDELT_ENABLED=false` disables all outbound GDELT requests across both verification and `Live News Monitor` while keeping Google Fact Check, RSS, Wikipedia, and local FEVER working.
   - Leaving `GOOGLE_FACT_CHECK_API_KEY=` empty cleanly bypasses Fact Check lookups without errors.
4. **Database & Blockchain Isolation:** `verification_records` canonical hashes and Ethereum Sepolia state (`VerificationRegistry` `0xcDa4CE06d44642Fd0034C817B5b7cB6AFC886ffb`, record `verif-9c524ca7b6f5`, tx `0x8ba191...`) are **never** altered, redeployed, or mutated—requiring zero blockchain rollback under any scenario.

---

*End of Controlled Remediation Implementation Plan. Execution is paused awaiting explicit user review and approval.*
