"""
Unified Group E External Evidence Aggregator.

Coordinates Google Fact Check Tools API and GDELT DOC 2.0 alongside Phase 1
retrieval/verification without replacing or weakening Phase 1 NLI, alignment,
confidence, or safe abstention logic.

Core Safeguards:
  - Never converts GDELT headline counts, sentiment, or duplicate syndications into truth proof.
  - Preserves Google Fact Check publisher ratings verbatim with reviewer attribution and stale flags.
  - Flags conflicting fact-check ratings and contradicting GDELT headlines transparently.
  - Respects the shared 200-request GDELT hard budget and fails closed safely.
  - Never alters Phase 1's six-class verdict semantics or turns API outages/empty results into FAKE/GENUINE.
"""

import dataclasses
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ml.inference.evidence_alignment import extract_subject_entities
from backend.app.services.external_apis.gdelt_client import (
    GdeltArticleItem,
    GdeltClient,
    GdeltSearchResult,
)
from backend.app.services.external_apis.gdelt_usage_tracker import GdeltUsageStatus
from backend.app.services.external_apis.google_factcheck_client import (
    FactCheckMatch,
    GoogleFactCheckClient,
    GoogleFactCheckResult,
)


_GDELT_STOP = {
    "the", "is", "are", "was", "were", "be", "been", "being", "a", "an", "and",
    "or", "of", "in", "on", "at", "to", "for", "from", "by", "with", "as",
    "that", "this", "these", "those", "it", "its", "has", "have", "had",
    "did", "does", "do", "will", "would", "can", "could", "should", "may",
    "only", "exclusively", "sole", "solely", "always", "never", "all", "every",
    "what", "when", "where", "which", "who", "how", "while", "whereas", "however",
    "according", "amid", "during", "reported", "reports", "announced", "regular", "regularly",
    "today", "now", "nowadays", "current", "currently", "incumbent", "sitting", "reigning",
    "recent", "recently", "latest", "monday", "tuesday", "wednesday", "thursday", "friday",
    "saturday", "sunday", "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
}

_PHRASE_LEADING_SKIP = {"The", "A", "An", "On", "In", "By", "At", "Of", "As", "For", "To"}
_FOUR_DIGIT_YEAR_RE = re.compile(r"^(?:19|20)\d{2}$")

_STATIC_SCIENCE_TEXTBOOK_RE = re.compile(
    r"\b(boils at|freezes at|double-helix|photosynthesis|boiling point|freezing point)\b",
    re.IGNORECASE,
)

_GDELT_CONTRAST_POSITIVE_RE = re.compile(
    r"\b(confirms?|confirmed|verified|signed|enacted|approved|launched|wins?|won|agrees?|completed)\b",
    re.IGNORECASE,
)
_GDELT_CONTRAST_NEGATIVE_RE = re.compile(
    r"\b(denies?|denied|refutes?|false|hoax|debunked|fake|no evidence|never|rumou?r|retracted|cancelled|canceled|fails?|failed)\b",
    re.IGNORECASE,
)


def build_focused_claim_queries(claim_text: str) -> Tuple[str, str]:
    """
    Constructs clean focused search queries from an individual claim or extracted proposition
    (never passing an entire multi-paragraph article blindly).
    Returns: (google_fact_check_query, gdelt_doc_query).
    GDELT query stays concise (3-5 high-signal entities/topic terms, filtering temporal noise).
    """
    clean = re.sub(r"\s+", " ", (claim_text or "").strip())
    fc_query = clean[:280].strip()

    entities = extract_subject_entities(clean)
    years = re.findall(r"\b(?:19|20)\d{2}\b", clean)

    tokens = re.findall(r"[A-Za-z0-9\-]+", clean)
    gdelt_terms: List[str] = []
    seen = set()

    # 1. Extract concise multi-word proper-noun phrases without leading determiners or month noise
    for m in re.finditer(r"\b([A-Z][A-Za-z0-9\-]+(?:\s+(?:of|and|[A-Z][A-Za-z0-9\-]+)){1,3})\b", clean):
        words = m.group(1).strip().split()
        while words and words[0] in _PHRASE_LEADING_SKIP:
            words.pop(0)
        kept = [w for w in words if w.lower() not in _GDELT_STOP]
        if len(kept) < 2:
            continue
        phrase = " ".join(words)
        low = phrase.lower()
        if low not in seen and len(phrase) >= 5:
            seen.add(low)
            for part in words:
                seen.add(part.lower())
            gdelt_terms.append(f'"{phrase}"')
            if len(gdelt_terms) >= 2:
                break

    # 2. Prioritize high-signal named entities / uppercase acronyms before general lowercase words
    entity_candidates = []
    for ent in entities:
        for part in ent.split():
            entity_candidates.append(part)
    for tok in tokens:
        if len(tok) >= 2 and tok.isupper():
            entity_candidates.append(tok)

    for tok in entity_candidates:
        low = tok.lower()
        if low in _GDELT_STOP or low in seen or _FOUR_DIGIT_YEAR_RE.match(tok):
            continue
        if len(low) < 3 and not (len(tok) >= 2 and tok.isupper()):
            continue
        seen.add(low)
        gdelt_terms.append(tok)
        if len(gdelt_terms) >= 5:
            break

    # 3. Fill up to 5 terms cleanly with meaningful non-temporal topic tokens
    if len(gdelt_terms) < 5:
        for tok in tokens:
            low = tok.lower()
            if low in _GDELT_STOP or low in seen or _FOUR_DIGIT_YEAR_RE.match(tok):
                continue
            if len(low) < 3 and not (len(tok) >= 2 and tok.isupper()):
                continue
            seen.add(low)
            gdelt_terms.append(tok)
            if len(gdelt_terms) >= 5:
                break

    # 4. Append a 4-digit year ONLY when fewer than 3 non-temporal terms exist
    if len(gdelt_terms) < 3:
        for yr in years:
            if yr not in seen:
                seen.add(yr)
                gdelt_terms.append(yr)
                if len(gdelt_terms) >= 3:
                    break

    if not gdelt_terms and entities:
        gdelt_query = " ".join(entities[:4])
    else:
        gdelt_query = " ".join(gdelt_terms[:5])

    return fc_query, gdelt_query.strip()


def should_query_gdelt_for_claim(
    claim_text: str,
    phase1_verdict: Optional[str] = None,  # Deprecated/ignored: retrieval must never depend on ML verdict
    fact_check_result: Optional[GoogleFactCheckResult] = None,
) -> Tuple[bool, str]:
    """
    Prediction-independent gate deciding whether GDELT news coverage discovery is warranted,
    protecting the hard 200-request budget from static textbook assertions WITHOUT inspecting
    any initial ML prediction or preliminary verdict.
    """
    del phase1_verdict  # Explicitly unused: retrieval independence invariant
    clean = (claim_text or "").strip()
    if not clean:
        return False, "empty_claim"

    # Skip static basic textbook physics/biology facts unconditionally regardless of ML prediction
    if _STATIC_SCIENCE_TEXTBOOK_RE.search(clean):
        return False, "resolved_static_reference_fact"

    has_recent_year = bool(re.search(r"\b20(?:1[8-9]|2[0-9]|3[0])\b", clean))
    is_temporal_or_news = bool(
        re.search(
            r"\b(current|currently|incumbent|sitting|reigning|today|president|prime minister|"
            r"chancellor|secretly|memo|tax|acquired|banned|survey|election|champion|minister|"
            r"government|policy|summit|report|announced|released|joined|company|rebranded)\b",
            clean,
            re.IGNORECASE,
        )
    )
    has_entities = len(extract_subject_entities(clean)) >= 1

    if has_recent_year or is_temporal_or_news:
        return True, "news_or_uncertain_claim"
    if fact_check_result and fact_check_result.has_conflicting_reviews:
        return True, "conflicting_fact_check"
    if has_entities:
        return True, "entity_context_lookup"
    return False, "skipped_not_needed"


def _detect_gdelt_coverage_tension(articles: List[GdeltArticleItem]) -> Tuple[bool, Optional[str]]:
    """Checks if returned GDELT headlines appear to express opposing claims."""
    if len(articles) < 2:
        return False, None
    has_pos = any(_GDELT_CONTRAST_POSITIVE_RE.search(a.title) for a in articles)
    has_neg = any(_GDELT_CONTRAST_NEGATIVE_RE.search(a.title) for a in articles)
    if has_pos and has_neg:
        return (
            True,
            "Retrieved GDELT headlines contain contrasting framing (affirmative vs. skeptical/denying reports); reporting alone does not settle factual truth.",
        )
    return False, None


@dataclass
class RetrievalAttempt:
    provider: str
    direction: str  # support_oriented, contradiction_oriented, neutral
    query: str
    outcome: str    # success_with_results | no_results | cache_hit | timeout | network_error | quota_exhausted | skipped_by_policy | unavailable_no_api_key
    available: bool
    from_cache: bool = False
    items_retrieved: int = 0
    relevant_items: int = 0
    reason: Optional[str] = None
    claim_text: Optional[str] = None
    claim_id: Optional[str] = None


def _map_fc_outcome(fc_res: GoogleFactCheckResult) -> str:
    if fc_res.from_cache:
        return "cache_hit"
    if fc_res.status == "ok":
        return "success_with_results" if fc_res.matches else "no_results"
    if fc_res.status == "no_results":
        return "no_results"
    if fc_res.status == "unavailable_no_api_key":
        return "unavailable_no_api_key"
    if fc_res.status == "timeout":
        return "timeout"
    if fc_res.status in ("empty_query", "disabled"):
        return "skipped_by_policy"
    return "network_error"


def _map_gdelt_outcome(gd_res: GdeltSearchResult) -> str:
    if gd_res.from_cache:
        return "cache_hit"
    if gd_res.status == "ok":
        return "success_with_results" if gd_res.articles else "no_results"
    if gd_res.status == "no_results":
        return "no_results"
    if gd_res.status in ("connect_timeout", "read_timeout", "timeout"):
        return "timeout"
    if gd_res.status in ("quota_exhausted", "tracker_unavailable"):
        return "quota_exhausted"
    if gd_res.status in ("disabled", "invalid_timespan", "empty_query"):
        return "skipped_by_policy"
    return "network_error"


@dataclass
class ExternalAggregationResult:
    fact_check_matches: List[FactCheckMatch] = field(default_factory=list)
    news_evidence: List[GdeltArticleItem] = field(default_factory=list)
    google_status: str = "not_queried"
    google_available: bool = False
    google_error: Optional[str] = None
    gdelt_status: str = "not_queried"
    gdelt_error: Optional[str] = None
    gdelt_usage: Optional[GdeltUsageStatus] = None
    has_conflicting_fact_checks: bool = False
    has_stale_fact_checks: bool = False
    gdelt_conflicting_coverage: bool = False
    duplicates_collapsed: int = 0
    supplementary_notes: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    retrieval_attempts: List[RetrievalAttempt] = field(default_factory=list)
    fact_check_directions: Dict[str, str] = field(default_factory=dict)
    gdelt_claim_selections: List[Dict[str, Any]] = field(default_factory=list)
    fact_check_matches_by_claim: Dict[str, List[FactCheckMatch]] = field(default_factory=dict)
    news_evidence_by_claim: Dict[str, List[GdeltArticleItem]] = field(default_factory=dict)
    conflicting_fact_checks_by_claim: Dict[str, bool] = field(default_factory=dict)
    stale_fact_checks_by_claim: Dict[str, bool] = field(default_factory=dict)
    gdelt_conflicting_by_claim: Dict[str, bool] = field(default_factory=dict)
    duplicates_collapsed_by_claim: Dict[str, int] = field(default_factory=dict)
    fact_check_directions_by_claim: Dict[str, Dict[str, str]] = field(default_factory=dict)
    retrieval_attempts_by_claim: Dict[str, List[RetrievalAttempt]] = field(default_factory=dict)


class ExternalEvidenceAggregator:
    """
    Enriches claim & article verification responses with structured third-party Fact Check
    matches and bounded GDELT news coverage discovery while preserving Phase 1 integrity.
    """

    def __init__(
        self,
        fact_check_client: Optional[GoogleFactCheckClient] = None,
        gdelt_client: Optional[GdeltClient] = None,
    ):
        self.fact_check_client = fact_check_client or GoogleFactCheckClient()
        self.gdelt_client = gdelt_client or GdeltClient()

    def enrich_claims(
        self,
        claims: List[str],
        phase1_verdict: Optional[str] = None,  # Deprecated/ignored for prediction-independent retrieval
        *,
        source_label: str = "verification",
        max_fact_check_queries: int = 2,
        max_gdelt_queries: int = 1,
        force_gdelt: bool = False,
        claim_ids: Optional[List[str]] = None,
    ) -> ExternalAggregationResult:
        """
        Backward-compatible wrapper delegating to `collect_independent_external_evidence`.
        Never uses `phase1_verdict` to restrict or alter external queries.
        """
        del phase1_verdict
        return self.collect_independent_external_evidence(
            claims,
            source_label=source_label,
            max_fact_check_queries=max_fact_check_queries,
            max_gdelt_queries=max_gdelt_queries,
            force_gdelt=force_gdelt,
            claim_ids=claim_ids,
        )

    def collect_independent_external_evidence(
        self,
        claims: List[str],
        *,
        source_label: str = "verification",
        max_fact_check_queries: int = 2,
        max_gdelt_queries: int = 1,
        force_gdelt: bool = False,
        gdelt_eligible_claims: Optional[List[str]] = None,
        gdelt_skipped_claims: Optional[List[Any]] = None,
        claim_ids: Optional[List[str]] = None,
    ) -> ExternalAggregationResult:
        """
        Queries external sources for focused claims WITHOUT inspecting any ML prediction/verdict:
          - Google Fact Check: round-robin allocation across all eligible claims (support pass first,
            then contradiction pass), tracking skipped budget queries explicitly by claim_id.
          - GDELT DOC 2.0 (Option A): at most 1 neutral/balanced query per eligible claim (max 2 on articles)
            plus explicit `skipped_static_reference_fact` and budget-skip logging per claim_id.
        """
        from backend.app.utils.logger import logger
        from ml.inference.evidence_quality import build_directional_queries

        agg = ExternalAggregationResult()
        clean_pairs: List[Tuple[str, str]] = []
        claim_id_by_norm: Dict[str, str] = {}
        for idx, raw_cl in enumerate(claims, 1):
            c_txt = re.sub(r"\s+", " ", raw_cl or "").strip()
            if not c_txt:
                continue
            raw_cid = claim_ids[idx - 1] if (claim_ids and idx - 1 < len(claim_ids) and claim_ids[idx - 1]) else f"claim_{len(clean_pairs) + 1}"
            cid = str(raw_cid)
            clean_pairs.append((cid, c_txt))
            claim_id_by_norm.setdefault(c_txt.lower(), cid)
            agg.fact_check_matches_by_claim.setdefault(cid, [])
            agg.news_evidence_by_claim.setdefault(cid, [])
            agg.conflicting_fact_checks_by_claim.setdefault(cid, False)
            agg.stale_fact_checks_by_claim.setdefault(cid, False)
            agg.gdelt_conflicting_by_claim.setdefault(cid, False)
            agg.duplicates_collapsed_by_claim.setdefault(cid, 0)
            agg.fact_check_directions_by_claim.setdefault(cid, {})
            agg.retrieval_attempts_by_claim.setdefault(cid, [])

        if not clean_pairs:
            agg.gdelt_usage = self.gdelt_client.tracker.get_status()
            return agg

        def _record_attempt(attempt: RetrievalAttempt) -> None:
            agg.retrieval_attempts.append(attempt)
            if attempt.claim_id:
                agg.retrieval_attempts_by_claim.setdefault(attempt.claim_id, []).append(attempt)

        # 1. Google Fact Check Tools API (round-robin fair allocation across claims)
        seen_fc_keys = set()
        seen_fc_keys_by_claim: Dict[str, set] = {cid: set() for cid, _ in clean_pairs}
        all_fc_matches: List[FactCheckMatch] = []
        fc_statuses: List[str] = []
        fc_errors: List[str] = []
        fc_available = False
        fc_conflict_sum: Optional[str] = None
        any_fc_conflict = False
        any_fc_stale = False
        first_fc_res_by_claim: Dict[str, GoogleFactCheckResult] = {}

        per_claim_directional: List[Tuple[str, str, str, str]] = []
        for cid, cl in clean_pairs:
            dq = build_directional_queries(cl)
            sup_q = dq.factcheck_support_query or cl[:280]
            con_q = dq.factcheck_contradict_query or build_focused_claim_queries(cl)[1]
            per_claim_directional.append((cid, cl, sup_q, con_q))

        # Round 1: support_oriented across ALL claims, Round 2: contradiction_oriented across ALL claims
        fc_query_plan: List[Tuple[str, str, str, str]] = []  # (claim_id, claim_text, direction, query)
        for cid, cl, sup_q, _ in per_claim_directional:
            if sup_q:
                fc_query_plan.append((cid, cl, "support_oriented", sup_q))
        for cid, cl, sup_q, con_q in per_claim_directional:
            if con_q and con_q.lower() != (sup_q or "").lower():
                fc_query_plan.append((cid, cl, "contradiction_oriented", con_q))

        fc_budget = max(1, int(max_fact_check_queries))
        executed_queries_in_call: Dict[str, GoogleFactCheckResult] = {}
        queries_consumed = 0
        budget_exhausted_fc: List[Tuple[str, str, str, str]] = []

        for cid, cl, fc_dir, fc_q in fc_query_plan:
            q_norm = fc_q.lower()
            if q_norm in executed_queries_in_call:
                fc_res = executed_queries_in_call[q_norm]
                cached_reuse = True
            elif queries_consumed < fc_budget:
                fc_res = self.fact_check_client.search_claims(fc_q, max_results=5)
                executed_queries_in_call[q_norm] = fc_res
                queries_consumed += 1
                cached_reuse = False
            else:
                budget_exhausted_fc.append((cid, cl, fc_dir, fc_q))
                continue

            first_fc_res_by_claim.setdefault(cid, fc_res)
            fc_statuses.append(fc_res.status)
            fc_available = fc_available or fc_res.available
            if fc_res.error_detail:
                fc_errors.append(fc_res.error_detail)
            if fc_res.has_conflicting_reviews:
                any_fc_conflict = True
                agg.conflicting_fact_checks_by_claim[cid] = True
                fc_conflict_sum = fc_res.conflict_summary or fc_conflict_sum
            if fc_res.has_stale_reviews:
                any_fc_stale = True
                agg.stale_fact_checks_by_claim[cid] = True

            _record_attempt(
                RetrievalAttempt(
                    provider="google_fact_check",
                    direction=fc_dir,
                    query=fc_q,
                    outcome="cache_hit" if cached_reuse else _map_fc_outcome(fc_res),
                    available=fc_res.available,
                    from_cache=fc_res.from_cache or cached_reuse,
                    items_retrieved=len(fc_res.matches),
                    relevant_items=len(fc_res.matches),
                    reason=fc_res.error_detail or ("reused_in_batch_query" if cached_reuse else fc_res.status),
                    claim_text=cl,
                    claim_id=cid,
                )
            )

            for m in fc_res.matches:
                dedup_key = ((m.review_url or "").lower(), (m.publisher_name or "").lower(), (m.rating_text or "").lower())
                dir_key = f"{(m.review_url or '')}|{(m.publisher_name or '')}|{(m.review_title or '')}"
                if dedup_key not in seen_fc_keys_by_claim[cid]:
                    seen_fc_keys_by_claim[cid].add(dedup_key)
                    scoped_match = dataclasses.replace(m, claim_id=cid)
                    agg.fact_check_matches_by_claim[cid].append(scoped_match)
                    agg.fact_check_directions_by_claim[cid][dir_key] = fc_dir
                if dedup_key not in seen_fc_keys:
                    seen_fc_keys.add(dedup_key)
                    all_fc_matches.append(dataclasses.replace(m, claim_id=cid))
                    agg.fact_check_directions[dir_key] = fc_dir

        for cid, cl, fc_dir, fc_q in budget_exhausted_fc:
            _record_attempt(
                RetrievalAttempt(
                    provider="google_fact_check",
                    direction=fc_dir,
                    query=fc_q,
                    outcome="skipped_by_policy",
                    available=True,
                    from_cache=False,
                    items_retrieved=0,
                    relevant_items=0,
                    reason=f"skipped_fact_check_query_budget: excluded by max_fact_check_queries={fc_budget} cap",
                    claim_text=cl,
                    claim_id=cid,
                )
            )

        agg.fact_check_matches = all_fc_matches[:8]
        agg.google_available = fc_available
        agg.has_conflicting_fact_checks = any_fc_conflict
        agg.has_stale_fact_checks = any_fc_stale
        agg.google_error = fc_errors[0] if fc_errors and not all_fc_matches else None

        if all_fc_matches:
            agg.google_status = "ok_cached" if all(s == "ok_cached" for s in fc_statuses) else "ok"
        elif fc_statuses:
            agg.google_status = fc_statuses[0]

        # 2. Prediction-independent GDELT DOC 2.0 Discovery (1 neutral query/claim, max 2/article, static guard)
        seen_news_urls = set()
        seen_news_urls_by_claim: Dict[str, set] = {cid: set() for cid, _ in clean_pairs}
        all_news: List[GdeltArticleItem] = []
        gd_statuses: List[str] = []
        gd_errors: List[str] = []
        total_dupes = 0
        logged_gd_skips = set()

        def _log_gd_skip(cid: str, cl_txt: str, reason_str: str, q_str: str) -> None:
            skip_key = (cid, cl_txt.lower())
            if skip_key in logged_gd_skips:
                return
            logged_gd_skips.add(skip_key)
            agg.gdelt_claim_selections.append(
                {"claim_id": cid, "claim": cl_txt, "selected": False, "reason": reason_str, "query": q_str}
            )
            _record_attempt(
                RetrievalAttempt(
                    provider="gdelt",
                    direction="neutral",
                    query=q_str,
                    outcome="skipped_by_policy",
                    available=True,
                    from_cache=False,
                    items_retrieved=0,
                    relevant_items=0,
                    reason=reason_str,
                    claim_text=cl_txt,
                    claim_id=cid,
                )
            )

        if gdelt_skipped_claims:
            for item in gdelt_skipped_claims:
                if len(item) == 3:
                    sk_cid, sk_claim, sk_reason = str(item[0]), str(item[1]), str(item[2])
                else:
                    sk_claim, sk_reason = str(item[0]), str(item[1])
                    sk_cid = claim_id_by_norm.get(re.sub(r"\s+", " ", sk_claim).strip().lower(), "claim_1")
                _, sk_q = build_focused_claim_queries(sk_claim)
                _log_gd_skip(sk_cid, sk_claim, sk_reason, sk_q)

        target_gd_pairs: List[Tuple[str, str]] = []
        if gdelt_eligible_claims is not None:
            for idx, c_raw in enumerate(gdelt_eligible_claims, 1):
                c_txt = re.sub(r"\s+", " ", c_raw or "").strip()
                if c_txt:
                    cid = claim_id_by_norm.get(c_txt.lower(), f"claim_{idx}")
                    target_gd_pairs.append((cid, c_txt))
        else:
            target_gd_pairs = list(clean_pairs)

        gd_budget = max(0, int(max_gdelt_queries))
        for cid, cl in target_gd_pairs[gd_budget:]:
            _, gd_q = build_focused_claim_queries(cl)
            _log_gd_skip(
                cid,
                cl,
                f"skipped_gdelt_query_budget: excluded by max_gdelt_queries={gd_budget} cap",
                gd_q,
            )

        for cid, cl in target_gd_pairs[:gd_budget]:
            _, gd_q = build_focused_claim_queries(cl)
            first_fc_res = first_fc_res_by_claim.get(cid)
            should_run, skip_reason = (True, "forced") if force_gdelt else should_query_gdelt_for_claim(
                cl, fact_check_result=first_fc_res
            )
            if not should_run:
                logged_skip = (
                    "skipped_static_reference_fact"
                    if skip_reason == "resolved_static_reference_fact"
                    else skip_reason
                )
                logger.info(f"GDELT query skipped ({logged_skip}) cleanly (prediction-independent).")
                gd_statuses.append(logged_skip)
                _log_gd_skip(cid, cl, logged_skip, gd_q)
                continue

            gd_res: GdeltSearchResult = self.gdelt_client.search_coverage(
                gd_q,
                source_label=source_label,
            )
            gd_statuses.append(gd_res.status)
            total_dupes += gd_res.duplicates_collapsed
            agg.duplicates_collapsed_by_claim[cid] = agg.duplicates_collapsed_by_claim.get(cid, 0) + gd_res.duplicates_collapsed
            if gd_res.usage:
                agg.gdelt_usage = gd_res.usage
            if gd_res.error_detail:
                gd_errors.append(gd_res.error_detail)

            agg.gdelt_claim_selections.append(
                {
                    "claim_id": cid,
                    "claim": cl,
                    "selected": True,
                    "reason": "selected_central_claim",
                    "query": gd_q,
                    "status": gd_res.status,
                }
            )
            _record_attempt(
                RetrievalAttempt(
                    provider="gdelt",
                    direction="neutral",
                    query=gd_q,
                    outcome=_map_gdelt_outcome(gd_res),
                    available=gd_res.status not in ("quota_exhausted", "tracker_unavailable", "timeout", "connect_timeout", "read_timeout", "network_error"),
                    from_cache=gd_res.from_cache,
                    items_retrieved=len(gd_res.articles),
                    relevant_items=len(gd_res.articles),
                    reason=gd_res.error_detail or gd_res.status,
                    claim_text=cl,
                    claim_id=cid,
                )
            )

            for art in gd_res.articles:
                url_key = art.url.lower()
                if url_key not in seen_news_urls_by_claim[cid]:
                    seen_news_urls_by_claim[cid].add(url_key)
                    agg.news_evidence_by_claim[cid].append(dataclasses.replace(art, claim_id=cid))
                if url_key in seen_news_urls:
                    total_dupes += 1
                    continue
                seen_news_urls.add(url_key)
                all_news.append(dataclasses.replace(art, claim_id=cid))

            gd_c_tension, _ = _detect_gdelt_coverage_tension(agg.news_evidence_by_claim[cid])
            if gd_c_tension:
                agg.gdelt_conflicting_by_claim[cid] = True

        if agg.gdelt_usage is None:
            agg.gdelt_usage = self.gdelt_client.tracker.get_status()

        agg.news_evidence = all_news[:10]
        agg.duplicates_collapsed = total_dupes
        if all_news:
            agg.gdelt_status = "ok_cached" if all(s == "ok_cached" for s in gd_statuses) else "ok"
        elif gd_statuses:
            agg.gdelt_status = gd_statuses[0]
        agg.gdelt_error = gd_errors[0] if gd_errors and not all_news else None

        has_gd_tension, gd_tension_note = _detect_gdelt_coverage_tension(agg.news_evidence)
        agg.gdelt_conflicting_coverage = has_gd_tension

        # 3. Build clear non-authoritative supplementary notes & limitations
        if any_fc_conflict and fc_conflict_sum:
            agg.supplementary_notes.append(f"Conflicting External Fact-Checks: {fc_conflict_sum}")
        if any_fc_stale:
            agg.supplementary_notes.append(
                "Stale Fact-Check Warning: One or more third-party fact-check reviews may precede recent developments or post-review years."
            )
        if has_gd_tension and gd_tension_note:
            agg.supplementary_notes.append(gd_tension_note)
        if total_dupes > 0:
            agg.supplementary_notes.append(
                f"GDELT deduplication collapsed {total_dupes} duplicate/syndicated article reference(s); repeated copies are never counted as independent corroboration."
            )

        if agg.gdelt_usage and agg.gdelt_usage.limit_reached:
            agg.limitations.append(
                f"Shared GDELT request allowance reached ({agg.gdelt_usage.requests_used}/{agg.gdelt_usage.allowance_limit}); further outbound GDELT discovery is blocked fail-closed."
            )
        elif agg.gdelt_usage and agg.gdelt_usage.warning_active:
            agg.limitations.append(
                f"GDELT quota warning: {agg.gdelt_usage.requests_remaining} of {agg.gdelt_usage.allowance_limit} shared requests remaining."
            )

        agg.limitations.append(
            "Google Fact Check results reflect attributed third-party ClaimReviews (not independent verification by Google or this system), and GDELT DOC 2.0 articles represent media coverage metadata rather than factual proof."
        )
        return agg
