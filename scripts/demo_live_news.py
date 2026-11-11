"""
scripts/demo_live_news.py
Demonstration script testing Live Breaking News Monitoring:
  - Querying active sources
  - Refreshing live feeds from BBC, NPR, NYTimes, Phys.org, GDELT 2.0
  - Verifying duplicate detection and SQLite caching
  - Searching by keyword and category
  - Dispatching an article to the verification engine
"""

import sys
import json
import urllib.request
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_URL = "http://127.0.0.1:5173/api/v1"


def get_json(endpoint: str):
    req = urllib.request.Request(f"{BASE_URL}{endpoint}")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def post_json(endpoint: str, payload: dict = None):
    data = json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}{endpoint}",
        data=data,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    print("=" * 80)
    print("FAKENEWSBLOCKCHAIN - LIVE BREAKING NEWS MONITORING DEMO")
    print("Testing /api/v1/news via Frontend Reverse Proxy")
    print("=" * 80)

    # 1. Inspect Sources
    print("\n>>> 1. Fetching Active News Ingestion Sources...")
    sources = get_json("/news/sources")["sources"]
    for s in sources:
        print(f"  - [{s['source_type'].upper()}] {s['name']} ({s['category']}): {s['feed_url'][:60]}...")

    # 2. Refresh Feeds
    print("\n>>> 2. Triggering News Feed Refresh (RSS & GDELT)...")
    refresh_res = post_json("/news/refresh")
    print(f"  Status:             {refresh_res['status']}")
    print(f"  Articles Fetched:   {refresh_res['articles_fetched']}")
    print(f"  New Articles Saved: {refresh_res['new_articles_saved']}")
    print(f"  Duplicates Skipped: {refresh_res['duplicates_skipped']}")
    print(f"  Sources Succeeded:  {refresh_res['sources_succeeded']} / {refresh_res['sources_contacted']}")

    # 3. List Latest Cached Articles
    print("\n>>> 3. Listing Latest Cached Breaking News...")
    news_list = get_json("/news?limit=5")
    print(f"  Total Articles in SQLite Cache: {news_list['total']}")
    for art in news_list["articles"]:
        verdict_str = f"[{art['verified_verdict']}]" if art["verified_verdict"] else "[Unverified]"
        print(f"  * {verdict_str} ({art['publisher']}) \"{art['title'][:70]}\"")
        print(f"    URL: {art['canonical_url'][:75]}...")

    # 4. One-Click Verification of an Article
    if news_list["articles"]:
        target_art = news_list["articles"][0]
        print(f"\n>>> 4. Dispatching Article '{target_art['id']}' to Fact Verification Engine...")
        print(f"  Headline: \"{target_art['title']}\"")
        v_res = post_json(f"/news/{target_art['id']}/verify")
        print(f"  Truth Verdict:       {v_res['overall_verdict']} (Confidence: {v_res['overall_confidence']:.2f})")
        print(f"  Summary Explanation: {v_res['summary_explanation']}")
        print(f"  Article Classifier:  {v_res['article_classifier']['prediction']} ({v_res['article_classifier']['confidence']:.2f})")
        print(f"  Claims Analyzed:     {v_res['claims_analyzed']}")
        for cl in v_res["extracted_claims"][:2]:
            print(f"    - Claim: \"{cl['claim']}\" -> {cl['verdict']}")
            if cl["evidence"]:
                print(f"      Top Evidence: {cl['evidence'][0]['page']} (NLI: {cl['evidence'][0]['nli_label']} {cl['evidence'][0]['nli_confidence']*100:.1f}%)")

    print("\n" + "=" * 80)
    print("LIVE NEWS MONITORING DEMO COMPLETED SUCCESSFULLY")
    print("=" * 80)


if __name__ == "__main__":
    main()
