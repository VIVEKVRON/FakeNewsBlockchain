"""
ml/rag/wikipedia_fallback.py
Zero-cost, SSRF-safe public MediaWiki API fallback retriever for entities or post-2017 facts
missing or stale in the static 126k FEVER Wikipedia snapshot.
Strictly allowlists https://en.wikipedia.org with strict timeouts and graceful offline handling.
"""

import re
import threading
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import requests

from backend.app.config import get_settings
from backend.app.utils.logger import logger
from ml.inference.model_loader import get_ml_inference_semaphore, get_model_manager


ALLOWED_WIKIPEDIA_HOSTS = {"en.wikipedia.org"}
WIKIPEDIA_API_ENDPOINT = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "FakeNewsBlockchain/1.0 (https://github.com/fakenewsblockchain; local-fact-verification)"

QUERY_FILLER_WORDS = {
    "the", "is", "was", "were", "are", "be", "been", "being", "a", "an", "and", "or",
    "of", "in", "on", "at", "to", "for", "from", "by", "with", "as", "that", "this",
    "these", "those", "it", "its", "has", "have", "had", "does", "do", "did", "not",
    "no", "never", "current", "currently", "now", "today", "present", "presently",
    "official", "confirmed", "still", "always", "only", "all", "every", "sole", "solely",
    "exclusively", "former", "previously", "originally", "known", "called", "named",
    "sitting", "incumbent", "reigning", "unrenamed", "top-level", "publicly", "traded",
    "remaining", "remains", "purely", "healthy", "effectively", "formally",
    "ever", "successfully", "anywhere", "entire", "regular",
    "however", "moreover", "furthermore", "meanwhile", "additionally", "therefore",
    "although", "though", "while", "after", "before", "during", "decades", "years"
}

SEARCH_EXPANSIONS = {
    "cm": "Chief Minister",
    "pm": "Prime Minister",
}


@dataclass
class WikipediaSentenceHit:
    page: str
    sentence_id: int
    doc_id: str
    text: str
    similarity_score: float
    source_url: str
    publication_date: str


@dataclass
class WikipediaRetrievalResult:
    """Request-local Wikipedia fallback output carrying hits and exact outcome telemetry."""
    hits: List[WikipediaSentenceHit] = field(default_factory=list)
    status: str = "idle"
    from_cache: bool = False
    query_outcomes: List[Dict[str, Any]] = field(default_factory=list)


def is_allowlisted_wikipedia_url(url: str) -> bool:
    """Strict domain allowlisting guard: only HTTPS en.wikipedia.org URLs permitted."""
    try:
        parsed = urllib.parse.urlparse(url)
        return parsed.scheme == "https" and (parsed.hostname or "").lower() in ALLOWED_WIKIPEDIA_HOSTS
    except Exception:
        return False


def build_wikipedia_search_queries(claim: str) -> List[str]:
    """
    Constructs clean MediaWiki search queries from a natural-language claim.
    Produces up to 3 focused queries:
      1. Clean keyword query (possessives & filler words stripped, acronyms expanded).
      2. Prominent proper-noun phrases (preferring multi-word / non-initial topic entities).
      3. Ordinal office phrase OR corporate-rebrand / secondary entity query if applicable.
    """
    stripped_possessives = re.sub(r"(?:'s|’s)\b", "", claim)
    clean = re.sub(r"[^\w\s.\-']", " ", stripped_possessives).strip()
    tokens = clean.split()

    keyword_tokens = []
    for tok in tokens:
        stripped = tok.rstrip(".,'\"?!")
        low = stripped.lower()
        if not low or low in QUERY_FILLER_WORDS:
            continue
        expanded = SEARCH_EXPANSIONS.get(low, stripped)
        keyword_tokens.append(expanded)

    primary_query = " ".join(keyword_tokens[:6]).strip()

    # Extract capitalized entities/phrases and track whether they only appeared at sentence index 0
    proper_phrases: List[Tuple[int, str]] = []
    for m in re.finditer(
        r"\b(?:(?:\d+\s+)?[A-Z][A-Za-z0-9.\-']*(?:\s+(?:of|the|and|for|on|[A-Z][A-Za-z0-9.\-']*)){0,4})",
        clean,
    ):
        phrase = m.group(0).strip().rstrip(".,'\"?!")
        if len(phrase) > 2 and phrase.lower() not in QUERY_FILLER_WORDS:
            proper_phrases.append((m.start(), phrase))

    # Prefer multi-word or mid-sentence entities (index > 0) before single sentence-initial capitalized common nouns
    proper_phrases.sort(key=lambda item: (0 if " " in item[1] else (1 if item[0] > 0 else 2), item[0]))

    queries: List[str] = []
    if primary_query:
        queries.append(primary_query)

    for _, p in proper_phrases:
        if p.lower() != primary_query.lower():
            queries.append(p)
            if len(queries) >= 2:
                break

    # Add ordinal office phrase or corporate/parent entity query if room remains
    ordinal_office = re.search(
        r"\b(?:first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|\d+(?:st|nd|rd|th))\s+"
        r"(?:president|prime\s+minister|chief\s+minister|chancellor|monarch|king|queen)"
        r"(?:\s+of\s+(?:the\s+)?[A-Za-z][A-Za-z\s]{1,25})?\b",
        clean,
        re.IGNORECASE,
    )
    if ordinal_office:
        queries.append(ordinal_office.group(0).strip())
    elif re.search(r"\b(?:parent|company|rebranded|holding|corporation)\b", clean, re.IGNORECASE) and proper_phrases:
        lead_ent = proper_phrases[0][1]
        queries.append(f"{lead_ent} parent company")
    elif len(proper_phrases) > 1:
        for _, p in proper_phrases:
            if p.lower() != primary_query.lower():
                queries.append(p)

    # Deduplicate while preserving order, max 3 queries per claim
    deduped: List[str] = []
    seen = set()
    for q in queries:
        norm = q.lower()
        if norm not in seen and len(q) >= 2:
            seen.add(norm)
            deduped.append(q)
    return deduped[:3]


def _split_clean_sentences(extract_text: str) -> List[str]:
    """Splits plain-text Wikipedia extract into clean factual sentences without breaking initials."""
    if not extract_text:
        return []
    text = re.sub(r"==+[^=]+==+", " ", extract_text)
    text = re.sub(r"\s+", " ", text).strip()

    # Protect single-letter initials (e.g. "D. K.") and common honorifics/abbreviations before splitting
    placeholder = "<DOT>"
    protected = re.sub(r"\b([A-Z]|Jr|Sr|Dr|Mr|Mrs|Ms|St|vs|etc|Inc|Corp)\.(?=\s)", rf"\1{placeholder}", text)
    protected = re.sub(r"\b(U\.S|U\.K)\.(?=\s)", rf"\1{placeholder}", protected)

    raw_sentences = re.split(r"(?<=[.!?][\"')\]])\s+(?=[A-Z0-9\"'(])|(?<=[.!?])\s+(?=[A-Z0-9\"'(])", protected)
    cleaned = []
    for s in raw_sentences:
        s = s.replace(placeholder, ".").strip()
        if len(s) >= 20 and len(s.split()) >= 4:
            cleaned.append(s)
    return cleaned[:24]


class WikipediaFallbackClient:
    """
    SSRF-guarded, session-pooled public Wikipedia MediaWiki fallback retriever.
    Gracefully returns [] on timeouts or offline networks.
    """
    _instance: Optional["WikipediaFallbackClient"] = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self.settings = get_settings()
        self.model_manager = get_model_manager()
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": USER_AGENT})
        self._default_session_get = self._session.get
        self._thread_local = threading.local()
        self._cache: Dict[str, List[Tuple[str, str, str, str]]] = {}
        self._cache_lock = threading.Lock()
        self._initialized = True

    @property
    def last_status(self) -> str:
        """Thread-local status fallback so concurrent requests never overwrite each other."""
        return getattr(self._thread_local, "last_status", "idle")

    @last_status.setter
    def last_status(self, value: str) -> None:
        self._thread_local.last_status = value

    def _get_session(self) -> requests.Session:
        """Uses injected/patched test session when present, otherwise a thread-local Session."""
        if self._session.get != self._default_session_get:
            return self._session
        sess = getattr(self._thread_local, "session", None)
        if sess is None:
            sess = requests.Session()
            sess.headers.update({"User-Agent": USER_AGENT})
            self._thread_local.session = sess
        return sess

    def _query_mediawiki_with_status(
        self, search_query: str
    ) -> Tuple[List[Tuple[str, str, str, str]], str, bool]:
        """
        Queries en.wikipedia.org MediaWiki API for top matching pages with extracts, URLs, and revision dates.
        Returns request-local (pages, status, from_cache) without mutating shared instance state.
        """
        with self._cache_lock:
            if search_query in self._cache:
                return list(self._cache[search_query]), "cache_hit", True

        if not is_allowlisted_wikipedia_url(WIKIPEDIA_API_ENDPOINT):
            return [], "blocked_domain", False

        timeout_sec = max(2.0, float(getattr(self.settings, "WIKIPEDIA_TIMEOUT_SEC", 8.0)))
        params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": search_query,
            "gsrlimit": 4,
            "prop": "extracts|info|revisions",
            "exintro": True,
            "exlimit": 4,
            "explaintext": True,
            "inprop": "url",
            "rvprop": "timestamp",
            "format": "json",
        }

        sess = self._get_session()
        try:
            resp = sess.get(
                WIKIPEDIA_API_ENDPOINT,
                params=params,
                timeout=(min(6.0, timeout_sec), timeout_sec),
                allow_redirects=False,
            )
            if resp.status_code == 429:
                time.sleep(0.8)
                resp = sess.get(
                    WIKIPEDIA_API_ENDPOINT,
                    params=params,
                    timeout=(min(6.0, timeout_sec), timeout_sec),
                    allow_redirects=False,
                )
            resp.raise_for_status()
            if not (resp.content or b"").strip():
                return [], "empty_response", False
            data = resp.json()
        except requests.Timeout:
            logger.warning(f"Wikipedia fallback timed out for query '{search_query}'. Operating gracefully offline.")
            return [], "timeout", False
        except requests.RequestException as exc:
            logger.warning(f"Wikipedia fallback unavailable ({exc}); continuing with local knowledge base only.")
            return [], "offline", False
        except ValueError:
            return [], "invalid_response", False

        pages_map = data.get("query", {}).get("pages", {})
        if not pages_map:
            return [], "no_results", False

        # Sort by MediaWiki search rank index
        sorted_pages = sorted(pages_map.values(), key=lambda p: p.get("index", 999))
        parsed_pages: List[Tuple[str, str, str, str]] = []
        for pinfo in sorted_pages:
            title = pinfo.get("title", "").strip()
            full_url = pinfo.get("fullurl", "").strip()
            if full_url and not is_allowlisted_wikipedia_url(full_url):
                continue
            if not full_url and title:
                full_url = f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"
            revisions = pinfo.get("revisions", [])
            rev_ts = revisions[0].get("timestamp", "") if revisions else ""
            extract = pinfo.get("extract", "").strip()
            if title and extract:
                parsed_pages.append((title, full_url, rev_ts, extract))

        status = "ok" if parsed_pages else "no_results"

        with self._cache_lock:
            if len(self._cache) >= 128:
                # Evict oldest key to keep memory bounded
                first_key = next(iter(self._cache))
                del self._cache[first_key]
            self._cache[search_query] = parsed_pages

        return parsed_pages, status, False

    def _query_mediawiki(self, search_query: str) -> List[Tuple[str, str, str, str]]:
        """Backward-compatible wrapper returning pages and updating thread-local status."""
        pages, status, _ = self._query_mediawiki_with_status(search_query)
        self.last_status = status
        return pages

    def retrieve_with_status(self, claim: str, top_k: int = 5) -> WikipediaRetrievalResult:
        """
        Thread-safe, request-local entrypoint returning ranked Wikipedia sentence hits
        along with aggregated request-local status, cache provenance, and per-query outcomes.
        """
        if not getattr(self.settings, "WIKIPEDIA_FALLBACK_ENABLED", True):
            self.last_status = "disabled"
            return WikipediaRetrievalResult(hits=[], status="disabled", from_cache=False, query_outcomes=[])

        queries = build_wikipedia_search_queries(claim)
        if not queries:
            self.last_status = "no_results"
            return WikipediaRetrievalResult(hits=[], status="no_results", from_cache=False, query_outcomes=[])

        all_pages: Dict[str, Tuple[str, str, str, str]] = {}
        query_outcomes: List[Dict[str, Any]] = []
        for q in queries:
            pages, q_status, q_cached = self._query_mediawiki_with_status(q)
            query_outcomes.append(
                {
                    "query": q,
                    "status": q_status,
                    "from_cache": q_cached,
                    "pages_found": len(pages),
                }
            )
            for page_tuple in pages:
                title = page_tuple[0]
                if title not in all_pages:
                    all_pages[title] = page_tuple

        # Aggregate request-local outcome cleanly without letting later queries erase prior timeouts/cache hits
        statuses = [o["status"] for o in query_outcomes]
        any_cached_hit = any(o["from_cache"] and o["pages_found"] > 0 for o in query_outcomes)
        any_live_hit = any((not o["from_cache"]) and o["pages_found"] > 0 for o in query_outcomes)
        all_cached = bool(query_outcomes) and all(o["from_cache"] for o in query_outcomes)

        if all_pages:
            if all_cached or (any_cached_hit and not any_live_hit):
                agg_status = "cache_hit"
                agg_from_cache = True
            else:
                agg_status = "ok"
                agg_from_cache = False
        else:
            agg_from_cache = all_cached
            if "timeout" in statuses:
                agg_status = "timeout"
            elif "blocked_domain" in statuses:
                agg_status = "blocked_domain"
            elif "offline" in statuses:
                agg_status = "offline"
            elif "invalid_response" in statuses:
                agg_status = "invalid_response"
            elif "empty_response" in statuses:
                agg_status = "empty_response"
            elif all_cached:
                agg_status = "cache_hit"
            else:
                agg_status = "no_results"

        if not all_pages:
            self.last_status = agg_status
            return WikipediaRetrievalResult(
                hits=[],
                status=agg_status,
                from_cache=agg_from_cache,
                query_outcomes=query_outcomes,
            )

        candidate_rows: List[Tuple[str, int, str, str, str, str]] = []
        for title, full_url, rev_ts, extract in all_pages.values():
            sentences = _split_clean_sentences(extract)
            for s_idx, s_text in enumerate(sentences):
                doc_id = f"wiki_live_{title.replace(' ', '_')}_{s_idx}"
                candidate_rows.append((title, s_idx, doc_id, s_text, full_url, rev_ts))

        if not candidate_rows:
            empty_status = "cache_hit" if agg_from_cache else "no_results"
            self.last_status = empty_status
            return WikipediaRetrievalResult(
                hits=[],
                status=empty_status,
                from_cache=agg_from_cache,
                query_outcomes=query_outcomes,
            )

        # Score candidate sentences against claim using SentenceTransformer cosine similarity
        texts_to_encode = [claim.strip()] + [row[3] for row in candidate_rows]
        with get_ml_inference_semaphore():
            embedder = self.model_manager.get_embedding_model()
            embeddings = embedder.encode(
                texts_to_encode,
                convert_to_numpy=True,
                normalize_embeddings=True
            )
        claim_vec = embeddings[0]
        sent_vecs = embeddings[1:]
        raw_sims = np.dot(sent_vecs, claim_vec)

        claim_lc = claim.lower()
        def _rank_score(idx: int) -> float:
            title, s_idx, _, _, _, _ = candidate_rows[idx]
            score = float(raw_sims[idx])
            title_lc = title.lower()
            if title_lc in claim_lc or (len(title_lc) >= 5 and any(tok in title_lc for tok in re.findall(r"[a-z0-9]{5,}", claim_lc))):
                score += 0.03
            if s_idx <= 1 and (title_lc in claim_lc):
                score += 0.02
            return score

        limit = max(1, min(top_k, 10))
        sorted_indices = sorted(range(len(candidate_rows)), key=_rank_score, reverse=True)
        selected_indices: List[int] = []
        selected_set = set()
        page_counts: Dict[str, int] = {}

        # Pass 1: prioritize lead context on exact-title matches (up to 3) & diversify other pages (up to 2)
        for idx in sorted_indices:
            title = candidate_rows[idx][0]
            per_page_cap = 3 if title.lower() in claim_lc else 2
            if page_counts.get(title, 0) < per_page_cap:
                selected_indices.append(idx)
                selected_set.add(idx)
                page_counts[title] = page_counts.get(title, 0) + 1
                if len(selected_indices) >= limit:
                    break

        # Pass 2: fill remaining slots with secondary high-scoring sentences if needed
        if len(selected_indices) < limit:
            for idx in sorted_indices:
                if idx in selected_set:
                    continue
                selected_indices.append(idx)
                if len(selected_indices) >= limit:
                    break

        hits: List[WikipediaSentenceHit] = []
        for idx in selected_indices:
            title, s_idx, doc_id, s_text, full_url, rev_ts = candidate_rows[idx]
            hits.append(
                WikipediaSentenceHit(
                    page=title,
                    sentence_id=s_idx,
                    doc_id=doc_id,
                    text=s_text,
                    similarity_score=round(float(raw_sims[idx]), 4),
                    source_url=full_url,
                    publication_date=rev_ts or "Unknown revision date",
                )
            )

        self.last_status = agg_status
        return WikipediaRetrievalResult(
            hits=hits,
            status=agg_status,
            from_cache=agg_from_cache,
            query_outcomes=query_outcomes,
        )

    def retrieve(self, claim: str, top_k: int = 5) -> List[WikipediaSentenceHit]:
        """
        Searches live public Wikipedia for relevant pages, splits extracts into sentences,
        embeds them with all-MiniLM-L6-v2, and returns top_k sorted by cosine similarity.
        """
        res = self.retrieve_with_status(claim, top_k=top_k)
        return res.hits


def get_wikipedia_fallback() -> WikipediaFallbackClient:
    return WikipediaFallbackClient()
