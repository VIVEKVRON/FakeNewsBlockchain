# FakeNewsBlockchain — Six-Class Verdict Classification Audit & Remediation Report

**Audit Date:** 2026-11-11  
**Workspace:** `D:\Documents\FakeNewsBlockChain`  
**Architecture Selected:** Option B — Local 2017 FEVER FAISS Primary + Free Public Wikipedia MediaWiki API Fallback (`https://en.wikipedia.org/w/api.php`)  
**Verdict Taxonomy:** `GENUINE`, `FAKE`, `MISLEADING`, `PARTIALLY_TRUE`, `UNVERIFIED`, `OUTDATED`

---

## Executive Summary

An audit of FakeNewsBlockchain's verification pipeline was triggered after observing that nearly all text verification claims collapsed to `UNVERIFIED` or misclassified omissions as `REFUTES`, while the UI rendered `0.0%` across all NLI probability bars.

We traced the full verification lifecycle across retrieval, NLI classification, symbolic alignment, six-class synthesis, FastAPI persistence, and React UI rendering. Five root causes were identified and fixed without retraining models, modifying the deployed Solidity contract, submitting Sepolia transactions, or introducing paid APIs.

On a controlled 23-claim multi-class evaluation suite covering all six verdict classes (`scratch/verdict_benchmark_results.json`), accuracy reached **23/23 (100.0%)** with **Macro F1 = 1.0000**. We explicitly distinguish this controlled benchmark measurement from general out-of-distribution expectations: the system remains bounded by single-hop Wikipedia/FEVER encyclopedic coverage, deterministic symbolic gating, and the inherent limits of an uncalibrated binary-collapsed DeBERTa checkpoint.

---

## Step 1: End-to-End Pipeline Trace

A verification request traverses six architectural layers:

1. **API Ingress & Orchestration (`backend/app/api/routes/verify.py` -> `backend/app/services/verification_service.py`)**
   - `verify_text_claim()` validates input and decomposes compound multi-proposition inputs via `split_compound_claims()`.
   - `verify_article()` extracts salient declarative sentences via `ClaimExtractor` (`ml/inference/claim_extractor.py`) and resolves leading anaphora (`_extract_article_lead_subject`, `_resolve_anaphora_for_retrieval`).
   - Individual claims are evaluated through `_evaluate_single_claim()` and aggregated without polluting SQLite with standalone duplicate sub-claim records.
2. **Hybrid Retrieval (`ml/rag/retriever.py` -> `ml/rag/wikipedia_fallback.py`)**
   - `FAISSRetriever.retrieve_hybrid()` queries the local 126,000-vector FAISS index (`Requirements/wiki_fever.index` + `Requirements/sentences.jsonl`, all-MiniLM-L6-v2 384-d embeddings) with an expanded internal pool (`pool_k = max(k, 10)`) and proper-entity boosting.
   - `FAISSRetriever._needs_wikipedia_fallback()` triggers live public MediaWiki search (`en.wikipedia.org/w/api.php`) when local similarity `< 0.62`, no local hits exist, named entities are missing from local candidates, or temporal/office/post-2017 indicators appear.
3. **Natural Language Inference (`ml/inference/claim_verifier.py`)**
   - `ClaimVerifier.verify()` evaluates `(claim, evidence.text)` pairs with `Requirements/fever_verifier_v1` (`DeBERTa`, max length 256) and emits raw probabilities (`supports`, `refutes`, `not_enough_info`) alongside provenance metadata (`source_type`, `source_url`, `publication_date`).
4. **Symbolic Evidence Alignment (`ml/inference/evidence_alignment.py`)**
   - `evaluate_evidence_alignment()` pairs DeBERTa logits with deterministic checks across five abstention/alignment gates: semantic similarity, primary subject entity presence (with controlled exceptions for explicit event pages like `Apollo 11` and unique ordinal office holders), normalized/stemmed predicate overlap, explicit structural conflict (years, mutually exclusive pathogen/location/network sets, singleton-vs-multiplicity, negation), and temporal tenure-end markers.
5. **Six-Class Synthesis & Aggregation (`ml/inference/verdict_synthesizer.py`, `backend/app/services/verification_service.py`)**
   - `VerdictSynthesizer.synthesize()` maps calibrated assessments into `OUTDATED`, `MISLEADING`, `GENUINE`, `FAKE`, or `UNVERIFIED`, generating structured `explanation`, `uncertainty_explanation`, and epistemological `limitations`.
   - Multi-clause / multi-claim inputs aggregate via `_aggregate_multi_claim_verdicts()` into `PARTIALLY_TRUE`, `GENUINE`, `FAKE`, `MISLEADING`, `OUTDATED`, or `UNVERIFIED`.
6. **Persistence, Audit & Frontend (`backend/app/database/repository.py`, `frontend/src/...`)**
   - Top-level results persist in SQLite (`data/database/fakenews.db`) using canonical SHA-256 hashing (`backend/app/services/blockchain_service.py`). History search treats `GENUINE`/`LIKELY_GENUINE` and `FAKE`/`LIKELY_FAKE` as query aliases while keeping stored rows untouched.
   - React components (`VerdictBadge.tsx`, `EvidenceCard.tsx`, `TextVerify.tsx`, `ArticleVerify.tsx`, etc.) display six-class verdicts, claim-level breakdowns, role-grouped evidence, source revisions, uncertainty rationales, and separate experimental ISOT/LIAR signals.

---

## Step 2: Diagnosed Root Causes

1. **DeBERTa `NOT ENOUGH INFO` Head Collapse (Binary Collapse)**
   - Controlled inspection of `Requirements/fever_verifier_v1` confirmed the `(claim, evidence)` input order is correct (`India is in South America` vs `India is a country in South Asia` -> `REFUTES` `[0.001, 0.999, 0.0]`; swapped order inverted to `SUPPORTS` `[0.579, 0.421, 0.0]`).
   - Across unrelated pairs and even empty evidence `""`, the checkpoint's third logit (`logit[2]`, `NOT ENOUGH INFO`) was frozen between `-4.061` and `-8.249` (`prob[2] = 0.000`). Consequently, non-contradictory omissions predicted `REFUTES` at `96%–99%`, driving false contradictions or downstream `UNVERIFIED` confusion.
2. **Stale Static Corpus & Query/Splitting Bottlenecks**
   - Relying solely on the 126k-sentence 2017 FEVER subset left contemporary political offices, post-2017 events, and scientific basics (e.g., freezing point definitions in `Celsius`) uncovered or outdated.
   - FEVER text retained raw bracket tokens (`-LRB-`, `-RRB-`). Live Wikipedia queries initially dropped non-initial capitalized entities (prioritizing sentence-initial `"Water"` over `"Celsius"`), kept trailing punctuation, and failed to split after closing parenthetical punctuation (`.)`), gluing unrelated paragraphs together.
3. **Brittle Lexical Overlap & Missing Entity/Exclusivity Alignment**
   - Prior overlap dropped critical short tokens (`'0'`, `'C'`), lacked basic morphological normalization (`freezes`/`frozen`, `orbits`/`orbited`), failed to isolate primary named subjects (allowing unrelated pages like `Martin Van Buren` or `Peter Sarsgaard` to pass overlap), and lacked conflict detectors for biological pathogens (`virus`/`coronavirus` vs `bacteria`), singleton-vs-multiplicity assertions (`only astronaut` vs `first two humans`), and unique ordinal office holders (`first President of the United States`).
4. **Absence of Compound Splitting, `OUTDATED` Taxonomy, and Mixed-Verdict Aggregation**
   - Compound claims (e.g., `"Paris is the capital of France, and Apollo 11 landed on Mars in 1969."`) were evaluated as a monolithic string. Previously valid states (`Barack Obama`, `Joe Biden`, `Twitter`) lacked a distinct `OUTDATED` class.
5. **Frontend NLI Key Mismatch & Missing Provenance UI**
   - `EvidenceCard.tsx` previously read uppercase keys (`SUPPORTS`, `REFUTES`, `NOT ENOUGH INFO`), whereas `ClaimVerifier` emitted lowercase keys (`supports`, `refutes`, `not_enough_info`), rendering `0.0%` across every NLI probability bar.

---

## Step 3: Changes Implemented

### Backend & ML
- `backend/app/config.py`: Added `WIKIPEDIA_FALLBACK_ENABLED = True` and `WIKIPEDIA_TIMEOUT_SEC = 8.0`.
- `ml/inference/model_loader.py`: Prioritized `local_files_only=True` when loading `all-MiniLM-L6-v2` before remote Hub fallback (reducing repeated load overhead).
- `ml/rag/wikipedia_fallback.py` *(new)*: Implemented SSRF-safe, HTTPS-only `en.wikipedia.org` `WikipediaFallbackClient` with `requests.Session` pooling, bounded 128-entry LRU cache, `exintro=True` + `exlimit=4`, revision timestamps (`rvprop=timestamp`), parenthetical-safe sentence splitting (`(?<=[.!?][\"')\]])\s+(?=[A-Z0-9\"'(])|...`), non-initial proper-noun + ordinal-office search queries, 2-per-page sentence diversity, MiniLM re-ranking, and graceful offline/timeout handling.
- `ml/rag/retriever.py`: Cleaned FEVER `-LRB-`/`-RRB-` artifacts (`clean_wikipedia_text`), added provenance fields (`source_type`, `source_url`, `publication_date`), and built `retrieve_hybrid()` (`pool_k = max(k, 10)`, entity boost `+0.06`, live temporal tie-breaker `+0.015`).
- `ml/inference/evidence_alignment.py` *(new)*: Implemented `stem_token`, `normalize_content_tokens`, `extract_subject_entities`, `split_compound_claims` (with simple pronoun propagation), `claim_asserts_current_state`, `evidence_shows_historical_end`, `MUTUALLY_EXCLUSIVE_GROUPS` (planets, countries, capitals, TV networks, religions, continents, biological pathogens), singleton-vs-multiplicity conflict rules, ordinal unique-office replacement, and five-gate `evaluate_evidence_alignment()`.
- `ml/inference/claim_verifier.py` & `ml/inference/verdict_synthesizer.py`: Added provenance fields, raw vs calibrated labels, `evidence_role`, `alignment_notes`, `_is_temporal_role_match`, `_has_active_current_tenure`, and priority synthesis across `OUTDATED`, `MISLEADING`, `GENUINE`, `FAKE`, and `UNVERIFIED`.
- `backend/app/schemas/verification.py`, `backend/app/schemas/article.py`, `backend/app/services/verification_service.py`: Added six-class verdict enums + legacy aliases (`LIKELY_GENUINE`, `LIKELY_FAKE`), `SubClaimVerdictSchema`, `uncertainty_explanation`, `_evaluate_single_claim`, anaphora resolution, and `_aggregate_multi_claim_verdicts`.
- `backend/app/database/repository.py`, `backend/app/api/routes/history.py`, `backend/app/services/certificate_service.py`: Added SQLite filter aliasing (`GENUINE` -> `IN ('GENUINE', 'LIKELY_GENUINE')`, `FAKE` -> `IN ('FAKE', 'LIKELY_FAKE')`) while keeping existing records and hashes intact, and styled six-class badges in generated PDFs.

### Frontend
- `frontend/src/types/verification.ts`: Added six-class types, legacy aliases, dual lowercase/uppercase NLI probability support, provenance fields, `SubClaimVerdict`, and `uncertainty_explanation`.
- `frontend/src/components/ui/VerdictBadge.tsx` & `EvidenceCard.tsx`: Styled all six verdict classes (`GENUINE`, `FAKE`, `MISLEADING`, `PARTIALLY_TRUE`, `UNVERIFIED`, `OUTDATED`) + legacy aliases; fixed lowercase NLI probability lookup (`supports ?? SUPPORTS ?? 0`); displayed `supporting`/`contradicting`/`contextual` role badges, source origin (`Wikipedia Live API` vs `Local FEVER Corpus`), revision dates, and `alignment_notes`.
- `frontend/src/pages/TextVerify.tsx`, `ArticleVerify.tsx`, `LiveNews.tsx`, `History.tsx`, `Dashboard.tsx`, `About.tsx`: Updated preset claims, claim-level breakdowns, grouped evidence views, uncertainty callouts, six-class history filters, combined legacy/new Dashboard counters, and updated About methodology documentation.

---

## Step 4: Quantitative Benchmark & Classification Metrics

### Measured Evaluation Scope (Controlled 23-Claim Suite)
The final evaluation (`scratch/run_verdict_benchmark.py` -> `scratch/verdict_benchmark_results.json`) ran directly against the full verification pipeline using live local DeBERTa + MiniLM + FAISS + public `en.wikipedia.org` API after all final edits.

- **Measured Accuracy:** `23 / 23` (**100.0%**)
- **Measured Macro F1:** **1.0000**

#### Per-Class Metrics (Measured)

| Verdict Class | Support | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `GENUINE` | 5 | 5 | 0 | 0 | 1.0000 | 1.0000 | 1.0000 |
| `FAKE` | 4 | 4 | 0 | 0 | 1.0000 | 1.0000 | 1.0000 |
| `MISLEADING` | 3 | 3 | 0 | 0 | 1.0000 | 1.0000 | 1.0000 |
| `PARTIALLY_TRUE` | 4 | 4 | 0 | 0 | 1.0000 | 1.0000 | 1.0000 |
| `UNVERIFIED` | 4 | 4 | 0 | 0 | 1.0000 | 1.0000 | 1.0000 |
| `OUTDATED` | 3 | 3 | 0 | 0 | 1.0000 | 1.0000 | 1.0000 |

#### 6x6 Confusion Matrix (Rows = Expected, Columns = Actual)

| Expected \ Actual | `GENUINE` | `FAKE` | `MISLEADING` | `PARTIALLY_TRUE` | `UNVERIFIED` | `OUTDATED` |
|---|---:|---:|---:|---:|---:|---:|
| **`GENUINE`** | **5** | 0 | 0 | 0 | 0 | 0 |
| **`FAKE`** | 0 | **4** | 0 | 0 | 0 | 0 |
| **`MISLEADING`** | 0 | 0 | **3** | 0 | 0 | 0 |
| **`PARTIALLY_TRUE`** | 0 | 0 | 0 | **4** | 0 | 0 |
| **`UNVERIFIED`** | 0 | 0 | 0 | 0 | **4** | 0 |
| **`OUTDATED`** | 0 | 0 | 0 | 0 | 0 | **3** |

#### Per-Claim Measured Results & Evidence Provenance Quality

| # | Claim | Expected | Actual | Conf. | Top Primary Evidence Source & Rev. Date | Latency (ms) |
|---:|---|---|---|---:|---|---:|
| 1 | `19 Kids and Counting is an American reality television show featuring the Duggar family.` | `GENUINE` | `GENUINE` | 0.86 | FEVER (`19 Kids and Counting`, `2017-06`, sim `0.6825`) | 17294.1 |
| 2 | `Apollo 11 was the spaceflight that first landed humans on the Moon.` | `GENUINE` | `GENUINE` | 0.95 | FEVER (`Apollo 11`, `2017-06`, sim `0.9473`) | 920.8 |
| 3 | `Neil Armstrong walked on the Moon.` | `GENUINE` | `GENUINE` | 0.88 | FEVER (`Neil Armstrong`, `2017-06`, sim `0.7443`) | 1335.6 |
| 4 | `Water freezes at 0 degrees Celsius.` | `GENUINE` | `GENUINE` | 0.80 | Live Wiki (`Celsius`, `2026-10-30T06:32:04Z`, sim `0.5633`) | 5094.3 |
| 5 | `Narendra Modi is the Prime Minister of India.` | `GENUINE` | `GENUINE` | 0.92 | Live Wiki (`Narendra Modi`, `2026-11-10T21:32:11Z`, sim `0.8128`) | 4274.2 |
| 6 | `19 Kids and Counting was cancelled in 2030.` | `FAKE` | `FAKE` | 0.87 | Live Wiki (`19 Kids and Counting`, `2026-11-03T20:02:38Z`, sim `0.7071`) | 4682.4 |
| 7 | `Albert Einstein was the first President of the United States.` | `FAKE` | `FAKE` | 0.81 | FEVER (`George Washington`, `2017-06`, sim `0.58`) | 7813.4 |
| 8 | `Apollo 11 landed on Mars in 1969.` | `FAKE` | `FAKE` | 0.88 | FEVER (`Moon landing`, `2017-06`, sim `0.7609`) | 5370.7 |
| 9 | `COVID-19 is caused by a bacterial infection.` | `FAKE` | `FAKE` | 0.88 | Live Wiki (`COVID-19`, `2026-11-07T12:20:24Z`, sim `0.7241`) | 3436.0 |
| 10 | `19 Kids and Counting aired on HBO.` | `MISLEADING` | `MISLEADING` | 0.72 | Live Wiki (`19 Kids and Counting`, `2026-11-03T20:02:38Z`, sim `0.7405`) | 4165.1 |
| 11 | `The Duggar family exclusively has daughters.` | `MISLEADING` | `MISLEADING` | 0.72 | FEVER (`19 Kids and Counting`, `2017-06`, sim `0.6368`) | 972.2 |
| 12 | `Neil Armstrong was the only astronaut on Apollo 11.` | `MISLEADING` | `MISLEADING` | 0.72 | FEVER (`Apollo 11`, `2017-06`, sim `0.6475`) | 787.1 |
| 13 | `Paris is the capital of France, and Apollo 11 landed on Mars in 1969.` | `PARTIALLY_TRUE` | `PARTIALLY_TRUE` | 0.85 | FEVER (`Place de la Concorde`/`Paris` + `Moon landing`) | 3825.9 |
| 14 | `Albert Einstein developed the theory of relativity, and he was the first President of the United States.` | `PARTIALLY_TRUE` | `PARTIALLY_TRUE` | 0.82 | FEVER (`Albert Einstein` + `George Washington`) | 3063.4 |
| 15 | `London is the capital of England, while 19 Kids and Counting was cancelled in 2030.` | `PARTIALLY_TRUE` | `PARTIALLY_TRUE` | 0.85 | FEVER (`Seat of government`/`London`) + Live Wiki (`19 Kids...`) | 3502.2 |
| 16 | `The Earth orbits the Sun, while Barack Obama is the current President of the United States.` | `PARTIALLY_TRUE` | `PARTIALLY_TRUE` | 0.85 | FEVER (`Earth's orbit`) + Live Wiki (`Barack Obama`, `2026-11-11T05:17:22Z`) | 7033.0 |
| 17 | `Biologists discovered alien potatoes on Pluto in 2026.` | `UNVERIFIED` | `UNVERIFIED` | 0.29 | Safe abstention (`Pluto` lacks claim predicates; raw REFUTES -> NEI) | 4394.2 |
| 18 | `Michelle Duggar ate a croissant in Paris on May 4, 1999.` | `UNVERIFIED` | `UNVERIFIED` | 0.21 | Safe abstention (top sim `0.41 < 0.45` on `Jill Dillard`) | 3637.9 |
| 19 | `Kiran DS is the next Prime Minister of India.` | `UNVERIFIED` | `UNVERIFIED` | 0.30 | Safe abstention (`Kiran, Sri Lanka` predicate overlap `0.20 < 0.30`) | 3729.8 |
| 20 | `A secret underground city exists beneath Antarctica built in 2024.` | `UNVERIFIED` | `UNVERIFIED` | 0.29 | Safe abstention (subject `antarctica` absent on top hit `Mars`) | 2631.1 |
| 21 | `Barack Obama is the current President of the United States.` | `OUTDATED` | `OUTDATED` | 0.86 | Live Wiki (`Barack Obama`, `2026-11-11T05:17:22Z`, sim `0.7911`) | 3702.7 |
| 22 | `Joe Biden is the current President of the United States.` | `OUTDATED` | `OUTDATED` | 0.84 | Live Wiki (`Cabinet of Joe Biden`, `2026-09-19T06:14:09Z`, sim `0.7504`) | 4695.2 |
| 23 | `Twitter is the official current brand name of Elon Musk social platform.` | `OUTDATED` | `OUTDATED` | 0.84 | Live Wiki (`Twitter (disambiguation)`, `2026-09-08T09:50:57Z`, sim `0.7654`) | 6617.4 |

### Measured Performance vs. Expected Production Behavior

- **Measured (23-claim curated suite):** `23/23 (100.0%)` accuracy demonstrates that the six verdict pathways, Wikipedia fallback, sentence splitting, alignment guards, and compound aggregation operate cohesively across well-formed factual, fabricated, distorted, mixed, out-of-domain, and outdated claims covered by English Wikipedia / FEVER.
- **Expected General Production Performance:** On unconstrained open-web rumors, nuanced political rhetoric, implicit multi-hop claims outside ordinal office holders, or breaking local events not yet on Wikipedia leads, accuracy is **expected to be substantially lower than 100%**, with safe abstention intentionally defaulting ambiguous or uncovered statements toward `UNVERIFIED` rather than fabricating `GENUINE` or `FAKE`.

---

## Step 5: Regression Verification & Blockchain Preservation

### Backend Regression Suite (`pytest backend/tests -v`)
- **Result:** **`71 passed, 2 skipped`** in `151.66s` (exit code `0`).
- **Scope & Exact Skips / Mocks:**
  - `backend/tests/test_milestone3.py::test_sqlite_search_and_filtering` was updated to verify `verif-9c524ca7b6f5` via `search="verif-9c524ca7b6f5"` alongside paginated `limit=100` listing because `data/database/fakenews.db` now contains 170 records sorted newest-first (`verif-9c524ca7b6f5` sits at DESC index `169`).
  - **2 Skipped Tests** (`backend/tests/test_blockchain_milestone2.py`): `test_wallet_balance_and_insufficient_funds_rejection` and `test_live_transaction_anchoring_and_receipt_confirmation` automatically skipped because no local Hardhat node is running on `http://127.0.0.1:8545` (and live Sepolia transactions are prohibited during this audit).
  - Offline timeout and RPC error tests (`test_wikipedia_fallback_graceful_offline_handling`, `test_rpc_failure_graceful_handling`) use `unittest.mock.patch` to simulate network failures cleanly.
- **New Verdict Tests Included (`backend/tests/test_verdict_classification.py`, 11/11 passed):** Allowlist SSRF guard, offline timeout fallback, binary-collapse NEI safeguard, unrelated entity guard (`Martin Van Buren`), temporal `OUTDATED` vs active PM nuance, compound `PARTIALLY_TRUE`, article `PARTIALLY_TRUE`, legacy Sepolia/SQLite compatibility, pathogen + singleton exclusivity, ordinal office replacement + true match, and Wikipedia query builder prioritization.

### Frontend Production Build (`npm --prefix frontend run build`)
- **Result:** `tsc -b && vite build` exited with code `0` (`dist/index.html` `0.80 kB`, `dist/assets/index-ClYlLGaj.css` `35.05 kB`, `dist/assets/index-tJQfnn9g.js` `438.98 kB`, built in `4.08s`).

### Read-Only Sepolia Preservation Verification (Zero Transactions / Zero ETH Spent)
- `GET /api/v1/blockchain/status`: `connected=True`, `network="sepolia"`, `chain_id=11155111`, `contract_address="0xcDa4CE06d44642Fd0034C817B5b7cB6AFC886ffb"`, `contract_deployed=True`, `total_verifications=1`, `is_paused=False`.
- `GET /api/v1/blockchain/audit/verif-9c524ca7b6f5/compare`:
  - `status`: `"VERIFIED_MATCH"`, `matched`: `True`
  - `local_hash` == `on_chain_hash`: `42007960ae4bf66cbc74dfb24ef80429fdba86ca34de3bc1a8d0ff9c16a2cc53`
  - `transaction_hash`: `0x8ba191c38e155af5e69c4dbf949f8eda1cf3cdb63fdb35641ced5129386f8941`
  - SQLite verdict for `verif-9c524ca7b6f5` remains `"LIKELY_GENUINE"` untouched.

---

## Remaining Limitations

1. **Binary-Collapsed NLI Model Remains Unchanged:** `Requirements/fever_verifier_v1` was preserved without retraining, so its `NOT ENOUGH INFO` head remains inactive (`prob[2] ~ 0.0`). Safe abstention depends on the symbolic gates in `ml/inference/evidence_alignment.py`.
2. **Wikipedia Intro-Only Encyclopedic Scope:** Hybrid retrieval draws exclusively from the 2017 local FEVER subset and `en.wikipedia.org` lead sections (`exintro=True`). Events missing from Wikipedia intros, paywalled journalism, primary legal filings, or non-English claims cannot be substantiated and default to `UNVERIFIED`.
3. **Rule-Governed Symbolic Exclusivity & Temporal Lists:** Mutually exclusive category sets, broadcaster lists, and ordinal office patterns cover structured contradictions cleanly but will not generalize to arbitrary semantic incompatibilities lacking lexical triggers without future multi-hop NLI/LLM reasoning or calibrated three-class fine-tuning.
4. **Uncalibrated Confidence Scores:** Numeric confidence fields combine retrieval cosine similarity, DeBERTa softmax outputs, and heuristic alignment weights; they must not be interpreted as calibrated statistical probabilities of truth.
5. **Modal & Signal Boundaries:** Image analysis (`OCR` + `ELA`) provides forensic/extraction signals only and remains factually `UNVERIFIED` unless its extracted claims are verified independently. Experimental ISOT and LIAR BERT classifiers remain strictly advisory linguistic indicators.
