"""
scripts/demo_article_verify.py
Runs sample verification requests against the article verification API (/api/v1/verify/article)
and prints formatted results for user review.
"""

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Ensure UTF-8 stdout
if sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import json
from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)

ARTICLES = [
    {
        "category": "1. SUPPORTED REAL ARTICLE (Expected: LIKELY_GENUINE)",
        "payload": {
            "title": "TLC Reality Series Follows Duggar Family",
            "text": (
                "19 Kids and Counting is an American reality television show featuring the Duggar family. "
                "The reality show focused on the life of the Duggar family who are devout Baptists. "
                "The series originally documented their day-to-day household activities in Arkansas."
            ),
            "max_claims": 2
        }
    },
    {
        "category": "2. FABRICATED REFUTED ARTICLE (Expected: LIKELY_FAKE)",
        "payload": {
            "title": "Television Show Cancellation Date Rumors",
            "text": (
                "19 Kids and Counting was cancelled in 2030. "
                "Industry analysts claimed that network executives delayed the official cancellation "
                "until the beginning of the next decade."
            ),
            "max_claims": 2
        }
    },
    {
        "category": "3. MISLEADING BROADCASTER CLAIM (Expected: MISLEADING - HBO vs TLC)",
        "payload": {
            "title": "Television Network Broadcasting History",
            "text": (
                "19 Kids and Counting aired on HBO. "
                "The show attracted millions of viewers across the country during its primetime weekend broadcast slot."
            ),
            "max_claims": 1
        }
    },
    {
        "category": "4. UNVERIFIED / OUT-OF-KNOWLEDGE CLAIM (Expected: UNVERIFIED)",
        "payload": {
            "title": "Alien Potatoes Discovered on Pluto",
            "text": (
                "Biologists discovered alien potatoes on Pluto in 2026. "
                "The extraterrestrial tubers supposedly survive in sub-zero atmospheric methane."
            ),
            "max_claims": 2
        }
    }
]

def main():
    print("=" * 80)
    print("FAKENEWSBLOCKCHAIN - REAL-TIME ARTICLE VERIFICATION DEMO")
    print("Testing /api/v1/verify/article with Multi-Signal Pipeline")
    print("=" * 80)

    for case in ARTICLES:
        print(f"\n>>> Running: {case['category']}")
        print(f"Title: {case['payload']['title']}")
        print(f"Text Snippet: {case['payload']['text'][:100]}...")
        
        response = client.post("/api/v1/verify/article", json=case["payload"])
        if response.status_code != 200:
            print(f"ERROR: HTTP {response.status_code}: {response.text}")
            continue
        
        res = response.json()
        print(f"\n[RESULTS]")
        print(f"  Overall Truth Verdict:   {res['overall_verdict']} (Confidence: {res['overall_confidence']:.2f})")
        print(f"  Summary Explanation:     {res['summary_explanation']}")
        print(f"  Article Classifier:      {res['article_classifier']['prediction']} (Confidence: {res['article_classifier']['confidence']:.2f})")
        print(f"  Warning:                 {res['article_classifier']['distribution_shift_warning']}")
        print(f"  Claims Analyzed:         {res['claims_analyzed']}")
        
        for idx, cl in enumerate(res["extracted_claims"], 1):
            print(f"\n  --- Claim {idx}: \"{cl['claim']}\"")
            print(f"      Claim Verdict:       {cl['verdict']} (Confidence: {cl['confidence_score']:.2f})")
            print(f"      Claim Explanation:   {cl['explanation']}")
            if cl.get("liar_signal"):
                print(f"      LIAR Signal:         {cl['liar_signal']['prediction']} (Top Prob: {cl['liar_signal']['confidence']:.2f})")
            if cl["evidence"]:
                top_ev = cl["evidence"][0]
                print(f"      Top Evidence Page:   {top_ev['page']} (Sim: {top_ev['retrieval_similarity']:.2f}, NLI: {top_ev['nli_label']} {top_ev['nli_confidence']*100:.1f}%)")
                print(f"      Top Evidence Text:   \"{top_ev['text']}\"")
        print("-" * 80)

if __name__ == "__main__":
    main()
