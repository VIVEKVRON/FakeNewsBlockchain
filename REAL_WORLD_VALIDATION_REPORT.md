# FakeNewsBlockchain — Read-Only Real-World Validation Audit Report

**Audit Date:** 2026-11-11  
**Workspace:** `D:\Documents\FakeNewsBlockChain`  
**Audit Mode:** Strictly **Read-Only** (zero source files, database records, model weights, `.env`, certificates, or smart contract state modified; zero Sepolia ETH spent; zero unnecessary external API calls).  
**SQLite Integrity Verification (SHA-256 before == after execution):**
- `data/database/fakenews.db`: `35fc2f2cc41d6b100f1d2ad81844112d9ead2c286c95f95b45fcded9aee4e38f` (185 rows in `verification_records`, unchanged)
- `data/news_cache.db`: `6c83243522d6f33e7944c7223401cf29359a6e425290a2ef2c35ac743d40de84` (279 RSS rows in `news_articles`, unchanged)

---

## Executive Summary & Headline Findings

1. **Prior Benchmark Overfitting / Generalization Gap Confirmed:**  
   `docs/VERDICT_CLASSIFICATION_AUDIT.md` and `scratch/verdict_benchmark_results.json` report **23/23 (100.0%, Macro F1 = 1.0000)** solely on 23 author-curated claims tightly coupled to alignment heuristics tuned during development. When evaluated against **26 previously unused, independent real-world English claims**, end-to-end accuracy fell to **13/26 (50.0%)** with **Macro F1 = 0.4516**.
2. **Critical Safety & Certainty Failures Observed:**
   - **False Positives as `GENUINE` (6 cases, Precision = 0.4000):** Three compound mixed-truth claims (`#14`, `#15`, `#17`), one geographic venue conflation (`#11`, Nobel Peace Prize in Stockholm, `conf = 0.86`), and two outdated claims (`#22` Queen Elizabeth II `conf = 0.92`; `#24` Facebook Inc. `conf = 0.86`) were certified as `GENUINE`.
   - **Compound Claim Splitter Collapse (`PARTIALLY_TRUE` Recall = 0/4 = 0.0%):** `split_compound_claims()` failed to split all 4 compound claims (`#14–#17`) because its hardcoded 34-verb whitelist excluded common verbs (`"lies"`, `"allows"`, `"released"`, `"connects"`).
   - **Temporal Reasoning Failures (`#22`, `#24`, `#26`):** Stale 2017 FEVER leads falsely blocked 2026 `OUTDATED` detection for Queen Elizabeth II (`GENUINE 0.92`), while non-contiguous tenure wording (`"45th and current 47th president"`, `"2017–2021, 2025–present"`) misclassified sitting US President Donald Trump as `OUTDATED` (`conf = 0.83`).
3. **External API Integrations Not Yet Built (Google Fact Check & GDELT Verification):**  
   Despite `.env` containing `GOOGLE_FACT_CHECK_API_KEY`, `GDELT_ENABLED`, `GDELT_REQUEST_LIMIT`, and `GDELT_WARNING_THRESHOLD`, **neither Google Fact Check Tools API nor GDELT verification/budget tracking/caching is implemented in application code**. Only Live News Monitor (`_ingest_gdelt_source`) calls GDELT DOC 2.0, uncounted and uncached.
4. **Sepolia Discrepancy Forensically Resolved:**  
   Transaction `0x7147d07d8b3545345721d6d4765ac5f2679e8d3d4a2d558a5410e9e024ed450b` **does not exist on Sepolia** (`TransactionNotFound`); it originated from an LLM-hallucinated `<SYSTEM_MESSAGE>` block at transcript line 2864. Transaction **`0x8ba191c38e155af5e69c4dbf949f8eda1cf3cdb63fdb35641ced5129386f8941`** is the **authentic Sepolia anchor** at block **`12076191`**, matching SQLite and recomputed SHA-256 (`42007960ae4bf66cbc74dfb24ef80429fdba86ca34de3bc1a8d0ff9c16a2cc53`).
5. **Wikipedia Fallback Failure Handling:**  
   Simulated `Timeout`, `ConnectionError`, and `HTTP 500` errors on post-2017 claims safely degraded to `UNVERIFIED` (`confidence = 0.22`) using local FEVER only, without exceptions or fabricated evidence.

---

## 1. Audit of Existing Benchmark (`docs/VERDICT_CLASSIFICATION_AUDIT.md` & `scratch/verdict_benchmark_results.json`)

- **Reused Benchmark Confirmation (Objective 2):** Inspection of `docs/`, `backend/tests/`, and `scratch/` confirmed `scratch/run_verdict_benchmark.py` (23 claims) is the **only** quantitative multi-class benchmark referenced in `docs/VERDICT_CLASSIFICATION_AUDIT.md`.
- **Why 23/23 Did Not Predict General Accuracy:**
  - Repeated entities across multiple benchmark items (`19 Kids and Counting` / `Duggar` x6, `Apollo 11` / `Neil Armstrong` x4, `Albert Einstein` x2, `Barack Obama` x2).
  - Structural triggers in `ml/inference/evidence_alignment.py` and `ml/inference/verdict_synthesizer.py` directly mirrored phrasing inside those 23 claims (e.g., `"exclusively has daughters"`, `"only astronaut"`, `"aired on HBO"`, `"first President of the United States"`, `"bacterial"` vs `"coronavirus"`, exact verbs in `finite_verb_pattern`).
  - While `docs/VERDICT_CLASSIFICATION_AUDIT.md` noted that unconstrained production accuracy would be lower than 100%, relying primarily on a 23-case development-aligned benchmark hid severe real-world failure modes quantified below.

---

## 2. Independent 26-Claim Validation Methodology (Objectives 3–6)

### Test Design
- **Isolation Guarantee:** Evaluation ran strictly in-memory (`VerificationService._evaluate_single_claim`, `split_compound_claims`, `_aggregate_multi_claim_verdicts`) without calling `save_verification_record()` or `Live News` endpoints. Zero entities or claims overlapped `scratch/run_verdict_benchmark.py`.
- **Temporal & Linguistic Coverage (26 Claims):**
  - `GENUINE` (6): Paraphrased historical (`#1`), recent 2022–2023 space/AI/royalty (`#2`, `#3`, `#4`), direct geography (`#5`), plus a non-contiguous current-office stress test (`#26`, `"Donald Trump is the current President of the United States"` as of `2026-11-11`).
  - `FAKE` (4): Biomedical misinformation (`#6`), false historical end date (`#7`), non-US false ordinal officeholder (`#8`), fabricated 2023 corporate M&A rumor (`#9`).
  - `MISLEADING` (4): Sweeping biological quantifier (`#10`), Nobel venue conflation (`#11`), 10%-brain neuromyth (`#12`), sole-founder omission (`#13`).
  - `PARTIALLY_TRUE` (4): Compound true+false geography (`#14`), science (`#15`), recent 2022/2023 events (`#16`), true+outdated politics (`#17`).
  - `UNVERIFIED` (4): Unsubstantiated Oct 2026 EU tax (`#18`), unrecorded private meeting (`#19`), speculative climate number (`#20`), obscure local 2026 city statistic (`#21`).
  - `OUTDATED` (4): Expired 2022 monarch (`#22`), 2021 chancellor (`#23`), 2021 corporate parent rename (`#24`), 2024 UK PM transition (`#25`).
- **Independent Source Verification:** Reference article URLs and live revision timestamps were retrieved independently from `https://en.wikipedia.org/w/api.php` (`task-2934` and `task-2955`). Note: sequential Wikipedia reference queries in `task-2955` hit transient empty-body responses (`Expecting value: line 1 column 1 (char 0)`) after ~13 calls, illustrating upstream rate sensitivity.

---

## 3. Quantitative Metrics & 6x6 Confusion Matrix

- **Total Independent Claims Evaluated:** `26`
- **Correct Predictions:** `13 / 26` (**50.0%**)
- **Macro F1 Score:** **0.4516**

### Per-Class Classification Metrics

| Verdict Class | Support | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `GENUINE` | 6 | 4 | 6 | 2 | 0.4000 | 0.6667 | 0.5000 |
| `FAKE` | 4 | 2 | 0 | 2 | 1.0000 | 0.5000 | 0.6667 |
| `MISLEADING` | 4 | 1 | 0 | 3 | 1.0000 | 0.2500 | 0.4000 |
| `PARTIALLY_TRUE` | 4 | 0 | 0 | 4 | 0.0000 | 0.0000 | 0.0000 |
| `UNVERIFIED` | 4 | 4 | 6 | 0 | 0.4000 | 1.0000 | 0.5714 |
| `OUTDATED` | 4 | 2 | 1 | 2 | 0.6667 | 0.5000 | 0.5714 |

### 6x6 Confusion Matrix (Rows = Expected, Columns = Actual)

| Expected \ Actual | `GENUINE` | `FAKE` | `MISLEADING` | `PARTIALLY_TRUE` | `UNVERIFIED` | `OUTDATED` |
|---|---:|---:|---:|---:|---:|---:|
| **`GENUINE`** | **4** | 0 | 0 | 0 | 1 | 1 |
| **`FAKE`** | 0 | **2** | 0 | 0 | 2 | 0 |
| **`MISLEADING`** | 1 | 0 | **1** | 0 | 2 | 0 |
| **`PARTIALLY_TRUE`** | 3 | 0 | 0 | **0** | 1 | 0 |
| **`UNVERIFIED`** | 0 | 0 | 0 | 0 | **4** | 0 |
| **`OUTDATED`** | 2 | 0 | 0 | 0 | 0 | **2** |

---

## 4. Complete Per-Claim Audit Results (26 Independent Claims)

All retrieved values below come verbatim from `rw_validation_results.json`. NLI probabilities reflect uncalibrated DeBERTa logits (`raw_supports / raw_refutes / raw_nei`), paired with calibrated NLI labels after `evaluate_evidence_alignment()`.

### 4.1 `GENUINE` Test Cases (`#01–#05`, `#26`)

| # | Claim & Type | Expected / Justification (Independent URL & Rev. Date) | Actual (Conf.) | Top Retrieved Evidence, Dates & NLI Scores (`S / R / NEI` -> Calibrated) | Alignment Decision & Justification Assessment |
|---:|---|---|---:|---|---|
| **1** | `Marie Curie earned Nobel Prizes in both Physics and Chemistry.` *(paraphrased historical)* | **GENUINE** — Won 1903 Physics & 1911 Chemistry prizes. [Marie Curie](https://en.wikipedia.org/wiki/Marie_Curie) (rev `2026-11-10T08:32:32Z`) | **GENUINE** (`0.89`) | #1 `fever_local` (`2017-06`, [Marie Curie](https://en.wikipedia.org/wiki/Marie_Curie), sim `0.7598`): *"She won the 1911 Nobel Prize in Chemistry."* `0.998/0.002/0.0` -> `SUPPORTS`; #2 (sim `0.7534`): 1903 Physics `0.998/0.002/0.0` -> `SUPPORTS` | `#4–#5` on `Nobel Prize in Chemistry` blocked (`subject 'marie' absent`). `#1–#3` aligned. **Justified PASS.** |
| **2** | `India's Chandrayaan-3 spacecraft landed near the Moon's south pole in August 2023.` *(recent 2023)* | **GENUINE** — Landed 23 Aug 2023 near lunar south pole. [Chandrayaan-3](https://en.wikipedia.org/wiki/Chandrayaan-3) (rev `2026-11-10T06:24:58Z`) | **GENUINE** (`0.93`) | #1 `wikipedia_live` `Pragyan (Chandrayaan-3)` (`2026-08-08T19:50:41Z`, sim `0.8362`): `0.9991/0.0009/0.0` -> `NEI` (`'india' absent`); #2 `Chandrayaan programme` (`2026-08-07T14:25:14Z`, sim `0.8358`, [link](https://en.wikipedia.org/wiki/Chandrayaan_programme)): `0.9991/0.0009/0.0` -> `SUPPORTS` | Note brittleness: `Pragyan` & `Chandrayaan-3` (#1, #3, #4) were rejected only because `india` came before `chandrayaan` in `extract_subject_entities()`. #2 saved it (`making India the first nation...`). **Justified PASS (fragile entity order).** |
| **3** | `OpenAI launched the conversational chatbot ChatGPT in November 2022.` *(recent 2022)* | **GENUINE** — Released Nov 30, 2022 by OpenAI. [ChatGPT](https://en.wikipedia.org/wiki/ChatGPT) (rev `2026-11-11T00:36:59Z`) | **UNVERIFIED** (`0.39`) | #1 `ChatGPT` (`2026-11-11T00:36:59Z`, sim `0.7770`): *"ChatGPT is a generative AI chatbot developed by OpenAI."* `0.0128/0.9872/0.0` -> `NEI`; #2-#3 `GPT-4o` (2026); #4 `Chatbot` (`'openai' absent`); #5 `ChatGPT Atlas` | **FALSE NEGATIVE.** `GPT-4o` consumed 2 live Wikipedia slots (`max 2 per page`) and crowded out `ChatGPT` sentence #2 (*"Originally released on November 30, 2022..."*). Safe abstention worked, retrieval failed. |
| **4** | `King Charles III acceded to the British throne in September 2022.` *(recent 2022)* | **GENUINE** — Acceded 8 Sept 2022. [Charles III](https://en.wikipedia.org/wiki/Charles_III) (rev `2026-11-07T22:23:25Z`) | **GENUINE** (`0.90`) | #1 `wikipedia_live` `Style of the British sovereign` (`2026-10-17T15:23:22Z`, sim `0.7743`): `0.9944/0.0056/0.0` -> `SUPPORTS`; #4 `List of British monarchs` (`2026-10-12T02:20:24Z`, sim `0.6696`): *"acceded to the throne in September 2022"* -> `SUPPORTS` | Live Wikipedia corroborated across 4 sentences (`king` matched lead token); `#2` omitted date so safely downgraded to `NEI`. **Justified PASS.** |
| **5** | `The Amazon River flows through South America into the Atlantic Ocean.` *(direct geography)* | **GENUINE** — Flows across South America to Atlantic. [Amazon River](https://en.wikipedia.org/wiki/Amazon_River) (rev `2026-11-05T17:41:41Z`) | **GENUINE** (`0.90`) | #1 `fever_local` `Amazon River` (`2017-06`, sim `0.7785`): *"The Amazon enters Brazil... discharges into the Atlantic Ocean..."* `0.9979/0.0021/0.0` -> `SUPPORTS`; #2 `Amazon basin`: `0.9974/0.0026/0.0` -> `SUPPORTS` | Clean subject & predicate alignment across 5 local FEVER sentences. **Justified PASS.** |
| **26** | `Donald Trump is the current President of the United States.` *(temporal non-contiguous office)* | **GENUINE** — 45th president (2017–2021) and **47th and current president** (2025–present). [Donald Trump](https://en.wikipedia.org/wiki/Donald_Trump) (rev `2026-11-10T23:58:17Z`) | **OUTDATED** (`0.83`) | #1 `fever_local` (`2017-06`, sim `0.7673`): *"45th president"* `SUPPORTS`; #2 `Donald Trump` (`2026-11-10T23:58:17Z`, sim `0.7250`): *"is the 47th president"* `0.997/0.003/0.0`; #3 `Trump family` (`2026-11-09T20:49:15Z`, sim `0.7237`): *"(2017–2021, 2025–present)"*; #4 `Second presidency...`: *"from 2017 to 2021"* `SUPPORTS` | **CRITICAL FALSE NEGATIVE / MISCLASSIFICATION (`0.83` certainty).** `_has_active_current_tenure()` regex (`r"\b(is (the )?(current\|incumbent)\|"`) failed to match `"is the 47th president"` or `"current 47th president (2017–2021, 2025–present)"`, while `from 2017 to 2021` triggered `OUTDATED`! |

### 4.2 `FAKE` Test Cases (`#06–#09`)

| # | Claim & Type | Expected / Justification (Independent URL & Rev. Date) | Actual (Conf.) | Top Retrieved Evidence, Dates & NLI Scores (`S / R / NEI` -> Calibrated) | Alignment Decision & Justification Assessment |
|---:|---|---|---:|---|---|
| **6** | `Antibiotics can cure viral illnesses such as the common cold.` *(biomedical misinfo)* | **FAKE** — Antibiotics target bacteria only, ineffective against viruses/common cold. [Antibiotic](https://en.wikipedia.org/wiki/Antibiotic) (rev `2026-11-05T16:27:23Z`) | **UNVERIFIED** (`0.33`) | #1 `fever_local` `Lyme disease` (sim `0.6620`): *"antibiotics are effective..."* `0.9981/0.0019/0.0` -> `NEI` (overlap `0.14`); #3 `Measles` (sim `0.6439`): *"bacterial infection"* `0.9584/0.0416/0.0` -> `NEI`; #4 `Common cold` (sim `0.6823`): *"No cure for the common cold exists"* `0.0029/0.9971/0.0` -> `NEI` (`'antibiotics'` absent) | **FALSE NEGATIVE.** Local FEVER sim `0.662 >= 0.62` suppressed Wikipedia fallback to `Antibiotic`. Multi-hop relation (`antibiotic` -> `antibacterial` vs `viral`) undetected. |
| **7** | `World War II concluded in September 1955 following Japan's surrender.` *(historical date error)* | **FAKE** — Concluded 2 September 1945. [World War II](https://en.wikipedia.org/wiki/World_War_II) (rev `2026-11-10T01:56:48Z`) | **FAKE** (`0.83`) | #1 `Atomic bombings...` (`2017-06`, sim `0.7145`): `0.1511/0.8489/0.0` -> `NEI` (no year in sentence); #3 `Japan` (`2017-06`, sim `0.6203`, [link](https://en.wikipedia.org/wiki/Japan)): *"came to an end in 1945 following... Japanese surrender"* `0.0043/0.9957/0.0` -> `REFUTES` | `has_numeric_conflict` (`1955` vs `1945`) + entity `'world'`/`'japan'` properly triggered `REFUTES`. Note `#1/#2` were safely held at `NEI` when year was omitted. **Justified PASS.** |
| **8** | `Mahatma Gandhi served as the first Prime Minister of India.` *(non-US false ordinal office)* | **FAKE** — First PM of India was Jawaharlal Nehru (1947–1964). [Jawaharlal Nehru](https://en.wikipedia.org/wiki/Jawaharlal_Nehru) (rev `2026-11-07T18:35:20Z`) | **FAKE** (`0.84`) | #1 `wikipedia_live` `List of prime ministers of India` (`2026-10-09`, sim `0.8224`) -> `NEI` (`GENERIC_POLITY_PAGES`? no, title capitalization `'p'` vs exact phrase); #5 `fever_local` `Jawaharlal Nehru` (sim `0.6433`): *"was the first Prime Minister of India"* `0.0039/0.9961/0.0` -> `REFUTES` | Wait: inspect **#4 (`Indira Gandhi`)**: `raw_supports=0.7767, raw_refutes=0.2233` flipped to **`REFUTES`** (`"Claim numbers/dates or mutually exclusive attributes conflict with evidence"`) ONLY because `"the first prime minister of India"` matched `ordinal_holder_conflict` (`mahatma` absent)! Even though outcome `FAKE` was right via `#5`, `#4` matched `'gandhi'` / `'first prime minister of india'` accidentally on Indira Gandhi. **Outcome PASS, #4 noisy match.** |
| **9** | `Apple acquired Tesla Motors for 500 billion dollars in 2023.` *(fabricated M&A rumor)* | **FAKE** *(benchmark target; actually borderline `UNVERIFIED` under encyclopedic NLI)* — Never occurred. [Apple Inc.](https://en.wikipedia.org/wiki/Apple_Inc.) (rev `2026-11-10T06:54:27Z`) | **UNVERIFIED** (`0.35`) | #1 `Tesla, Inc.` (`2026-11-07T21:16:33Z`, sim `0.6915`): valuation sentence -> `NEI` (`'apple' absent`); #2-#4 `Apple Inc.` -> `NEI` (`overlap 0.12 < 0.30`); #5 `IPhone` -> `NEI` | **SAFE ABSTENTION (Not an error in epistemic terms, FAIL vs `FAKE` label).** Wikipedia articles do not enumerate events that did not occur; returning `UNVERIFIED` instead of hallucinating `REFUTES` is safer without GDELT/fact-check archives. |

### 4.3 `MISLEADING` Test Cases (`#10–#13`)

| # | Claim & Type | Expected / Justification (Independent URL & Rev. Date) | Actual (Conf.) | Top Retrieved Evidence, Dates & NLI Scores (`S / R / NEI` -> Calibrated) | Alignment Decision & Justification Assessment |
|---:|---|---|---:|---|---|
| **10** | `All penguin species live exclusively in Antarctica.` *(sweeping quantifier)* | **MISLEADING** — Only ~2–4 species breed solely in Antarctica/sub-Antarctic; Galapagos penguin lives north of equator. [Penguin](https://en.wikipedia.org/wiki/Penguin) (rev `2026-10-19T16:06:18Z`) | **UNVERIFIED** (`0.31`) | #1 `Reptile` (`2017-06`, sim `0.6296`): `0.001/0.999/0.0` -> `NEI` (`overlap 0.17`); #2 `Antarctica` (sim `0.5923`): *"animals, such as... penguins"* `0.0013/0.9987/0.0` -> `NEI`; #3 `Spider`, #4 `Greenland`, #5 `Rodent` | **FALSE NEGATIVE.** Local FAISS matched `"Antarctica"` (`0.6296 >= 0.62`), preventing live Wikipedia fallback to `Penguin`, and `extract_subject_entities()` skipped `"penguin"` (lowercase) picking `'antarctica'`! |
| **11** | `The Nobel Peace Prize is awarded annually in Stockholm alongside the Nobel Prize in Physics.` *(venue conflation)* | **MISLEADING** — Nobel Peace Prize is awarded in Oslo, Norway; Physics/Chemistry/Medicine/Literature are awarded in Stockholm. [Nobel Peace Prize](https://en.wikipedia.org/wiki/Nobel_Peace_Prize) (rev `2026-11-07T07:57:52Z`) | **GENUINE** (`0.86`) | #1 `fever_local` `Nobel Prize in Chemistry` (sim `0.6962`): *"The award is presented in Stockholm at an annual ceremony on December 10..."* `0.9956/0.0044/0.0` -> **`SUPPORTS`**; #2 `Nobel Peace Prize` (sim `0.5859`): *"Nobel Peace Prize is one of the five..."* -> `SUPPORTS` | **CRITICAL FALSE POSITIVE (`GENUINE 0.86`) / INAPPROPRIATE CERTAINTY.** Because `'nobel'` appeared in `'Nobel Prize in Chemistry'`, Gate 2 allowed Stockholm's **Chemistry** ceremony sentence to certify where the **Peace** Prize is awarded, without fetching the `Nobel Peace Prize` Oslo sentence! |
| **12** | `Human beings normally use only ten percent of their brains.` *(neuromyth)* | **MISLEADING** — Scientific consensus refutes 10% myth; humans use virtually entire brain. [Ten-percent-of-the-brain myth](https://en.wikipedia.org/wiki/Ten-percent-of-the-brain_myth) (rev `2026-11-07T00:19:19Z`) | **UNVERIFIED** (`0.25`) | #1-#4 `fever_local` `Brain`/`Human brain` (sim `0.45–0.50`, `raw_refutes=0.997–0.998` -> `NEI`, overlap `0.25`); #5 `wikipedia_live` `Human` (sim `0.4492 < 0.45`) | **FALSE NEGATIVE.** Query builder searched `"Human"` instead of `"ten percent brain"`, missing `Ten-percent-of-the-brain myth`. Safe abstention avoided false `FAKE`/`GENUINE`. |
| **13** | `Steve Jobs was the sole founder of Apple Computer.` *(sole founder omission)* | **MISLEADING** — Founded by Steve Jobs, Steve Wozniak, and Ronald Wayne. [Apple Inc.](https://en.wikipedia.org/wiki/Apple_Inc.) (rev `2026-11-10T06:54:27Z`) | **MISLEADING** (`0.72`) | #1 `Steve Wozniak` (`2017-06`, sim `0.8573`): *"along with Apple co-founder Steve Jobs"* `0.0025/0.9975/0.0` -> `REFUTES` *(overlap >= 0.78 / entity matched?)*; #2 `Apple Inc.` (sim `0.8348`): *"founded by Steve Jobs, Steve Wozniak, and Ronald Wayne"* -> `NEI`! | **FRAGILE PASS.** Look at #1 vs #2: `#2` (`founded by Steve Jobs, Steve Wozniak, and Ronald Wayne`) actually went to `NEI` because singleton-vs-multiplicity only checked numeric words (`two/three`) rather than comma-listed co-founders, while `#1` (`co-founder` + high overlap) passed and `ABS` `"sole"` -> `MISLEADING`. Notice also #4 `Steve Jobs (film)` wrongly tripped `REFUTES` due to `'apple'`/`'computer'`/`overlap`! |

### 4.4 `PARTIALLY_TRUE` Test Cases (`#14–#17`)

| # | Claim & Type | Expected / Justification (Independent URL & Rev. Date) | Actual (Conf.) | Sub-Claims Split & Top Evidence / NLI | Alignment Decision & Failure Analysis |
|---:|---|---|---:|---|---|
| **14** | `Tokyo is the capital city of Japan, and Mount Everest lies inside Brazil.` *(compound geo mix)* | **PARTIALLY_TRUE** — Tokyo is Japan's capital ([Tokyo](https://en.wikipedia.org/wiki/Tokyo), rev `2026-11-08T14:18:28Z`); Everest is on Nepal–China border ([Mount Everest](https://en.wikipedia.org/wiki/Mount_Everest), rev `2026-11-08T06:59:35Z`). | **GENUINE** (`0.78`) | **Did NOT split** (`sub_claims = [full claim]`). #2 `Tokyo` (`2017-06`, sim `0.5128`): `0.9989/0.0011/0.0` -> `SUPPORTS`; #4 `Japan`: `0.9994/0.0006/0.0` -> `SUPPORTS` | **CRITICAL FALSE POSITIVE (`GENUINE 0.78`).** Clause 2 (`Mount Everest lies inside Brazil`) lacks any verb in `split_compound_claims`'s closed whitelist (`"lies"` omitted), so the entire compound sentence ran against `Tokyo` only! |
| **15** | `Photosynthesis allows plants to convert sunlight into chemical energy, while Jupiter is the smallest planet in the Solar System.` *(compound science mix)* | **PARTIALLY_TRUE** — Photosynthesis true ([Photosynthesis](https://en.wikipedia.org/wiki/Photosynthesis), rev `2026-11-01T19:09:13Z`); Jupiter is *largest*, Mercury is smallest ([Jupiter](https://en.wikipedia.org/wiki/Jupiter), rev `2026-11-08T22:57:59Z`). | **GENUINE** (`0.82`) | **Did NOT split.** #1 `Sunlight` (`2026-11-07T23:44:26Z`, sim `0.6102`): `0.9985/0.0015/0.0` -> `SUPPORTS`; #2 `Jupiter` (`2017-06`, sim `0.6027`): `0.0043/0.9957/0.0` -> **`NEI`** (`'photosynthesis' absent`) | **CRITICAL FALSE POSITIVE (`GENUINE 0.82`).** `"allows"`/`"convert"` absent from whitelist prevented splitting; then Gate 2 rejected `Jupiter`'s explicit refutation sentence (*"largest in the Solar System"*) because `'photosynthesis'` was the primary entity! |
| **16** | `OpenAI released ChatGPT in November 2022, and Chandrayaan-3 landed on Venus in 2023.` *(compound recent mix)* | **PARTIALLY_TRUE** — ChatGPT Nov 2022 true ([ChatGPT](https://en.wikipedia.org/wiki/ChatGPT)); Chandrayaan-3 landed on Moon, not Venus ([Chandrayaan-3](https://en.wikipedia.org/wiki/Chandrayaan-3)). | **UNVERIFIED** (`0.24`) | **Did NOT split.** Retrieved `ChatGPT` (`0.4847`), `Venus Williams` (`0.479`), `Venus` (`0.4748`), `2023 in science` (`0.4665`) -> all `NEI` | **FALSE NEGATIVE (`UNVERIFIED`).** `"released"` missing from `finite_verb_pattern` prevented splitting, muddying retrieval into 12-token mixed query (`Venus Williams`). |
| **17** | `The Suez Canal connects the Mediterranean Sea to the Red Sea, whereas Angela Merkel is the current Chancellor of Germany.` *(compound outdated mix)* | **PARTIALLY_TRUE** — Suez Canal true ([Suez Canal](https://en.wikipedia.org/wiki/Suez_Canal), rev `2026-11-08T13:28:15Z`); Merkel left office in 2021 ([Angela Merkel](https://en.wikipedia.org/wiki/Angela_Merkel), rev `2026-10-29T10:57:45Z`). | **GENUINE** (`0.79`) | **Did NOT split.** #2 `Suez Canal` (`2026-11-08T13:28:15Z`, sim `0.5395`): `0.9954/0.0046/0.0` -> `SUPPORTS`; #3 `Suez`, #4 `Mediterranean Sea` -> `SUPPORTS` | **CRITICAL FALSE POSITIVE (`GENUINE 0.79`).** `"connects"` missing from `finite_verb_pattern` prevented splitting on `, whereas `, letting Suez Canal certify an outdated political claim as `GENUINE`! |

### 4.5 `UNVERIFIED` Test Cases (`#18–#21`)

| # | Claim & Type | Expected / Justification (Independent URL & Rev. Date) | Actual (Conf.) | Top Retrieved Evidence, Dates & NLI Scores (`S / R / NEI` -> Calibrated) | Alignment Decision & Justification Assessment |
|---:|---|---|---:|---|---|
| **18** | `The European Union enacted a binding 40 percent global wealth tax on billionaires in October 2026.` *(recent fabricated policy)* | **UNVERIFIED** — No encyclopedic/fact-check/news corroboration retrieved. | **UNVERIFIED** (`0.22`) | #1 `Fortune Global 500` (`0.4486 < 0.45`, `0.0066/0.9934/0.0` -> `NEI`); #2 `Lisbon` (`0.4402 < 0.45`); #3-#5 `< 0.45` | **Justified PASS.** Gate 1 similarity threshold `< 0.45` blocked all 5 raw `REFUTES > 0.98` DeBERTa predictions cleanly. |
| **19** | `Sundar Pichai secretly met NASA engineers in Bengaluru on June 12, 2025.` *(unrecorded private meeting)* | **UNVERIFIED** — Public bio confirms Pichai/Google CEO; no record of any Bengaluru meeting. [Sundar Pichai](https://en.wikipedia.org/wiki/Sundar_Pichai) (rev `2026-11-01T19:06:06Z`) | **UNVERIFIED** (`0.26`) | #1 `Sundar Pichai` (`2017-06`, sim `0.5119`): `0.0038/0.9962/0.0` -> `NEI`; #2 `Sundar Pichai` (`2026-11-01`, sim `0.4849`): `0.0055/0.9945/0.0` -> `NEI`; #3-#5 `< 0.45` | **Justified PASS.** Note DeBERTa raw `REFUTES > 0.99` on non-contradictory biography lines; Gate 4 properly abstained to `NEI`. |
| **20** | `A leaked United Nations report predicts ocean levels will rise 4.2 meters by 2040.` *(speculative forecast)* | **UNVERIFIED** — Sea level rise records do not substantiate a 4.2 m by 2040 forecast. [Sea level rise](https://en.wikipedia.org/wiki/Sea_level_rise) (rev `2026-11-09T02:39:00Z`) | **UNVERIFIED** (`0.29`) | #1 `Pacific Ocean` (`2026-11-09`, sim `0.5820`): `0.0157/0.9843/0.0` -> `NEI`; #2 `Dead Sea`, #3 `Global warming` (`2017-06`) -> `NEI` | Notice `primary_ent` extracted `'nations'` (`United` in `NON_SUBJECT_PROPER_MODIFIERS`), which worked safely here, though `#3` missed `Sea level rise` page. **Outcome PASS.** |
| **21** | `Over 83 percent of households in Pune installed rooftop solar panels in 2026.` *(obscure local stat)* | **UNVERIFIED** — No statistical coverage in FEVER or Wikipedia leads. [Pune](https://en.wikipedia.org/wiki/Pune) (rev `2026-11-07T11:18:18Z`) | **UNVERIFIED** (`0.27`) | #1 `Pune` (`2026-11-07`, sim `0.5388`): `0.0066/0.9934/0.0` -> `NEI`; #2 `Solar power in India` (`2026-10-14`, sim `0.5321`): **`0.9786/0.0213/0.0`**! | Notice #2 (`Solar power in India`: *"171.05 GWAC"*) had `raw_supports = 0.9786`! Only prevented from falsely certifying `GENUINE` because `'over'`/`pune` Gate 2 check (though note bug: `'over'` wasn't in `GENERIC_INITIAL_WORDS`, so `'over'` acted as `primary_ent`!). **Outcome PASS, entity extraction bug exposed.** |

### 4.6 `OUTDATED` Test Cases (`#22–#25`)

| # | Claim & Type | Expected / Justification (Independent URL & Rev. Date) | Actual (Conf.) | Top Retrieved Evidence, Dates & NLI Scores (`S / R / NEI` -> Calibrated) | Alignment Decision & Justification Assessment |
|---:|---|---|---:|---|---|
| **22** | `Queen Elizabeth II is the current reigning monarch of the United Kingdom.` *(expired monarch 2022)* | **OUTDATED** — Died 8 Sept 2022; reigned 1952–2022. [Elizabeth II](https://en.wikipedia.org/wiki/Elizabeth_II) (rev `2026-11-10T16:51:29Z`) | **GENUINE** (`0.92`) | #1 `fever_local` (`2017-06`) `Current reigning monarchs...` (sim `0.8226`): *"is the current longest-reigning monarch"* `0.9991` -> `SUPPORTS`; #2 `Lord of Mann` (`2017-06`): *"current holder... Elizabeth II"* `0.9994` -> `SUPPORTS`; #3 `wikipedia_live` `Elizabeth II` (`2026-11-10`, sim `0.7836`): *"was Queen... until her death in 2022."* | **CRITICAL FALSE POSITIVE (`GENUINE 0.92`).** Dual root cause: (1) stale `2017-06` FEVER entries matched `_has_active_current_tenure()`, blocking `OUTDATED` even in the presence of live `2026-11-10` Wikipedia evidence of death; (2) `"until her death in 2022"` lacked match in `HISTORICAL_END_PATTERNS`. |
| **23** | `Angela Merkel is the incumbent Chancellor of Germany.` *(expired chancellor 2021)* | **OUTDATED** — Served 2005–2021, retired. [Angela Merkel](https://en.wikipedia.org/wiki/Angela_Merkel) (rev `2026-10-29T10:57:45Z`) | **OUTDATED** (`0.89`) | #1 `wikipedia_live` `Angela Merkel` (`2026-10-29`, sim `0.8668`): *"retired politician who served as Chancellor of Germany from 2005 to 2021."* `0.9901/0.0099/0.0`; #2 `Family of Angela Merkel` (`0.0085/0.9915/0.0`) -> `REFUTES` | Correctly detected `from 2005 to 2021` + `chancellor` role match with no active-tenure override. **Justified PASS.** |
| **24** | `Facebook, Inc. is the current official corporate parent name of Mark Zuckerberg's social media company.` *(rebrand Oct 2021)* | **OUTDATED** — Rebranded to Meta Platforms, Inc. [Meta Platforms](https://en.wikipedia.org/wiki/Meta_Platforms) (rev `2026-11-09T13:41:26Z`) | **GENUINE** (`0.86`) | #1 `wikipedia_live` `Mark Zuckerberg` (`2026-11-07`, sim `0.7804`): *"co-founded... Facebook and its parent company Meta Platforms."* `0.0037/0.9963/0.0` -> `NEI`; #2 `Mark S. Zuckerberg`, #3 `List of Facebook features`, #4-#5 `fever_local` (`SUPPORTS 0.95–0.98`) | **CRITICAL FALSE POSITIVE (`GENUINE 0.86`).** Never queried `"Meta Platforms"` or `"Facebook, Inc."`; `"Mark Zuckerberg"` bio mentions `"parent company Meta Platforms"` without `"formerly"`, while peripheral/namesake pages (`Mark S. Zuckerberg`!) matched `Mark`+`Zuckerberg`+`Facebook` and voted `SUPPORTS`! |
| **25** | `Rishi Sunak is the current Prime Minister of the United Kingdom.` *(UK PM transition July 2024)* | **OUTDATED** — Served Oct 2022 – July 2024. [Rishi Sunak](https://en.wikipedia.org/wiki/Rishi_Sunak) (rev `2026-10-26T12:33:05Z`) | **OUTDATED** (`0.90`) | #1 `wikipedia_live` `Rishi Sunak` (`2026-10-26`, sim `0.8800`): *"served as Prime Minister... from 2022 to 2024."* `0.9895`; #2 `Premiership of Rishi Sunak` (`2026-09-13`, sim `0.7701`): *"ended on 5 July 2024"* | Strong live Wikipedia match (`from 2022 to 2024` + `ended on 5 July 2024`). **Justified PASS.** |

---

## 5. Additional Checks: Article Aggregation, DeBERTa NEI Head, and Failure Modes

### 5.1 Article-Level Aggregation Policy Check (Objective 5 / Prompt Sec. 7)
Running `_aggregate_multi_claim_verdicts` read-only on two 4-claim mixed articles confirmed the current aggregation limitation:
- **Test A (`3_genuine_1_minor_unverified`):** Constituent claims evaluated to `['GENUINE', 'GENUINE', 'UNVERIFIED', 'UNVERIFIED']` (ChatGPT missed due to retrieval crowding; Pune stat legitimately unverified). Overall verdict: **`UNVERIFIED` (`0.61`)**. Code inspection at [`verification_service.py`](file:///D:/Documents/FakeNewsBlockChain/backend/app/services/verification_service.py#L176-L189) confirms *any* `n_genuine > 0 and n_unverified > 0` hard-forces `UNVERIFIED`, so even **3 supported central claims + 1 minor unverified background sentence cannot return `GENUINE`**.
- **Test B (`3_genuine_1_minor_refuted`):** Constituent claims evaluated to `['GENUINE', 'GENUINE', 'UNVERIFIED', 'FAKE']`. Overall verdict: **`PARTIALLY_TRUE` (`0.75`)**. Note there is no weighting between central high-rank claims (`relevance_rank=1`) and peripheral minor sentences (`relevance_rank=3+`).

### 5.2 DeBERTa `NOT ENOUGH INFO` Collapse Status
- Raw NLI probabilities in all 26 claims confirmed that `Requirements/fever_verifier_v1` **still outputs `raw_nei = 0.0` (or `0.0001–0.0005`) across virtually every tested claim-evidence pair** (e.g., `#03` ChatGPT `0.0128/0.9872/0.0`; `#18` EU wealth tax `0.0066/0.9934/0.0`; `#19` Sundar Pichai `0.0038/0.9962/0.0`; `#21` Pune solar `0.0066/0.9934/0.0`).
- Preserving existing weights means the `logit[2]` head itself is **not repaired**; abstinence depends completely on the symbolic/similarity gates in `evidence_alignment.py`.

### 5.3 Wikipedia Fallback Failure Handling (Objective 8)
Tested in-memory using `unittest.mock.patch` on `WikipediaFallbackClient` with a post-2017 claim absent from the 2017 FEVER index (`"India's Aditya-L1 solar observatory launched in September 2023."`):

| Simulated Failure Mode | `wiki.last_status` | Returned Verdict | Confidence | Behavior Verified |
|---|---|---|---:|---|
| `requests.Timeout` | `timeout` | **`UNVERIFIED`** | `0.22` | Fell back cleanly to 5 local FEVER hits (`sim 0.44–0.49`), all gated to `NEI`; uncertainty note explained timeout. No crash or fabrication. |
| `requests.ConnectionError` | `offline` | **`UNVERIFIED`** | `0.22` | Logged warning cleanly, relied on local FEVER only, abstained to `UNVERIFIED`. |
| `requests.HTTPError` (500) | `offline` | **`UNVERIFIED`** | `0.22` | Logged warning cleanly, relied on local FEVER only, abstained to `UNVERIFIED`. |

---

## 6. External API Implementation Audit: Google Fact Check & GDELT (Objectives 9–10)

Codebase search (`backend/**/*.py`, `ml/**/*.py`, `frontend/src/**/*.ts*`) and inspection of `data/database/fakenews.db` and `data/news_cache.db` verified **what is actually built versus merely configured in `.env`**:

| Component | `.env` Status (Verified Present, Value Hidden) | `config.py` / `.env.example` | Backend Code & SQLite Status | Frontend UI Status |
|---|---|---|---|---|
| **Google Fact Check Tools API** | `GOOGLE_FACT_CHECK_API_KEY` set non-empty | Declared in `config.py:53` & `.env.example:42` | **NOT IMPLEMENTED.** Zero occurrences of `factchecktools.googleapis.com`, zero client modules, zero rating preservation or evidence aggregation logic. | **NOT IMPLEMENTED.** Zero fact-check match cards or publisher ratings in UI. |
| **GDELT DOC 2.0 (Verification)** | `GDELT_ENABLED` set non-empty | Missing from `config.py` and `.env.example` | **NOT IMPLEMENTED.** Zero GDELT query integration inside `ml/rag/` or `verification_service.py`. | **NOT IMPLEMENTED.** |
| **GDELT Budget (`200`), Warning (`20`), Persistence & Caching** | `GDELT_REQUEST_LIMIT`, `GDELT_WARNING_THRESHOLD` set non-empty | Missing from `config.py` and `.env.example` | **NOT IMPLEMENTED.** Neither `fakenews.db` (`verification_records`) nor `news_cache.db` (`news_articles`, `news_sources`) has a usage counter, budget cap, or verification evidence cache table. | **NOT IMPLEMENTED.** No persistent GDELT usage dashboard exists. |
| **GDELT DOC 2.0 (Live News Monitor)** | Controlled only by RSS/GDELT feed refresh | Endpoint URL seeded in `news_cache.db` `news_sources` | **UNCOUNTED & UNCACHED.** `_ingest_gdelt_source` ([`news_service.py`](file:///D:/Documents/FakeNewsBlockChain/backend/app/services/news_service.py#L307-L351)) calls GDELT directly via `urllib.request.urlopen` on every refresh with no counter/cap. Last run (`2026-11-11T07:27:29Z`) failed with SSL handshake timeout; `news_articles` contains `279` RSS rows and `0` GDELT rows. | Listed as monitored feed source only; no request budget telemetry. |

---

## 7. Sepolia Transaction Hash Discrepancy Forensics (Objective 11)

Read-only queries executed via Web3 against Sepolia RPC (`chain_id = 11155111`), read-only inspection of `data/database/fakenews.db`, `blockchain/deployments/sepolia-deployment.json`, `.env` derived wallet address, and `transcript.jsonl` established the complete explanation:

| Artifact / Field | Reported Mystery Output (`0x7147...`) | Authentic Sepolia + SQLite Record (`0x8ba1...`) | Deployment Record (`0xc3c3...`) |
|---|---|---|---|
| **Transaction Hash** | `0x7147d07d8b3545345721d6d4765ac5f2679e8d3d4a2d558a5410e9e024ed450b` | **`0x8ba191c38e155af5e69c4dbf949f8eda1cf3cdb63fdb35641ced5129386f8941`** | `0xc3c340f4cb3a7c861dd03d89f8f921cc5b5881fe22577390fafb20f7b506dc8a` |
| **Live Sepolia RPC Lookup** | **`TransactionNotFound`** (never existed on-chain) | **CONFIRMED (`status = 1`, `gasUsed = 794,658`)** | **CONFIRMED (`status = 1`, `gasUsed = 6,327,393`)** |
| **Block Number** | `10772742` *(fabricated)* | **`12076191`** | `12076163` |
| **Block Timestamp** | `1778067300` (`2026-05-06T11:35:00Z`) | On-chain: **`1793963544`** (`2026-11-06T11:12:24+00:00`) *(Note: SQLite stores `1762427544`)* | `1793963208` |
| **Submitter / Wallet Address** | `0x85399c72245F5053564D061291592836DF2C8677` *(wrong)* | **`0x85357b97fA45f09743e289D3366A5936F044e57E`** (matches `.env` wallet & `owner()`) | `0x85357b97fA45f09743e289D3366A5936F044e57E` |
| **Contract Address** | `0xcDa4CE06d44642Fd0034C817B5b7cB6AFC886ffb` | `0xcDa4CE06d44642Fd0034C817B5b7cB6AFC886ffb` (`paused=False`, `totalVerifications=1`) | Deployed `0xcDa4CE06d44642Fd0034C817B5b7cB6AFC886ffb` |
| **Canonical Hash (`verif-9c524ca7b6f5`)** | `42007960...16a2cc53` | On-chain == SQLite == Recomputed: **`42007960ae4bf66cbc74dfb24ef80429fdba86ca34de3bc1a8d0ff9c16a2cc53`** | N/A (deploy tx) |

### Root Cause of `0x7147...`
1. Inspection of the conversation transcript (`transcript.jsonl` Line `2864`, `step_index=2862`, `created_at=2026-11-11T07:28:29Z`) shows `source="MODEL"`, `type="PLANNER_RESPONSE"` emitted an inline hallucinated `<SYSTEM_MESSAGE>` block while waiting for `task-2861` (using non-existent API path `/api/v1/blockchain/audit/compare/...` and invented JSON keys `match_status`, `sqlite_hash`, `wallet_balance_eth`, `total_on_chain_records`).
2. Six seconds later (`2026-11-11T07:28:35Z`), genuine OS task notification Line `2866` (`source="SYSTEM"`) arrived from `task-2861` reporting the real SQLite record `0x8ba191...`, and subsequent `task-2869` verified `VERIFIED_MATCH` via `GET /api/v1/blockchain/audit/verif-9c524ca7b6f5/compare`.
3. **Minor SQLite Metadata Inconsistency Discovered:** In `data/database/fakenews.db`, `verif-9c524ca7b6f5.block_timestamp` is `1762427544` (`2025-11-06T11:12:24+00:00`, off by `-31,536,000` seconds = 365 days), whereas `block_datetime` is `2026-11-06T11:12:24+00:00` and live Sepolia RPC `block.timestamp` is `1793963544` (`2026-11-06T11:12:24+00:00`). Canonical record hashing and on-chain verification remain unaffected.

---

## 8. Prioritized Known Limitations & Recommended Fixes (Unimplemented — Pending Approval)

1. **Replace Closed Verb Whitelist in `split_compound_claims()` (Highest Priority):**  
   Fix `ml/inference/evidence_alignment.py` so `, and `, `, while `, `, but `, `, whereas `, and `;` split any >= 4-word clauses containing general inflected/auxiliary/action verb forms instead of a hardcoded 34-word list (`0/4` `PARTIALLY_TRUE` recall and `3` false `GENUINE` verdicts stemmed directly from this bug).
2. **Fix Temporal Reasoning Precedence & Active-Tenure Patterns (`OUTDATED` vs `GENUINE`):**  
   - Stale `fever_local` (`2017-06`) sentences must **never** populate `active_hits` to veto live Wikipedia (`wikipedia_live`) evidence showing death/retirement/rebrand (`#22` Queen Elizabeth II).
   - Expand `HISTORICAL_END_PATTERNS` to capture `"until her/his death in YYYY"`, `"formerly named ... Inc."`, and `"now ..."` transitions.
   - Expand `_has_active_current_tenure()` to recognize ordinal incumbent phrasing (`"is the 47th president"`, `"current 47th"`, `"YYYY–present"`) so non-contiguous officeholders (`#26` Donald Trump) are not misclassified as `OUTDATED`.
3. **Eliminate Cross-Subject Contamination & Subject-Entity Word-Order Fragility:**  
   - In `extract_subject_entities()`, strip numeric/quantifier/common-noun noise (`"over"`, `"all"`) properly and avoid matching generic single tokens (`"nobel"`) across distinct award categories (`Nobel Peace Prize` vs `Nobel Prize in Chemistry` on `#11`) or namesake entities (`Mark S. Zuckerberg` on `#24`).
   - Do not block live Wikipedia fallback solely because a local FEVER distractor shares a secondary word (`#10` `Reptile` / `Antarctica` >= `0.62`, `#06` `Lyme disease` >= `0.62`), and allow lead sentence retrieval (`sentence_id <= 2` on an exact page title match) alongside MiniLM ranking (`#03` `ChatGPT`).
4. **Implement Approved External APIs & Persistent GDELT Budget Governance:**  
   Implement `google_factcheck_client.py`, `gdelt_client.py` (shared across verification and `news_service.py`), `evidence_cache.py` (SQLite query caching), `gdelt_usage_tracker.py` (persistent counter capped at `GDELT_REQUEST_LIMIT=200` with `GDELT_WARNING_THRESHOLD=20` alerts), `GDELT_*` settings in `config.py` / `.env.example`, centralized article-claim aggregation weighting, and frontend fact-check/GDELT/usage dashboard cards.
5. **Preserve Weight & Calibration Boundaries / Reconcile SQLite `block_timestamp`:**  
   Keep DeBERTa weights unchanged with explicit disclosure that `logit[2]` remains collapsed (proposing a separately evaluated 3-class NLI model as future upgrade), and align SQLite `verif-9c524ca7b6f5.block_timestamp` display or document its 365-day offset during audit sync without touching the anchored hash.

---

*End of Read-Only Validation Audit Report. No project files, SQLite databases, `.env`, or Sepolia contract states were altered during verification.*
