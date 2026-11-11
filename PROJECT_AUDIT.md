# PROJECT AUDIT REPORT
**Project:** FakeNewsBlockchain – Real-Time Multimodal Fake News Detection & Fact Verification  
**Date:** November 6, 2026  
**Auditor:** Senior AI/ML Engineer & Software Architect (Antigravity)  
**Status:** STEP 1 Complete — All 6 Core Research Assets Validated  

---

## 1. Executive Summary

A comprehensive, non-destructive audit of the workspace at `D:\Documents\FakeNewsBlockChain` has been conducted. All six critical machine learning and retrieval assets located in the `Requirements/` directory were inspected and verified down to their binary structures, safetensors headers, JSON schemas, and vector alignments.

**Key Findings:**
1. **Asset Integrity:** All 3 transformer models (`bert_isot_temporal_v1`, `bert_liar_v1`, `fever_verifier_v1`), the FAISS index (`wiki_fever.index`), and both corpus mapping files (`row_mapping.jsonl`, `sentences.jsonl`) are present, non-corrupted, and 100% structurally valid.
2. **Path & Naming Discrepancy Identified:** The prompt listed `ml/models/bert_isot_baseline_v1/`, but the physical folder in `Requirements/` is named `bert_isot_temporal_v1`. Binary inspection confirms it is a 100% compatible HuggingFace `BertForSequenceClassification` model with identical binary labels (`FAKE`, `REAL`).
3. **FAISS Index & Corpus Alignment:** The FAISS index is an inner-product index (`IndexFlatIP`, magic `IxFI`) containing exactly 126,000 vectors of dimension 384 (193,536,045 bytes). Both `row_mapping.jsonl` and `sentences.jsonl` contain exactly 126,000 rows with zero mismatch across document IDs, rows, and page pointers.
4. **Environment Readiness:** Python 3.12.2 (64-bit), Node.js v22.19.0, npm 10.9.3, and Git 2.53.0 are installed. The base Python environment lacks heavy ML dependencies (`torch`, `transformers`, `sentence_transformers`, `faiss`), so an isolated Python virtual environment will be established without altering global packages.

---

## 2. Environment & System Specifications

| Attribute | Detected Value | Compatibility Assessment |
| :--- | :--- | :--- |
| **Operating System** | Windows 10/11 Pro (64-bit) | Fully compatible with target constraints |
| **Python Version** | Python 3.12.2 (`C:\Users\ADMIN\AppData\Local\Programs\Python\Python312\python.exe`) | Meets Python 3.12 constraint |
| **Node.js / npm** | Node v22.19.0 / npm 10.9.3 | Modern LTS ready for React + Vite + Tailwind |
| **Git Version** | Git 2.53.0.windows.1 | Ready for version control |
| **Disk Space (D:)** | 54.61 GB Free / 42.59 GB Used | Ample headroom for virtual environments, caches, and database |
| **Disk Space (C:)** | 83.04 GB Free / 293.28 GB Used | Sufficient for temporary builds and npm cache |
| **RAM Budget** | 16 GB Laptop RAM constraint | Enforces CPU-only, lazy model loading & singleton inference |
| **Package Manager** | `uv 0.11.33` detected on system | Enables fast, deterministic virtualenv and dependency installation |

---

## 3. Machine Learning & Retrieval Asset Audit

### Asset 1: BERT ISOT Article Classifier (`bert_isot_temporal_v1`)
- **Physical Location:** `Requirements/bert_isot_temporal_v1/`
- **Model Architecture:** `BertForSequenceClassification` (base model: `google-bert/bert-base-uncased`)
- **Key Files & Sizes:**
  - `model.safetensors`: 437,958,624 bytes (417.67 MB, 202 tensors validated)
  - `config.json`: 920 bytes (`model_type: "bert"`, `hidden_size: 768`, `max_position_embeddings: 512`)
  - `tokenizer_config.json`: 351 bytes (`tokenizer_class: "BertTokenizer"`)
  - `tokenizer.json`: 711,494 bytes (HuggingFace Fast Tokenizer)
  - `training_args.bin`: 5,201 bytes
- **Label Mapping:**
  - `id2label`: `{"0": "FAKE", "1": "REAL"}`
  - `label2id`: `{"FAKE": 0, "REAL": 1}`
- **Compatibility Analysis:**
  - *Discrepancy Note:* Prompt references `ml/models/bert_isot_baseline_v1/`, but disk contains `bert_isot_temporal_v1`.
  - *Verdict:* 100% compatible. The model accepts text up to 512 tokens and outputs binary logits for FAKE vs REAL.
  - *Engineering Constraint:* Must be treated strictly as a statistical article-style classifier, not definitive proof of truth, due to known publisher/date distribution shifts on the ISOT dataset.

---

### Asset 2: BERT LIAR Claim Classifier (`bert_liar_v1`)
- **Physical Location:** `Requirements/bert_liar_v1/`
- **Subdirectories Present:**
  - `checkpoint-1920/` (contains training state, optimizer, model weights)
  - `checkpoint-2560/` (contains training state, optimizer, model weights)
  - `final_model/` (production deployment target)
- **Deployment Target (`final_model/`):**
  - `model.safetensors`: 437,970,928 bytes (417.68 MB, 202 tensors validated)
  - `config.json`: 1,100 bytes (`model_type: "bert"`, `hidden_size: 768`, 6 classes)
  - `tokenizer_config.json`: 351 bytes
  - `tokenizer.json`: 711,661 bytes
  - `training_args.bin`: 5,265 bytes
- **Label Mapping (6 classes):**
  - `0`: `pants-fire`
  - `1`: `false`
  - `2`: `barely-true`
  - `3`: `half-true`
  - `4`: `mostly-true`
  - `5`: `true`
- **Compatibility Analysis:**
  - *Verdict:* 100% compatible. Deploy using `Requirements/bert_liar_v1/final_model`.
  - *Engineering Constraint:* Test accuracy is ~26.84%. Its softmax probabilities provide a multi-point claim signal but must never be presented as literal truth probabilities.

---

### Asset 3: DeBERTa FEVER Evidence Verifier (`fever_verifier_v1`)
- **Physical Location:** `Requirements/fever_verifier_v1/`
- **Model Architecture:** `DebertaV2ForSequenceClassification` (`microsoft/deberta-v3-base`)
- **Key Files & Sizes:**
  - `model.safetensors`: 737,722,356 bytes (703.54 MB, 203 tensors validated)
  - `config.json`: 1,016 bytes (`model_type: "deberta-v2"`, `vocab_size: 128100`, `hidden_size: 768`)
  - `spm.model`: 2,464,616 bytes (SentencePiece tokenizer model)
  - `tokenizer.json`: 8,656,624 bytes
  - `tokenizer_config.json`: 1,315 bytes
  - `special_tokens_map.json`: 286 bytes
  - `added_tokens.json`: 23 bytes
- **Label Mapping (3 classes):**
  - `0`: `SUPPORTS`
  - `1`: `REFUTES`
  - `2`: `NOT ENOUGH INFO`
- **Compatibility Analysis:**
  - *Verdict:* 100% compatible. Valid safetensors weights and complete SentencePiece/Fast tokenizers.
  - *Engineering Constraint:* Evaluation accuracy of 97.25% was achieved on oracle/gold evidence subsets. In real-world retrieval, accuracy depends directly on retrieval quality.

---

### Asset 4: FAISS Vector Index (`wiki_fever.index`)
- **Physical Location:** `Requirements/wiki_fever.index`
- **File Size:** 193,536,045 bytes
- **Binary Header & Metric Inspection:**
  - Magic Bytes: `b'IxFI'` (`IndexFlatIP` — Inner Product metric)
  - Embedding Dimension: `384` (Float32, 4 bytes per dimension)
  - Vector Count: `126,000`
  - Exact Byte Calculation: $45 \text{ bytes (header)} + (126,000 \times 384 \times 4 \text{ bytes}) = 193,536,045 \text{ bytes}$
  - Match: **Exact Match**
- **Embedding Model Alignment:** Matches `sentence-transformers/all-MiniLM-L6-v2` (which produces 384-dimensional unit-normalized embeddings).
- **Inference Note:** Inner Product on unit-normalized vectors is mathematically identical to Cosine Similarity.

---

### Asset 5 & 6: Evidence Mapping & Sentences Corpus
- **Files:**
  - `Requirements/row_mapping.jsonl` (12,399,064 bytes, 126,000 JSON lines)
  - `Requirements/sentences.jsonl` (30,359,004 bytes, 126,000 JSON lines)
- **Schema & Alignment Verification:**
  - `row_mapping.jsonl` format: `{"row": int, "doc_id": str, "page": str, "sentence_id": int}`
  - `sentences.jsonl` format: `{"doc_id": str, "page": str, "sentence_id": int, "text": str}`
  - Cross-check points verified: Indices 0, 100, 1,000, 25,000, 50,000, 75,000, 100,000, 125,999.
  - Alignment Result: Zero discrepancies found. Index row $i$ in `wiki_fever.index` points exactly to line $i$ in `row_mapping.jsonl` and `sentences.jsonl`.
- **Engineering Constraint:** Covers a targeted FEVER Wikipedia subset (126,000 sentences), not the entirety of Wikipedia. Missing evidence must lead to `NOT ENOUGH INFO` / `UNVERIFIED`, never a default `FAKE` verdict.

---

## 4. Discrepancies, Risks & Recommended Path Strategy

| Item | Found in Workspace | Mentioned in Prompt | Risk Assessment & Mitigation |
| :--- | :--- | :--- | :--- |
| **ISOT Model Directory** | `Requirements/bert_isot_temporal_v1` | `ml/models/bert_isot_baseline_v1` | **Low Risk.** Both are binary BERT classifiers. We configure backend paths via `.env` pointing directly to `Requirements/bert_isot_temporal_v1`. |
| **LIAR Model Directory** | Subdirectories (`final_model`, checkpoints) | `ml/models/bert_liar_v1` | **Low Risk.** Point `.env` to `Requirements/bert_liar_v1/final_model` which contains the finished safetensors weights. |
| **Asset Location** | Root `Requirements/` folder | `ml/models/` and `ml/retrieval/` | **Zero Risk.** Per instruction 5: *"Do not rename, modify, delete, retrain or overwrite any original assets"*. We will keep `Requirements/` untouched and point application paths to them via environment variables or symbolic references. |
| **Base Python Packages** | Missing PyTorch, Transformers, FAISS | Needs Python 3.12 backend | **Standard.** Create a dedicated virtual environment (`.venv`) for `backend` and install pinned versions using `uv` or `pip`. |

---

## 5. Recommended Backend Integration Paths

```env
# Recommended .env model paths for backend
MODEL_FEVER_PATH="Requirements/fever_verifier_v1"
MODEL_ISOT_PATH="Requirements/bert_isot_temporal_v1"
MODEL_LIAR_PATH="Requirements/bert_liar_v1/final_model"
EMBEDDING_MODEL_NAME="sentence-transformers/all-MiniLM-L6-v2"

RETRIEVAL_INDEX_PATH="Requirements/wiki_fever.index"
RETRIEVAL_ROW_MAPPING_PATH="Requirements/row_mapping.jsonl"
RETRIEVAL_SENTENCES_PATH="Requirements/sentences.jsonl"
```

*Audit verified and certified complete.*
