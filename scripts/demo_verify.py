#!/usr/bin/env python3
"""
scripts/demo_verify.py
Demonstration script executing real verification requests across all 4 verdict categories.
"""

import sys
import json
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from backend.app.main import app

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

client = TestClient(app)

claims = [
    ("SUPPORTED CLAIM (LIKELY GENUINE)", "19 Kids and Counting is an American reality television show featuring the Duggar family."),
    ("REFUTED CLAIM (LIKELY FAKE)", "19 Kids and Counting was cancelled in 2030."),
    ("CONFLICTING / AMBIGUOUS CLAIM (MISLEADING)", "19 Kids and Counting aired on HBO."),
    ("OUT-OF-DOMAIN / UNVERIFIABLE CLAIM (UNVERIFIED)", "Quantum entangled alien potatoes were discovered on Pluto in 2026.")
]

def main():
    print("=" * 80)
    print(" FakeNewsBlockchain - Real Claim Verification Engine Demo")
    print("=" * 80)

    for category, claim in claims:
        print(f"\n--- {category} ---")
        print(f"Input Claim: \"{claim}\"")
        resp = client.post("/api/v1/verify/text", json={"claim": claim, "top_k": 3})
        assert resp.status_code == 200, f"Error {resp.status_code}: {resp.text}"
        data = resp.json()

        print(f"Verification ID : {data['verification_id']}")
        print(f"User Verdict    : {data['verdict']}")
        print(f"Confidence Score: {data['confidence_score']}")
        print(f"Explanation     : {data['explanation']}")
        print(f"Conflicting Ev  : {data['conflicting_evidence_detected']}")
        print("Retrieved Evidence (Top 3):")
        for ev in data["evidence"]:
            print(f"  Rank #{ev['rank']} [{ev['nli_label']}] (Confidence: {ev['nli_confidence']*100:.1f}%, Similarity: {ev['retrieval_similarity']:.4f})")
            print(f"         Source : Wikipedia Page '{ev['page']}' (Sent #{ev['sentence_id']})")
            print(f"         Text   : \"{ev['text'][:110]}...\"")
            print(f"         NLI Dist: {ev['nli_probabilities']}")

    print("\n" + "=" * 80)
    print(" DEMO COMPLETED SUCCESSFULLY")
    print("=" * 80)

if __name__ == "__main__":
    main()
