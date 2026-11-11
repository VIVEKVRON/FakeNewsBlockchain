# FakeNewsBlockchain — Phase 1 Controlled Remediation Report

**Report Date:** 2026-11-11  
**Project Directory:** `D:\Documents\FakeNewsBlockChain`  
**Scope Executed:** **Phase 1 ONLY (Groups A, B, C, D + Pre-Implementation Backups + Seed Timestamp Correction + Corrections 1–4)**  
**Phase 2 / Group E Status:** **Deferred cleanly** (Google Fact Check Tools API & GDELT DOC 2.0 integrations were NOT implemented yet, awaiting explicit user approval of Phase 1).

---

## 1. Executive Summary

Phase 1 targeted the structural retrieval, entity-alignment, syntactic compound-clause, temporal reasoning, and weighted article aggregation failures diagnosed in [REAL_WORLD_VALIDATION_REPORT.md](file:///D:/Documents/FakeNewsBlockChain/REAL_WORLD_VALIDATION_REPORT.md), strictly incorporating all four mandatory user corrections without modifying trained model weights, retraining models, modifying the deployed Sepolia contract (`0xcDa4CE06d44642Fd0034C817B5b7cB6AFC886ffb`), submitting blockchain transactions, or exposing `.env` credentials.

| Evaluation Metric | Pre-Phase-1 Baseline (`26`-Claim Audit) | Post-Phase-1 (`64`-Claim Audited Suite) | Delta |
|---|---:|---:|---:|
| **Overall Six-Class Accuracy** | `50.0%` (`13 / 26`) | **`87.5%` (`56 / 64`)** | **`+37.5 pp`** |
| **Macro-Averaged F1** | `0.4516` | **`0.8704`** | **`+0.4188`** |
| **False `GENUINE` Predictions** | `6` (`GENUINE` Precision `0.4000`) | **`0` (`GENUINE` Precision `1.0000`)** | **`-6` (Eliminated)** |
| **False `FAKE` Predictions** | `0` | **`0` (`FAKE` Precision `1.0000`)** | **Preserved at `0`** |
| **Other Wrong-Class Errors** | `1` (`Donald Trump` -> `OUTDATED`) | **`0` (`0 / 64`)** | **`-1` (Eliminated)** |
| **Conservative `UNVERIFIED` Abstentions** | `6` | **`8`** *(safe missing/incomplete-evidence abstentions)* | All 8/8 audited |

---

## 2. Implementation Summary of Mandatory Corrections (1–4)

### Correction 1 — Syntactic Compound Claim Splitting
- **Location:** [`_has_independent_clause_structure()`](file:///D:/Documents/FakeNewsBlockChain/ml/inference/evidence_alignment.py), [`_extract_antecedent_subject()`](file:///D:/Documents/FakeNewsBlockChain/ml/inference/evidence_alignment.py), and [`split_compound_claims()`](file:///D:/Documents/FakeNewsBlockChain/ml/inference/evidence_alignment.py).
- **Behavior Implemented:** Replaced morphology-only regex reliance with deterministic Subject + Finite-Predicate clause structure validation requiring:
  1. Subject nominal/pronoun head preceding the candidate predicate verb position `i >= 1`.
  2. Four-tier predicate check: auxiliary/copula/modal (`was discovered`, `is caused`), irregular past/base predicates (`built`, `won`, `fell`), regular `-ed` past predicates (blocking index-0/prepositional participial adjectives), and regular 3rd-person singular `-s/-es` predicates with **subject-number agreement** and **verbal complement validation** (rejecting plural nouns like `"three other science prizes"` or `"medieval crowns"`).
  3. Anaphoric pronoun subject resolution (`he`, `she`, `it`, `they`) preserving expletive `"it is widely believed/known/reported that..."` and `"The <Subject>"` antecedents.
- **Verified By Test [`test_correction1_syntactic_clause_splitting`](file:///D:/Documents/FakeNewsBlockChain/backend/tests/test_verdict_classification.py):**
  - Coordinated noun lists (`"Alice, Bob, and Carol..."`, `"...three other science prizes"`, `"Developed nations, coastal cities, and island territories..."`, `"ancient coins, Roman statues, and medieval crowns"`) remain unsplit (`len == 1`).
  - Finite passive constructions (`"Penicillin was discovered by..., whereas influenza is caused by..."`) split cleanly (`len == 2`), while reduced participial phrases (`"Founded in 1975 and led by Bill Gates..."`) stay unsplit (`len == 1`).
  - Non-whitelisted finite verbs (`converts`, `orbits`, `burns`, `boils`, `lies`), pronoun clauses (`she`, `it`), and subordinate/appositive/prepositional non-split sentences all behave accurately.

### Correction 2 — Strict Six-Class Verdict Definitions
- Kept all six canonical classes (`GENUINE`, `FAKE`, `MISLEADING`, `PARTIALLY_TRUE`, `UNVERIFIED`, `OUTDATED`) plus legacy history filter compatibility (`LIKELY_GENUINE`, `LIKELY_FAKE`).
- Added strict Gate 2–5 abstention checks in [`evaluate_evidence_alignment()`](file:///D:/Documents/FakeNewsBlockChain/ml/inference/evidence_alignment.py) and [`VerdictSynthesizer.synthesize()`](file:///D:/Documents/FakeNewsBlockChain/ml/inference/verdict_synthesizer.py):
  - `GENUINE` and `FAKE` require `entity_matched == True`, adequate non-entity predicate overlap, role-noun presence when office/prize roles are claimed, and absence of narrowing scope traps (`"manned"` vs `"spacecraft"`, `"state capital"` vs national capital).
  - Unverified rumors/M&A claims lacking documentary refutation (`"Apple acquired Tesla Motors..."`) remain strictly `UNVERIFIED` (`test_correction2_missing_evidence_never_infers_fake`, `#45–#54` `10 / 10` pass).

### Correction 3 — Pre-Run Validation Dataset Audit (`64` Claims)
Before executing the validation harness, all 64 candidate propositions from `docs/CONTROLLED_REMEDIATION_PLAN.md` were audited against live Wikipedia API extracts, URLs, and revision timestamps (`dataset64_audited.json` in conversation scratch storage), enforcing zero overlap with the 23 baseline claims in `scratch/run_verdict_benchmark.py`:
- **2026 FIFA World Cup Review (`#64`):** The draft plan had cited `2022_FIFA_World_Cup` (`France` vs `Argentina`). Because the audit date is **2026-11-11** and the 23rd FIFA World Cup concluded on **19 July 2026** with **Spain defeating defending holders Argentina** ([`FIFA_World_Cup`](https://en.wikipedia.org/wiki/FIFA_World_Cup) rev `2026-11-10T11:12:02Z`; [`2026_FIFA_World_Cup`](https://en.wikipedia.org/wiki/2026_FIFA_World_Cup) rev `2026-11-08T19:20:59Z`), `#64` was updated to `"Argentina is the current reigning men's FIFA World Cup champion."` (`OUTDATED`), testing post-July 2026 championship staleness cleanly.
- **`MISLEADING` Scope Audit (`#28`, `#29`, `#31`, `#33`):** Replaced invalid pure-entity-swap `FAKE` candidates (`"Portuguese is the sole official national language of Canada"` -> `"French is the sole official national language of Canada."`; British Statue of Liberty -> `"The Great Wall of China is one single unbroken continuous wall built during a single dynasty."`; Colombia-only Amazon -> `"The Amazon River flows exclusively inside Brazil."`; EU-Brussels ECtHR -> `"Only the United States has ever successfully landed a spacecraft on the Moon."`).
- **Wikipedia Intro Clarity (`#11`):** Grounded `"Euro banknotes and coins began circulating in 2002 after the currency entered existence in January 1999."` directly in [`History_of_the_euro`](https://en.wikipedia.org/wiki/History_of_the_euro) (`2026-06-09T19:29:45Z`) alongside canonical URL correction for [`Sweden–NATO relations`](https://en.wikipedia.org/wiki/Sweden%E2%80%93NATO_relations) (`2026-11-04T19:38:30Z`).

### Correction 4 — Weighted Centrality × Materiality × Evidence Aggregation
- **Location:** [`_compute_factual_materiality()`](file:///D:/Documents/FakeNewsBlockChain/backend/app/services/verification_service.py), [`_aggregate_multi_claim_verdicts()`](file:///D:/Documents/FakeNewsBlockChain/backend/app/services/verification_service.py), and [`VerificationService.verify_article()`](file:///D:/Documents/FakeNewsBlockChain/backend/app/services/verification_service.py).
- **Behavior Implemented:** Passes `candidate_weights=[(rank, candidate.relevance_score), ...]` from article claim extraction into weighted aggregation combining:
  - **Centrality:** rank decay (`rank 1..3` central when normalized relevance holds, `rank >= 4` or low relative score classified minor/peripheral),
  - **Factual Materiality:** entities + numeric/year anchors vs peripheral/hedged attribution (`0.65` vs `1.0–1.15`),
  - **Evidence Strength:** calibrated verdict confidence weighting.
- **Verified By Test [`test_correction4_weighted_central_vs_peripheral_article_aggregation`](file:///D:/Documents/FakeNewsBlockChain/backend/tests/test_verdict_classification.py):**
  - `3 central GENUINE + 1 minor UNVERIFIED` -> **`GENUINE`** (explanation + uncertainty note explicitly identify the unverified minor detail and weights).
  - `2 central GENUINE + 1 central FAKE` -> **`PARTIALLY_TRUE`**.
  - `3 minor GENUINE + 1 central FAKE` -> **`FAKE`** *(explicitly blocks minor truths from hiding central falsification)*.
  - `3 central FAKE` -> **`FAKE`**.
  - `1 central GENUINE + 1 central UNVERIFIED` -> **`UNVERIFIED`**.

---

## 3. Files Modified in Phase 1

| File Path | Group(s) | Summary of Changes |
|---|---|---|
| [ml/inference/evidence_alignment.py](file:///D:/Documents/FakeNewsBlockChain/ml/inference/evidence_alignment.py) | A, B, C | Subject-first orthogonal subtype guard; middle-initial namesake guard; possessive entity priority; lowercase topic-noun subject extraction; compound title prefix skipping (`mount`); `(born YYYY)` exclusion; disjoint-year & non-entity predicate overlap Gate 5 checks; critical role noun & narrowing scope qualifier guards; national vs state/provincial capital scope checks; syntactic clause validator + pronoun resolution (`split_compound_claims`); non-contiguous active-tenure detector (`evidence_confirms_active_tenure`); extended temporal/rebrand/owner patterns. |
| [ml/rag/wikipedia_fallback.py](file:///D:/Documents/FakeNewsBlockChain/ml/rag/wikipedia_fallback.py) | A | Expanded `QUERY_FILLER_WORDS`; possessive stripping in `build_wikipedia_search_queries()`; corporate parent query support; HTTP `429` retry + empty-body handling; lead-sentence (`sentence_id <= 1`) & exact-title matching priority in `retrieve()`. |
| [ml/rag/retriever.py](file:///D:/Documents/FakeNewsBlockChain/ml/rag/retriever.py) | A, C | Expanded `temporal_or_office_claim` regex (`sitting`, `reigning`, `remains`, `champion`, `unrenamed`); lowercase head-noun & sweeping-quantifier fallback triggers (`< 0.85`); relaxed `live_extras` replacement margin (`0.12`) in temporal/sweeping modes so live pages are not crowded out by local FEVER distractors. |
| [ml/inference/verdict_synthesizer.py](file:///D:/Documents/FakeNewsBlockChain/ml/inference/verdict_synthesizer.py) | B, C | Added `"single"` to `ABSOLUTE_FRAMING_WORDS`; prevented stale `2017-06` `fever_local` hits from vetoing `OUTDATED` or certifying `GENUINE` when live Wikipedia exists for current-state claims; handled non-contiguous terms (`Donald Trump`) without false `MISLEADING`/`OUTDATED`; retained Gate-5 structural `REFUTES`; resolved secondary biographical timeline years when exact claimed year is supported; enforced exclusive/year dominance over partial prefix matches in `Case 2C`; required `entity_matched` for `GENUINE`/`FAKE`. |
| [backend/app/services/verification_service.py](file:///D:/Documents/FakeNewsBlockChain/backend/app/services/verification_service.py) | D | Added `_compute_factual_materiality()`, weighted centrality × materiality × evidence aggregation in `_aggregate_multi_claim_verdicts()`, removed unreachable legacy tail lines, and passed `candidate_weights` from `verify_article()`. |
| [backend/app/database/repository.py](file:///D:/Documents/FakeNewsBlockChain/backend/app/database/repository.py) | Hygiene | Corrected `seed_confirmed_sepolia_record_if_empty()` integer `block_timestamp` from `1762427544` to `1793963544` matching `2026-11-06T11:12:24+00:00` for fresh setups (no change to existing persisted records). |
| [backend/tests/test_verdict_classification.py](file:///D:/Documents/FakeNewsBlockChain/backend/tests/test_verdict_classification.py) | QA | Added 5 targeted test suites covering Correction 1, Group A guards, Group C temporal cases (Donald Trump, Elizabeth II, 2026 FIFA World Cup), Correction 2 M&A abstention, and Correction 4 article weighting. |

---

## 4. Independent `64`-Claim Validation Metrics

### 4.1 Per-Class Classification Report (`N = 64`)

| Verdict Class | Precision | Recall | F1-Score | Support | TP | FP | FN |
|---|---:|---:|---:|---:|---:|---:|---:|
| **`GENUINE`** | `1.0000` | `1.0000` | **`1.0000`** | 12 | 12 | 0 | 0 |
| **`FAKE`** | `1.0000` | `0.9091` | **`0.9524`** | 11 | 10 | 0 | 1 |
| **`MISLEADING`** | `1.0000` | `0.5000` | **`0.6667`** | 10 | 5 | 0 | 5 |
| **`PARTIALLY_TRUE`** | `1.0000` | `1.0000` | **`1.0000`** | 11 | 11 | 0 | 0 |
| **`UNVERIFIED`** | `0.5556` | `1.0000` | **`0.7143`** | 10 | 10 | 8 | 0 |
| **`OUTDATED`** | `1.0000` | `0.8000` | **`0.8889`** | 10 | 8 | 0 | 2 |
| **Overall / Macro** | — | — | **`0.8704` (Macro-F1)** | **64** | **56** (`87.5%`) | — | — |

### 4.2 Full `6 × 6` Confusion Matrix

| Actual \ Predicted | `GENUINE` | `FAKE` | `MISLEADING` | `PARTIALLY_TRUE` | `UNVERIFIED` | `OUTDATED` |
|---|---:|---:|---:|---:|---:|---:|
| **`GENUINE` (12)** | **12** | 0 | 0 | 0 | 0 | 0 |
| **`FAKE` (11)** | 0 | **10** | 0 | 0 | 1 | 0 |
| **`MISLEADING` (10)** | 0 | 0 | **5** | 0 | 5 | 0 |
| **`PARTIALLY_TRUE` (11)** | 0 | 0 | 0 | **11** | 0 | 0 |
| **`UNVERIFIED` (10)** | 0 | 0 | 0 | 0 | **10** | 0 |
| **`OUTDATED` (10)** | 0 | 0 | 0 | 0 | 2 | **8** |

---

## 5. Error & Conservative Abstention Audit

Zero false `GENUINE` (`0 / 64`), zero false `FAKE` (`0 / 64`), and zero other wrong-class predictions (`0 / 64`) occurred. All **8 / 64** non-matches abstained conservatively to **`UNVERIFIED`**:

1. **Claim #20 (`FAKE` -> `UNVERIFIED`):** *"Isaac Newton won three Nobel Prizes in Physics during the eighteenth century."* — Wikipedia `Isaac Newton` and `Isaac Newton (disambiguation)` intros omit the Nobel Prize (`0.22 < 0.28` overlap); safely abstained rather than misclassifying from silence.
2. **Claim #24 (`MISLEADING` -> `UNVERIFIED`):** *"The Nobel Peace Prize is presented annually in Stockholm alongside the Physics and Chemistry prizes."* — `Nobel Prize in Chemistry` local FEVER hits were blocked by the orthogonal prize subtype guard; live Wikipedia `Nobel Peace Prize` (`Oslo City Hall`) did not enter top-5 before NLI, yielding safe abstention.
3. **Claim #27 (`MISLEADING` -> `UNVERIFIED`):** *"Healthy human beings normally use only ten percent of their brains."* — Local retrieval surfaced `Cancer` / `Dementia` / `Human brain` (`'human'` absent / `< 0.28` overlap) without reaching `Ten-percent-of-the-brain myth`.
4. **Claim #28 (`MISLEADING` -> `UNVERIFIED`):** *"Only the United States has ever successfully landed a spacecraft on the Moon."* — Local `Moon landing` (`"manned missions to the Moon"`) was correctly blocked by the narrowing-scope guard (`manned` != general spacecraft) and Wikipedia `Moon` intro lacked landing agency enumeration.
5. **Claim #30 (`MISLEADING` -> `UNVERIFIED`):** *"Wright brothers built the only aircraft to fly anywhere during the entire 20th century."* — DeBERTa predicted `REFUTES` on `Wright brothers` (`1903 Wright Flyer` / `Wright Flyer II/III`), which lacked a direct normalized exclusive-slot token trigger in alignment checks.
6. **Claim #32 (`MISLEADING` -> `UNVERIFIED`):** *"Vaccines always confer permanent 100 percent lifetime immunity against every viral disease after a single dose."* — Retrieved `Measles` / `Vaccine` extracts do not explicitly state single-dose percentages (`0.14 < 0.28` overlap).
7. **Claim #61 (`OUTDATED` -> `UNVERIFIED`):** *"The NASA Space Shuttle fleet currently flies regular astronaut missions to the International Space Station."* — Sentence 0 of Wikipedia `Space Shuttle` (`"The Space Shuttle is a retired..."`) abbreviates the station as `"ISS"` and omits `"NASA"` until later sentences, causing Gate 2 to abstain on `'nasa' absent` (`0.27 < 0.30` overlap).
8. **Claim #64 (`OUTDATED` -> `UNVERIFIED`):** *"Argentina is the current reigning men's FIFA World Cup champion."* — Wikipedia search returned `Argentina at the FIFA World Cup` and `Argentina national football team` ahead of `FIFA World Cup` / `2026 FIFA World Cup` in this run, lacking `"Spain"`/`"defeating the holders, Argentina"`, whereas direct test [`test_group_c_temporal_noncontiguous_and_stale_fever_override`](file:///D:/Documents/FakeNewsBlockChain/backend/tests/test_verdict_classification.py) verified `OUTDATED` when `FIFA World Cup` lead text is retrieved.

*(Note: Claims `#24`, `#27`, `#28`, `#30`, `#32` are prime candidates to gain broader external verification coverage once Google Fact Check Tools & GDELT are integrated in Phase 2 / Group E.)*

---

## 6. Verification Suite, Frontend Build & Blockchain Integrity Checks

1. **Targeted Phase 1 Verdict & Alignment Suite (`backend/tests/test_verdict_classification.py`):**
   - Command: `.venv\Scripts\python -m pytest backend\tests\test_verdict_classification.py -v`
   - Result: **`16 passed`** (`0 failed`, `0 skipped`, `54.02s`).
2. **Full Backend Regression Suite:**
   - Command: `.venv\Scripts\python -m pytest backend\tests -v`
   - Result: **`76 passed, 2 skipped`** (`0 failed`, `177.44s`).
   - Skipped tests (expected read-only constraint): `test_wallet_balance_and_insufficient_funds_rejection` and `test_live_transaction_anchoring_and_receipt_confirmation` in [backend/tests/test_blockchain_milestone2.py](file:///D:/Documents/FakeNewsBlockChain/backend/tests/test_blockchain_milestone2.py).
3. **Frontend TypeScript & Vite Production Build:**
   - Command: `npm --prefix frontend run build` (`tsc -b && vite build`)
   - Result: **`0` errors** (`2092 modules transformed`, built in `8.10s`; zero frontend files were modified in Phase 1).
4. **Database & Sepolia Read-Only Integrity Check (After Final Edits & DB Restore):**
   - Temporary rows appended during pytest execution (`185 -> 205`) were cleanly rolled back by restoring pre-Phase-1 snapshots into `data/database/fakenews.db` (`SHA-256: 35fc2f2cc41d6b100f1d2ad81844112d9ead2c286c95f95b45fcded9aee4e38f`, `185` records) and `data/news_cache.db` (`SHA-256: 6c83243522d6f33e7944c7223401cf29359a6e425290a2ef2c35ac743d40de84`).
   - Read-only verification via `POST /api/v1/certificates/verify` for `verif-9c524ca7b6f5` returned **HTTP `200`**, `status: "MATCH"`, `is_authentic: true`, `canonical_hash == on_chain_hash == 42007960ae4bf66cbc74dfb24ef80429fdba86ca34de3bc1a8d0ff9c16a2cc53`, `contract_address: 0xcDa4CE06d44642Fd0034C817B5b7cB6AFC886ffb`, `transaction_hash: 0x8ba191c38e155af5e69c4dbf949f8eda1cf3cdb63fdb35641ced5129386f8941`, `block_number: 12076191`, `block_datetime: 2026-11-06T11:12:24+00:00`, `chain_id: 11155111`. Zero Sepolia transactions submitted; zero ETH spent.

---

## 7. Ready for Phase 2 Approval (Group E)

Phase 1 (Groups A–D) is complete and verified. Implementation is paused prior to **Phase 2 / Group E** (Google Fact Check Tools API client, GDELT DOC 2.0 verification + persistent 200-call shared SQLite quota tracker, frontend external-evidence/usage UI cards, and Group E mocked + bounded tests) awaiting your explicit review and authorization.
