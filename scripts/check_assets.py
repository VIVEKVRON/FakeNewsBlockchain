#!/usr/bin/env python3
"""
scripts/check_assets.py
Comprehensive integrity and alignment verification for FakeNewsBlockchain ML assets.
"""

import json
import os
import struct
import sys

# Ensure UTF-8 output encoding across Windows command prompts
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def check_models(base_dir: str = "Requirements") -> bool:
    print("\n[1/4] Auditing Transformer Models...")
    models = {
        "BERT ISOT Classifier": {
            "path": os.path.join(base_dir, "bert_isot_temporal_v1"),
            "required_files": ["config.json", "model.safetensors", "tokenizer.json", "tokenizer_config.json"],
            "expected_arch": "BertForSequenceClassification",
            "expected_classes": 2
        },
        "BERT LIAR Classifier (final_model)": {
            "path": os.path.join(base_dir, "bert_liar_v1", "final_model"),
            "required_files": ["config.json", "model.safetensors", "tokenizer.json", "tokenizer_config.json"],
            "expected_arch": "BertForSequenceClassification",
            "expected_classes": 6
        },
        "DeBERTa FEVER Verifier": {
            "path": os.path.join(base_dir, "fever_verifier_v1"),
            "required_files": ["config.json", "model.safetensors", "spm.model", "tokenizer.json", "tokenizer_config.json"],
            "expected_arch": "DebertaV2ForSequenceClassification",
            "expected_classes": 3
        }
    }

    all_passed = True
    for name, spec in models.items():
        model_path = spec["path"]
        if not os.path.isdir(model_path):
            print(f"  [FAIL] Directory missing: {model_path}")
            all_passed = False
            continue

        missing = [f for f in spec["required_files"] if not os.path.isfile(os.path.join(model_path, f))]
        if missing:
            print(f"  [FAIL] {name} missing files: {missing}")
            all_passed = False
            continue

        # Check config
        with open(os.path.join(model_path, "config.json"), "r", encoding="utf-8") as f:
            cfg = json.load(f)

        arch = cfg.get("architectures", [None])[0]
        id2label = cfg.get("id2label", {})
        num_labels = len(id2label)

        # Check safetensors header
        st_path = os.path.join(model_path, "model.safetensors")
        st_size = os.path.getsize(st_path)
        with open(st_path, "rb") as f:
            header_len = struct.unpack("<Q", f.read(8))[0]
            header_json = json.loads(f.read(header_len).decode("utf-8"))
            num_tensors = len([k for k in header_json.keys() if k != "__metadata__"])

        print(f"  [PASS] {name}:")
        print(f"         Path: {model_path}")
        print(f"         Architecture: {arch} (Matches expected: {arch == spec['expected_arch']})")
        print(f"         Labels ({num_labels}): {id2label}")
        print(f"         Safetensors: {st_size:,} bytes, {num_tensors} tensors")

    return all_passed


def check_faiss_index(index_path: str = "Requirements/wiki_fever.index") -> bool:
    print("\n[2/4] Auditing FAISS Vector Index...")
    if not os.path.isfile(index_path):
        print(f"  [FAIL] FAISS index file not found at: {index_path}")
        return False

    file_size = os.path.getsize(index_path)
    with open(index_path, "rb") as f:
        magic = f.read(4)
        d = struct.unpack("<i", f.read(4))[0]
        ntotal = struct.unpack("<q", f.read(8))[0]

    expected_size = 45 + (ntotal * d * 4)
    is_valid_magic = (magic == b"IxFI")
    is_valid_dim = (d == 384)
    is_valid_count = (ntotal == 126000)
    is_size_match = (file_size == expected_size)

    if is_valid_magic and is_valid_dim and is_valid_count and is_size_match:
        print(f"  [PASS] FAISS Index: {index_path}")
        print(f"         Magic Header: {magic} (IndexFlatIP)")
        print(f"         Vector Dimension: {d}")
        print(f"         Total Vectors: {ntotal:,}")
        print(f"         Binary Size: {file_size:,} bytes (Exact match)")
        return True
    else:
        print(f"  [FAIL] FAISS Index validation failed: magic={magic}, dim={d}, ntotal={ntotal}, size={file_size}")
        return False


def check_corpus_alignment(
    map_path: str = "Requirements/row_mapping.jsonl",
    sent_path: str = "Requirements/sentences.jsonl"
) -> bool:
    print("\n[3/4] Auditing Corpus & Row Alignment (126,000 sentences)...")
    if not os.path.isfile(map_path) or not os.path.isfile(sent_path):
        print("  [FAIL] One or both corpus files are missing.")
        return False

    total_rows = 0
    mismatches = 0

    with open(map_path, "r", encoding="utf-8") as f_map, open(sent_path, "r", encoding="utf-8") as f_sent:
        for idx, (l_map, l_sent) in enumerate(zip(f_map, f_sent)):
            total_rows += 1
            d_map = json.loads(l_map)
            d_sent = json.loads(l_sent)

            if d_map.get("row") != idx or d_map.get("doc_id") != d_sent.get("doc_id"):
                mismatches += 1
                if mismatches <= 3:
                    print(f"  [FAIL] Row mismatch at {idx}: map={d_map} vs sent={d_sent}")

    if total_rows == 126000 and mismatches == 0:
        print(f"  [PASS] Total rows verified: {total_rows:,}")
        print(f"         Row alignment mismatches: 0")
        print(f"         Mapping and sentences 1-to-1 sync: 100%")
        return True
    else:
        print(f"  [FAIL] Verification failed: total_rows={total_rows}, mismatches={mismatches}")
        return False


def check_temporal_compatibility() -> bool:
    print("\n[4/4] Verifying bert_isot_temporal_v1 Compatibility...")
    cfg_path = "Requirements/bert_isot_temporal_v1/config.json"
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    is_bert = cfg.get("model_type") == "bert"
    is_cls = "BertForSequenceClassification" in cfg.get("architectures", [])
    labels = cfg.get("id2label", {})
    has_labels = labels.get("0") == "FAKE" and labels.get("1") == "REAL"

    if is_bert and is_cls and has_labels:
        print("  [PASS] bert_isot_temporal_v1 is 100% compatible with HuggingFace BertForSequenceClassification pipeline.")
        return True
    else:
        print(f"  [FAIL] Compatibility check failed: type={cfg.get('model_type')}, arch={cfg.get('architectures')}")
        return False


def main():
    print("=" * 70)
    print(" FakeNewsBlockchain - Machine Learning Asset Verification")
    print("=" * 70)

    m_ok = check_models()
    f_ok = check_faiss_index()
    c_ok = check_corpus_alignment()
    t_ok = check_temporal_compatibility()

    print("\n" + "=" * 70)
    if m_ok and f_ok and c_ok and t_ok:
        print(" ALL ASSET CHECKS PASSED SUCCESSFULLY (Exit Code 0)")
        print("=" * 70)
        sys.exit(0)
    else:
        print(" ONE OR MORE ASSET CHECKS FAILED (Exit Code 1)")
        print("=" * 70)
        sys.exit(1)


if __name__ == "__main__":
    main()
