"""
ml/inference/second_pass_synthesizer.py

Second-Pass Verdict Evaluator & Evidence Audit Trail Generator for the
Independent Evidence Verification Engine (IEVE).

Enforces architectural decisions and corrections:
  - Decision 1 (Modified Option A): LIAR BERT and ISOT BERT recorded separately with raw
    prediction, logits, probabilities, and applicable input type (never combined into a
    universal score; never filter retrieval). DeBERTa FEVER NLI operates strictly in the
    post-retrieval claim-evidence evaluation stage.
  - Decision 3 & Mandatory Correction 1 (Tiered Provenance & Sufficiency):
      * Tier 1: Official first-party records & institutional documents (potential single-source
        certification when all 6 strict criteria hold; NOT supplied by current 4 channels).
      * Tier 2: Wikipedia & 2017 FEVER snapshot (secondary encyclopedic only; NEVER automatically
        qualifies for single-source primary-authority certification; claims requiring an official
        primary record return cautious/UNVERIFIED when no Tier 1 record exists).
      * Tier 3: Single Google Fact Check ClaimReviews, GDELT headlines, syndicated copies
        (NEVER force GENUINE or FAKE alone; corroborated multi-publisher Fact Checks may assist).
  - Mandatory Correction 2 (Retrieval Attempt Telemetry): Records provider, direction, query,
    outcome taxonomy (`success_with_results`, `no_results`, `cache_hit`, `timeout`,
    `network_error`, `quota_exhausted`, `skipped_by_policy`, `unavailable_no_api_key`),
    cache status, counts, and reason without treating failed/skipped lookups as negative proof.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from ml.inference.claim_verifier import VerifiedEvidence
from ml.inference.evidence_alignment import claim_asserts_current_state
from ml.inference.evidence_quality import (
    BROADCASTER_NETWORKS,
    DirectionalQueries,
    EvidenceQualityAssessment,
    SOURCE_METHODOLOGY_NOTE,
    TIER_1_PRIMARY_OFFICIAL,
    TIER_2_SECONDARY_ENCYCLOPEDIC,
    TIER_3_SECONDARY_OR_METADATA,
    claim_requires_official_primary_record,
    evaluate_documentary_evidence,
    evaluate_fact_check_quality,
    evaluate_gdelt_article_quality,
)
from ml.inference.verdict_synthesizer import ABSOLUTE_FRAMING_WORDS, SynthesisResult


@dataclass
class ModelSignalRecord:
    model_name: str
    dataset_origin: str
    applicable_input_type: str  # short_claim | full_article
    applicable: bool
    prediction: Optional[str] = None
    confidence: Optional[float] = None
    probabilities: Dict[str, float] = field(default_factory=dict)
    raw_logits: Dict[str, float] = field(default_factory=dict)
    preliminary_verdict_tag: Optional[str] = None
    disclaimer: str = ""


@dataclass
class InitialMLSignals:
    liar_signal: ModelSignalRecord
    isot_signal: ModelSignalRecord
    preliminary_verdict: str  # Non-binding single-model baseline for verdict-change comparison
    note: str = (
        "LIAR BERT and ISOT BERT are recorded separately as exploratory preliminary linguistic signals. "
        "They are NOT combined into a universal confidence score and NEVER filter evidence retrieval."
    )


@dataclass
class DebertaNLISummary:
    model_name: str = "MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli (fever_verifier_v1)"
    evaluation_stage: str = "post_retrieval_claim_evidence_pair"
    pairs_evaluated: int = 0
    raw_label_counts: Dict[str, int] = field(default_factory=dict)
    calibrated_label_counts: Dict[str, int] = field(default_factory=dict)
    max_raw_probability: float = 0.0
    disclaimer: str = (
        "DeBERTa FEVER NLI operates strictly during post-retrieval evaluation on (claim, evidence) pairs. "
        "It is not an independent text-only initial prediction or an empirical truth probability."
    )


@dataclass
class RetrievalAttemptRecord:
    provider: str
    direction: str  # support_oriented | contradiction_oriented | neutral
    query: str
    outcome: str    # success_with_results | no_results | cache_hit | timeout | network_error | quota_exhausted | skipped_by_policy | unavailable_no_api_key
    available: bool
    from_cache: bool = False
    items_retrieved: int = 0
    relevant_items: int = 0
    reason: Optional[str] = None
    claim_text: Optional[str] = None
    claim_id: Optional[str] = None


@dataclass
class ProviderStatusRecord:
    provider: str
    status: str
    available: bool
    items_retrieved: int
    relevant_items: int
    error_or_reason: Optional[str] = None


@dataclass
class EvidenceQualitySummary:
    support_count: int
    contradict_count: int
    neutral_count: int
    independent_supporting_sources: int
    independent_contradicting_sources: int
    rejected_irrelevant_count: int
    syndicated_duplicates_collapsed: int
    max_support_quality: float
    max_contradict_quality: float
    temporal_mismatch_detected: bool
    geographic_mismatch_detected: bool
    tier1_official_primary_count: int = 0
    tier2_encyclopedic_count: int = 0
    tier3_secondary_or_metadata_count: int = 0
    primary_official_sources_available: bool = False
    claim_requires_primary_record: bool = False
    primary_record_need_reason: Optional[str] = None
    methodology_note: str = SOURCE_METHODOLOGY_NOTE


@dataclass
class EvidenceAuditTrail:
    initial_ml_signals: InitialMLSignals
    nli_evaluation: DebertaNLISummary
    directions_executed: List[str]
    queries_by_direction: Dict[str, str]
    retrieval_attempts: List[RetrievalAttemptRecord]
    supporting_evidence: List[EvidenceQualityAssessment]
    contradicting_evidence: List[EvidenceQualityAssessment]
    neutral_evidence: List[EvidenceQualityAssessment]
    rejected_irrelevant_evidence: List[EvidenceQualityAssessment]
    conflicts_detected: bool
    conflict_details: List[str]
    provider_statuses: List[ProviderStatusRecord]
    unavailable_providers: List[str]
    evidence_quality_summary: EvidenceQualitySummary
    second_pass_decision: str  # confirmed_initial | overridden_by_evidence | downgraded_uncertainty | abstained_insufficient
    verdict_changed_from_initial: bool
    verdict_change_reason: Optional[str]
    second_pass_reasoning: str
    final_verdict: str
    final_confidence: float
    limitations: List[str] = field(default_factory=list)
    total_retrieval_attempts: int = 0
    omitted_retrieval_attempts: int = 0


def map_classifier_to_preliminary_verdict(
    *,
    liar_prediction: Optional[str] = None,
    isot_prediction: Optional[str] = None,
) -> str:
    """
    Maps a single classifier output to a preliminary tag for post-evaluation comparison only.
    Never used to gate retrieval or combine models.
    """
    if liar_prediction:
        lp = liar_prediction.strip().lower()
        if lp in ("true", "mostly-true"):
            return "GENUINE"
        if lp in ("pants-fire", "false"):
            return "FAKE"
        if lp in ("barely-true", "half-true"):
            return "MISLEADING"
    if isot_prediction:
        ip = isot_prediction.strip().upper()
        if ip == "REAL":
            return "GENUINE"
        if ip == "FAKE":
            return "FAKE"
    return "UNVERIFIED"


_UNAVAILABLE_WIKI_STATES = {"timeout", "offline", "error_fallback", "disabled", "blocked_domain", "invalid_response"}
_UNAVAILABLE_GOOGLE_STATES = {
    "unavailable_no_api_key", "auth_error", "rate_limited", "timeout",
    "http_error", "network_error", "invalid_response", "disabled",
}
_UNAVAILABLE_GDELT_STATES = {
    "quota_exhausted", "tracker_unavailable", "connect_timeout", "read_timeout",
    "timeout", "rate_limited", "http_error", "network_error", "invalid_response",
    "disabled", "invalid_timespan",
}


def _map_wiki_status_to_outcome(wiki_status: str, items_cnt: int, from_cache: bool = False) -> str:
    if wiki_status in ("cache_hit", "ok_cached") or (from_cache and wiki_status in ("ok", "ok_cached", "cache_hit")):
        return "cache_hit"
    if wiki_status == "timeout":
        return "timeout"
    if wiki_status in ("offline", "error_fallback", "blocked_domain", "invalid_response"):
        return "network_error"
    if wiki_status in ("disabled", "not_needed"):
        return "skipped_by_policy"
    return "success_with_results" if items_cnt > 0 else "no_results"


class SecondPassEvaluator:
    """
    Performs rigorous prediction-independent Second-Pass synthesis integrating:
      - Separate exploratory Initial ML signals (recorded for audit transparency only)
      - Post-retrieval DeBERTa FEVER NLI claim-evidence pair assessments
      - Multi-dimensional Tiered Evidence Quality & Provenance rules
      - Explicit retrieval attempt & provider failure handling
    """

    def evaluate(
        self,
        *,
        claim: str,
        initial_signals: InitialMLSignals,
        directional_queries: DirectionalQueries,
        documentary_evidence: List[VerifiedEvidence],
        phase1_synthesis: SynthesisResult,
        fact_check_matches: Optional[List[Any]] = None,
        news_evidence: Optional[List[Any]] = None,
        retrieval_meta: Optional[Dict[str, Any]] = None,
        external_meta: Optional[Dict[str, Any]] = None,
        claim_id: Optional[str] = None,
    ) -> Tuple[SynthesisResult, EvidenceAuditTrail]:
        now_iso = datetime.now(timezone.utc).isoformat()
        ret_meta = retrieval_meta or {}
        ext_meta = external_meta or {}
        fc_list = list(fact_check_matches or [])
        news_list = list(news_evidence or [])

        # 1. Post-retrieval DeBERTa FEVER NLI stage summary (strictly claim-evidence pair stage)
        raw_counts: Dict[str, int] = {"SUPPORTS": 0, "REFUTES": 0, "NOT ENOUGH INFO": 0}
        cal_counts: Dict[str, int] = {"SUPPORTS": 0, "REFUTES": 0, "NOT ENOUGH INFO": 0}
        max_nli_prob = 0.0
        for ve in documentary_evidence:
            raw_lbl = getattr(ve, "raw_nli_label", ve.nli_label)
            raw_counts[raw_lbl] = raw_counts.get(raw_lbl, 0) + 1
            max_nli_prob = max(max_nli_prob, float(ve.nli_confidence))

        # 2. Evaluate quality dimensions across ALL candidate sources uniformly
        all_assessments: List[EvidenceQualityAssessment] = []
        for ve in documentary_evidence:
            item_q = evaluate_documentary_evidence(
                claim,
                ve,
                retrieval_direction=getattr(ve, "retrieval_direction", "neutral"),
                retrieved_at=now_iso,
            )
            cal_counts[item_q.ml_nli_label] = cal_counts.get(item_q.ml_nli_label, 0) + 1
            all_assessments.append(item_q)

        nli_summary = DebertaNLISummary(
            pairs_evaluated=len(documentary_evidence),
            raw_label_counts=raw_counts,
            calibrated_label_counts=cal_counts,
            max_raw_probability=round(max_nli_prob, 4),
        )

        fc_dir_map: Dict[str, str] = dict(ext_meta.get("fact_check_directions") or {})
        for m in fc_list:
            m_key = f"{(getattr(m, 'review_url', '') or '')}|{(getattr(m, 'publisher_name', '') or '')}|{(getattr(m, 'review_title', '') or '')}"
            fc_dir = fc_dir_map.get(m_key, "neutral")
            all_assessments.append(evaluate_fact_check_quality(claim, m, retrieval_direction=fc_dir))
        for art in news_list:
            all_assessments.append(evaluate_gdelt_article_quality(claim, art, retrieval_direction="neutral"))

        relevant_items = [a for a in all_assessments if a.is_relevant]
        rejected_items = [a for a in all_assessments if not a.is_relevant]

        sup_items = [a for a in relevant_items if a.stance == "supporting"]
        con_items = [a for a in relevant_items if a.stance == "contradicting"]
        neu_items = [a for a in relevant_items if a.stance == "neutral"]

        ind_sup_groups = {a.independent_group_key for a in sup_items}
        ind_con_groups = {a.independent_group_key for a in con_items}

        syndicated_collapsed = int(ext_meta.get("duplicates_collapsed", 0))
        for art in news_list:
            sc = int(getattr(art, "syndicated_count", 1))
            if sc > 1:
                syndicated_collapsed = max(syndicated_collapsed, sc - 1)

        temp_mismatch = any(
            a.temporal_status in ("historical_end_detected", "stale_2017_snapshot_for_current_claim", "stale_review")
            for a in relevant_items
        )
        geo_mismatch = any(a.geographic_status.startswith("mismatch") for a in all_assessments)

        t1_count = sum(1 for a in relevant_items if a.evidence_tier == TIER_1_PRIMARY_OFFICIAL)
        t2_count = sum(1 for a in relevant_items if a.evidence_tier == TIER_2_SECONDARY_ENCYCLOPEDIC)
        t3_count = sum(1 for a in relevant_items if a.evidence_tier == TIER_3_SECONDARY_OR_METADATA)
        needs_primary, primary_need_reason = claim_requires_official_primary_record(claim)

        quality_summary = EvidenceQualitySummary(
            support_count=len(sup_items),
            contradict_count=len(con_items),
            neutral_count=len(neu_items),
            independent_supporting_sources=len(ind_sup_groups),
            independent_contradicting_sources=len(ind_con_groups),
            rejected_irrelevant_count=len(rejected_items),
            syndicated_duplicates_collapsed=syndicated_collapsed,
            max_support_quality=max((a.overall_quality_score for a in sup_items), default=0.0),
            max_contradict_quality=max((a.overall_quality_score for a in con_items), default=0.0),
            temporal_mismatch_detected=temp_mismatch,
            geographic_mismatch_detected=geo_mismatch,
            tier1_official_primary_count=t1_count,
            tier2_encyclopedic_count=t2_count,
            tier3_secondary_or_metadata_count=t3_count,
            primary_official_sources_available=(t1_count > 0),
            claim_requires_primary_record=needs_primary,
            primary_record_need_reason=primary_need_reason,
        )

        # 3. Build explicit provider statuses & per-attempt telemetry (failures != negative evidence)
        fever_items = [a for a in all_assessments if a.source_type == "fever_local"]
        wiki_items = [a for a in all_assessments if a.source_type == "wikipedia_live"]
        fc_items = [a for a in all_assessments if a.source_type == "google_fact_check"]
        gdelt_items = [a for a in all_assessments if a.source_type == "gdelt"]

        wiki_status = str(ret_meta.get("wikipedia_status", "not_needed"))
        google_status = str(ext_meta.get("google_status", "not_queried"))
        gdelt_status = str(ext_meta.get("gdelt_status", "not_queried"))

        provider_statuses = [
            ProviderStatusRecord(
                provider="fever_local",
                status="ok" if fever_items else "no_results",
                available=True,
                items_retrieved=len(fever_items),
                relevant_items=sum(1 for a in fever_items if a.is_relevant),
            ),
            ProviderStatusRecord(
                provider="wikipedia_live",
                status=wiki_status,
                available=wiki_status not in _UNAVAILABLE_WIKI_STATES,
                items_retrieved=len(wiki_items),
                relevant_items=sum(1 for a in wiki_items if a.is_relevant),
                error_or_reason=f"Wikipedia fallback status: {wiki_status}" if wiki_status in _UNAVAILABLE_WIKI_STATES else None,
            ),
            ProviderStatusRecord(
                provider="google_fact_check",
                status=google_status,
                available=google_status not in _UNAVAILABLE_GOOGLE_STATES,
                items_retrieved=len(fc_items),
                relevant_items=sum(1 for a in fc_items if a.is_relevant),
                error_or_reason=ext_meta.get("google_error") or (f"Provider status: {google_status}" if google_status in _UNAVAILABLE_GOOGLE_STATES else None),
            ),
            ProviderStatusRecord(
                provider="gdelt",
                status=gdelt_status,
                available=gdelt_status not in _UNAVAILABLE_GDELT_STATES,
                items_retrieved=len(gdelt_items),
                relevant_items=sum(1 for a in gdelt_items if a.is_relevant),
                error_or_reason=ext_meta.get("gdelt_error") or (f"Provider status: {gdelt_status}" if gdelt_status in _UNAVAILABLE_GDELT_STATES else None),
            ),
        ]
        unavailable_providers = [p.provider for p in provider_statuses if not p.available]

        # Build unified retrieval_attempts across local FAISS, Wikipedia, Google Fact Check, and GDELT
        rel_counts_by_prov_dir: Dict[Tuple[str, str], int] = {}
        for a in all_assessments:
            if a.is_relevant:
                key = (a.source_type, a.retrieval_direction)
                rel_counts_by_prov_dir[key] = rel_counts_by_prov_dir.get(key, 0) + 1

        attempt_records: List[RetrievalAttemptRecord] = []
        raw_local_attempts = list(ret_meta.get("local_attempts") or [])
        wiki_cached_flag = bool(ret_meta.get("wikipedia_from_cache", False)) or wiki_status in ("cache_hit", "ok_cached")
        if raw_local_attempts:
            for la in raw_local_attempts:
                prov = str(la.get("provider", "fever_local"))
                dir_tag = str(la.get("direction", "neutral"))
                la_out = str(la.get("outcome", "no_results"))
                la_cached = bool(la.get("from_cache", False)) or la_out == "cache_hit"
                if prov == "wikipedia_live" and la_cached and la_out == "success_with_results":
                    la_out = "cache_hit"
                attempt_records.append(
                    RetrievalAttemptRecord(
                        provider=prov,
                        direction=dir_tag,
                        query=str(la.get("query", claim)),
                        outcome=la_out,
                        available=bool(la.get("available", True)),
                        from_cache=la_cached,
                        items_retrieved=int(la.get("items_retrieved", 0)),
                        relevant_items=rel_counts_by_prov_dir.get((prov, dir_tag), 0),
                        reason=la.get("reason"),
                        claim_text=la.get("claim_text") or claim,
                        claim_id=la.get("claim_id") or claim_id,
                    )
                )
        else:
            # Synthesize baseline local attempt summary when ret_meta came from lightweight test stub
            attempt_records.append(
                RetrievalAttemptRecord(
                    provider="fever_local",
                    direction="neutral",
                    query=directional_queries.neutral_query or claim,
                    outcome="success_with_results" if fever_items else "no_results",
                    available=True,
                    items_retrieved=len(fever_items),
                    relevant_items=sum(1 for a in fever_items if a.is_relevant),
                    reason="local_faiss_126k_search",
                    claim_text=claim,
                    claim_id=claim_id,
                )
            )
            wiki_out = _map_wiki_status_to_outcome(wiki_status, len(wiki_items), from_cache=wiki_cached_flag)
            attempt_records.append(
                RetrievalAttemptRecord(
                    provider="wikipedia_live",
                    direction="support_oriented",
                    query=claim,
                    outcome=wiki_out,
                    available=wiki_status not in _UNAVAILABLE_WIKI_STATES,
                    from_cache=wiki_cached_flag or wiki_out == "cache_hit",
                    items_retrieved=len(wiki_items),
                    relevant_items=sum(1 for a in wiki_items if a.is_relevant),
                    reason=wiki_status,
                    claim_text=claim,
                    claim_id=claim_id,
                )
            )

        for ea in list(ext_meta.get("retrieval_attempts") or []):
            if isinstance(ea, RetrievalAttemptRecord):
                prov = ea.provider
                dir_tag = ea.direction
                attempt_records.append(
                    RetrievalAttemptRecord(
                        provider=prov,
                        direction=dir_tag,
                        query=ea.query,
                        outcome=ea.outcome,
                        available=ea.available,
                        from_cache=ea.from_cache,
                        items_retrieved=ea.items_retrieved,
                        relevant_items=rel_counts_by_prov_dir.get((prov, dir_tag), ea.relevant_items),
                        reason=ea.reason,
                        claim_text=ea.claim_text,
                        claim_id=ea.claim_id or claim_id,
                    )
                )
            else:
                prov = str(getattr(ea, "provider", ea.get("provider") if isinstance(ea, dict) else ""))
                dir_tag = str(getattr(ea, "direction", ea.get("direction") if isinstance(ea, dict) else "neutral"))
                q_val = str(getattr(ea, "query", ea.get("query") if isinstance(ea, dict) else ""))
                out_val = str(getattr(ea, "outcome", ea.get("outcome") if isinstance(ea, dict) else "no_results"))
                avail_val = bool(getattr(ea, "available", ea.get("available") if isinstance(ea, dict) else True))
                cache_val = bool(getattr(ea, "from_cache", ea.get("from_cache") if isinstance(ea, dict) else False))
                cnt_val = int(getattr(ea, "items_retrieved", ea.get("items_retrieved") if isinstance(ea, dict) else 0))
                rel_val = getattr(ea, "relevant_items", ea.get("relevant_items") if isinstance(ea, dict) else None)
                rsn_val = getattr(ea, "reason", ea.get("reason") if isinstance(ea, dict) else None)
                ct_val = getattr(ea, "claim_text", ea.get("claim_text") if isinstance(ea, dict) else claim)
                cid_val = getattr(ea, "claim_id", ea.get("claim_id") if isinstance(ea, dict) else claim_id) or claim_id
                attempt_records.append(
                    RetrievalAttemptRecord(
                        provider=prov,
                        direction=dir_tag,
                        query=q_val,
                        outcome=out_val,
                        available=avail_val,
                        from_cache=cache_val,
                        items_retrieved=cnt_val,
                        relevant_items=rel_counts_by_prov_dir.get((prov, dir_tag), int(rel_val if rel_val is not None else cnt_val)),
                        reason=rsn_val,
                        claim_text=ct_val,
                        claim_id=cid_val,
                    )
                )

        # 4. Partition evidence strictly by provenance tier and canonical underlying sources
        tier1_sup = [
            a for a in sup_items
            if a.is_official_primary and not a.is_stale and a.overall_quality_score >= 0.60
        ]
        tier1_con = [
            a for a in con_items
            if a.is_official_primary and not a.is_stale and a.contradiction_strength >= 0.55 and a.overall_quality_score >= 0.60
        ]
        ind_tier1_sup = {a.independent_group_key for a in tier1_sup}
        ind_tier1_con = {a.independent_group_key for a in tier1_con}

        tier2_sup = [
            a for a in sup_items
            if a.is_secondary_encyclopedic and not a.is_stale and a.overall_quality_score >= 0.55 and a.evidence_specificity >= 0.48
        ]
        has_live_active_support = any(a.source_type == "wikipedia_live" for a in tier2_sup) or bool(tier1_sup)
        is_current = claim_asserts_current_state(claim)
        claim_yrs = set(re.findall(r"\b(?:1[5-9]\d{2}|20\d{2})\b", claim))
        has_exact_year_sup = bool(
            claim_yrs
            and any(
                (a.is_official_primary or a.is_secondary_encyclopedic)
                and a.subject_entity_alignment >= 0.65
                and claim_yrs.issubset(set(re.findall(r"\b(?:1[5-9]\d{2}|20\d{2})\b", a.text_excerpt)))
                for a in sup_items
            )
        )
        tier2_con = [
            a for a in con_items
            if a.is_secondary_encyclopedic
            and a.overall_quality_score >= 0.55
            and a.contradiction_strength >= 0.55
            and a.evidence_specificity >= 0.48
            # Prior historical tenure is background context when Tier 1 or live Wikipedia confirms active ongoing tenure
            and not (
                is_current
                and has_live_active_support
                and a.symbolic_alignment is not None
                and a.symbolic_alignment.shows_historical_end
                and not a.symbolic_alignment.has_exclusive_slot_conflict
                and not a.symbolic_alignment.has_negation_conflict
            )
            # Secondary non-exclusive dates on related missions/events do not negate an exact-year corroborated claim
            and not (
                has_exact_year_sup
                and a.symbolic_alignment is not None
                and a.symbolic_alignment.has_numeric_conflict
                and not a.symbolic_alignment.has_exclusive_slot_conflict
                and not a.symbolic_alignment.has_negation_conflict
            )
        ]
        ind_tier2_sup = {a.independent_group_key for a in tier2_sup}
        ind_tier2_con = {a.independent_group_key for a in tier2_con}

        credible_fc_sup = [a for a in sup_items if a.source_type == "google_fact_check" and not a.is_stale and a.overall_quality_score >= 0.50]
        credible_fc_con = [a for a in con_items if a.source_type == "google_fact_check" and not a.is_stale and a.overall_quality_score >= 0.50]
        ind_fc_con_publishers = {a.independent_group_key for a in credible_fc_con}
        ind_fc_sup_publishers = {a.independent_group_key for a in credible_fc_sup}

        has_relevant_fc = any(a.is_relevant for a in fc_items)
        fc_meta_conflict = (
            bool(ext_meta.get("has_conflicting_fact_checks"))
            if (not fc_items or (has_relevant_fc and (credible_fc_sup or credible_fc_con)))
            else False
        )
        tier1_sup_single_fc_only = bool(tier1_sup and not tier1_con and not tier2_con and len(ind_fc_con_publishers) == 1)
        tier1_con_single_fc_only = bool(tier1_con and not tier1_sup and not tier2_sup and len(ind_fc_sup_publishers) == 1)

        conflict_details: List[str] = []
        if fc_meta_conflict or (credible_fc_sup and credible_fc_con):
            conflict_details.append("Third-party Google Fact Check publishers reported disagreeing ratings for this claim.")
        if ext_meta.get("gdelt_conflicting_coverage") or (
            any(a.source_type == "gdelt" for a in sup_items) and any(a.source_type == "gdelt" for a in con_items)
        ):
            conflict_details.append("GDELT headlines contain contrasting affirmative vs. skeptical/denying framing.")
        if (tier1_sup or tier2_sup) and (tier1_con or tier2_con):
            conflict_details.append("Retrieved supporting and contradicting passages are in unresolved conflict.")
        if (tier1_sup or tier2_sup) and len(ind_fc_con_publishers) >= 1:
            if tier1_sup_single_fc_only:
                conflict_details.append(
                    "One third-party Google Fact Check review disagreed with qualifying Tier 1 official primary evidence; single Tier 3 review logged without overturning Tier 1 authority."
                )
            else:
                conflict_details.append("Encyclopedic/documentary support conflicts with external fact-check contradiction review(s).")
        if (tier1_con or tier2_con) and len(ind_fc_sup_publishers) >= 1:
            if tier1_con_single_fc_only:
                conflict_details.append(
                    "One third-party Google Fact Check review disagreed with qualifying Tier 1 official contradiction; single Tier 3 review logged without overturning Tier 1 authority."
                )
            else:
                conflict_details.append("Encyclopedic/documentary contradiction conflicts with external supporting fact-check review(s).")
        if ext_meta.get("has_stale_fact_checks"):
            conflict_details.append("One or more third-party ClaimReviews may be stale relative to current claim context.")

        conflicts_detected = bool(conflict_details) or phase1_synthesis.conflicting_evidence_detected

        # 5. Documented Second-Pass Verdict Resolution Precedence:
        #   1) Primary-record requirement gate (with >=2 independent ClaimReview hoax-refutation override -> FAKE)
        #   2) Unresolved credible conflict gate -> UNVERIFIED (evaluated BEFORE OUTDATED/MISLEADING/GENUINE/FAKE,
        #      while preserving Tier 1 against a single Tier 3 review and preserving resolved OUTDATED/MISLEADING framing)
        #   3) Resolved OUTDATED / MISLEADING framing (requires relevant Tier 1/2 historical-end or contradiction alignment;
        #      evaluated BEFORE stale-2017 snapshot guard so established pre-snapshot closures stay OUTDATED offline)
        #   4) Stale-only 2017 snapshot guard -> UNVERIFIED (rejects GENUINE supported solely by 2017 FEVER without live confirmation)
        #   5) Tiered Support Sufficiency (Case E: Tier 1 OR >=2 genuinely independent sources including Tier 2; NEVER 1 Tier 2 source or Tier 3 alone)
        #   6) Tiered Contradiction Sufficiency (Case F: Tier 1 OR >=2 independent sources OR explicit Tier 2 symbolic refutation)
        #   7) Multi-publisher Tier 3 ClaimReview consensus refutation fallback (Case G -> FAKE) / cautious UNVERIFIED
        limitations = list(phase1_synthesis.limitations)
        if SOURCE_METHODOLOGY_NOTE not in limitations:
            limitations.append(SOURCE_METHODOLOGY_NOTE)
        if not (tier1_sup or tier1_con):
            no_primary_note = (
                "No Tier 1 official first-party or institutional documents were available across the four configured "
                "secondary/metadata sources (FEVER snapshot, Wikipedia API, Google Fact Check, GDELT)."
            )
            if no_primary_note not in limitations:
                limitations.append(no_primary_note)

        final_verdict = phase1_synthesis.verdict
        final_conf = phase1_synthesis.confidence_score
        final_expl = phase1_synthesis.explanation
        final_uncert = phase1_synthesis.uncertainty_explanation
        strongest_page = phase1_synthesis.strongest_evidence_page
        reasoning_parts: List[str] = []

        only_stale_2017_support = (
            is_current
            and bool(documentary_evidence)
            and all(a.source_type == "fever_local" for a in sup_items if a.is_secondary_encyclopedic)
            and any(a.is_stale for a in all_assessments if a.is_secondary_encyclopedic)
            and wiki_status in _UNAVAILABLE_WIKI_STATES.union({"not_needed", "no_results"})
        )

        has_historical_end = any(
            a.symbolic_alignment is not None and a.symbolic_alignment.shows_historical_end
            for a in relevant_items
        )
        claim_tokens_lc = set(re.findall(r"[a-z0-9]+", claim.lower()))
        claim_nets = claim_tokens_lc.intersection(BROADCASTER_NETWORKS)
        has_resolved_broadcaster_swap = bool(claim_nets) and any(
            (set(re.findall(r"[a-z0-9]+", a.text_excerpt.lower())).intersection(BROADCASTER_NETWORKS))
            and not (claim_nets & set(re.findall(r"[a-z0-9]+", a.text_excerpt.lower())).intersection(BROADCASTER_NETWORKS))
            for a in con_items
            if a.is_official_primary or a.is_secondary_encyclopedic
        )
        has_resolved_absolute_distortion = bool(claim_tokens_lc & ABSOLUTE_FRAMING_WORDS) and any(
            a.is_official_primary or a.is_secondary_encyclopedic for a in con_items
        )
        has_resolved_distortion = has_resolved_broadcaster_swap or has_resolved_absolute_distortion

        fc_both_sides = bool(credible_fc_sup and credible_fc_con)
        tier1_conflict = bool(
            (tier1_sup and (tier1_con or tier2_con or len(ind_fc_con_publishers) >= 2))
            or (tier1_con and (tier1_sup or tier2_sup or len(ind_fc_sup_publishers) >= 2))
        )
        fc_external_vs_doc_conflict = bool(
            (tier2_sup and credible_fc_con and not (phase1_synthesis.verdict == "OUTDATED" and has_historical_end))
            or (tier2_con and credible_fc_sup)
        )
        doc_internal_unresolved = bool(
            tier2_sup
            and tier2_con
            and not (phase1_synthesis.verdict == "OUTDATED" and has_historical_end)
            and not (phase1_synthesis.verdict == "MISLEADING" and has_resolved_distortion)
            and not tier1_sup
            and not tier1_con
        )
        outdated_vs_active_conflict = bool(
            phase1_synthesis.verdict == "OUTDATED"
            and (fc_both_sides or fc_meta_conflict or bool(credible_fc_sup) or (tier1_sup and (tier1_con or tier2_con)))
        )
        misleading_unresolved_conflict = bool(
            phase1_synthesis.verdict == "MISLEADING"
            and not tier1_con
            and not has_resolved_distortion
            and (fc_both_sides or fc_meta_conflict or (tier2_sup and tier2_con))
        )
        has_unresolved_conflict = bool(
            not tier1_sup_single_fc_only
            and not tier1_con_single_fc_only
            and (
                tier1_conflict
                or fc_both_sides
                or fc_external_vs_doc_conflict
                or doc_internal_unresolved
                or (fc_meta_conflict and not (tier1_sup or tier1_con))
                or outdated_vs_active_conflict
                or misleading_unresolved_conflict
            )
        )

        # Case 0: Institutional / Official Primary Record Required & Zero Tier 1 Records Available
        if needs_primary and not (tier1_sup or tier1_con):
            if (
                len(ind_fc_con_publishers) >= 2
                and not tier2_sup
                and not credible_fc_sup
                and not fc_meta_conflict
            ):
                best_fc = max(credible_fc_con, key=lambda x: x.overall_quality_score)
                if best_fc.overall_quality_score >= 0.62 and best_fc.subject_entity_alignment >= 0.65:
                    final_verdict = "FAKE"
                    final_conf = 0.72
                    strongest_page = best_fc.title_or_page
                    final_expl = (
                        f"Multi-source external fact-check refutation: {len(ind_fc_con_publishers)} independent fact-checking publishers "
                        "explicitly debunked this institutional/primary-record claim (Tier 1 official records unavailable)."
                    )
                    reasoning_parts.append(
                        f"Tier 1 official primary record unavailable, but {len(ind_fc_con_publishers)} independent non-stale ClaimReviews explicitly refuted the fabricated claim."
                    )
                else:
                    final_verdict = "UNVERIFIED"
                    final_conf = round(min(0.42, max(0.18, phase1_synthesis.confidence_score * 0.45)), 2)
                    final_expl = (
                        f"Cautious abstention (UNVERIFIED): {primary_need_reason or 'This claim requires an official first-party primary record.'} "
                        "External ClaimReview entity alignment was insufficient."
                    )
                    reasoning_parts.append("Claim requires Tier 1 primary record; external alignment insufficient.")
            else:
                final_verdict = "UNVERIFIED"
                final_conf = round(min(0.42, max(0.18, phase1_synthesis.confidence_score * 0.45)), 2)
                final_expl = (
                    f"Cautious abstention (UNVERIFIED): {primary_need_reason or 'This claim requires an official first-party primary record.'} "
                    "None of the configured secondary/metadata sources supply Tier 1 institutional documents."
                )
                reasoning_parts.append(
                    "Claim requires a Tier 1 official institutional record; Tier 2/3 sources cannot substitute for first-party verification."
                )

        # Case C (High Precedence): Unresolved credible source conflicts -> UNVERIFIED
        # Evaluated BEFORE OUTDATED / MISLEADING shortcuts so unresolved external/cross-tier conflicts abstain safely.
        elif has_unresolved_conflict:
            final_verdict = "UNVERIFIED"
            final_conf = round(min(0.45, max(0.20, phase1_synthesis.confidence_score * 0.6)), 2)
            final_expl = (
                "Cautious abstention: Conflicting credible evidence was retrieved across available sources; "
                "neither truth nor falsehood could be certified safely without resolution."
            )
            reasoning_parts.append(
                "Detected unresolved conflict across independent supporting and contradicting items; downgraded conservatively to UNVERIFIED."
            )

        # Case A: Resolved OUTDATED (historical tenure closure without external/active conflict)
        elif phase1_synthesis.verdict == "OUTDATED" and (tier1_con or tier2_con or has_historical_end):
            final_verdict = "OUTDATED"
            if not tier1_con:
                final_conf = round(min(0.88, final_conf), 2)
            reasoning_parts.append("Temporal evaluation identified closed historical tenure or rebrand on a present-tense assertion.")

        # Case B: Resolved MISLEADING (explicit slot substitution or absolute framing distortion without unresolved external conflict)
        elif phase1_synthesis.verdict == "MISLEADING" and (tier1_con or tier2_con):
            final_verdict = "MISLEADING"
            if unavailable_providers or not tier1_con:
                final_conf = round(min(0.82 if not unavailable_providers else 0.72, final_conf), 2)
            reasoning_parts.append("Evidence revealed slot substitution, distortion, or direct framing conflict on an identifiable subject.")

        # Case D: Only outdated 2017 FEVER support for a current-state assertion (never overrides resolved OUTDATED/MISLEADING)
        elif (
            phase1_synthesis.verdict == "GENUINE"
            and only_stale_2017_support
            and bool(sup_items)
            and not any(
                a.source_type == "wikipedia_live" and a.is_relevant and a.stance == "supporting" for a in all_assessments
            )
            and not tier1_sup
        ):
            final_verdict = "UNVERIFIED"
            final_conf = round(min(0.40, phase1_synthesis.confidence_score * 0.5), 2)
            final_expl = (
                "Insufficient current evidence: Only static 2017 FEVER snapshot evidence matched this present-tense claim, "
                "and live confirmation could not be obtained."
            )
            reasoning_parts.append("Rejected GENUINE because stale 2017 snapshot evidence cannot establish current truth.")

        # Case E: Support Tiered Sufficiency Gate
        elif phase1_synthesis.verdict == "GENUINE" or any(a.meets_single_source_criteria for a in tier1_sup) or len(ind_tier1_sup) >= 2:
            if any(a.meets_single_source_criteria for a in tier1_sup) or len(ind_tier1_sup) >= 2:
                final_verdict = "GENUINE"
                base_cap = 0.88 if tier1_sup_single_fc_only else 0.95
                final_conf = round(min(base_cap, max(0.75, phase1_synthesis.confidence_score)), 2)
                strongest_page = strongest_page or tier1_sup[0].title_or_page
                if tier1_sup_single_fc_only:
                    reasoning_parts.append(
                        "Tier 1 official first-party record satisfied all strict provenance/alignment criteria and was preserved "
                        "over a single dissenting Tier 3 ClaimReview (conflict noted)."
                    )
                else:
                    reasoning_parts.append(
                        "Tier 1 official first-party record(s) directly satisfied all strict provenance, relevance, entity, predicate, temporal, and specificity criteria."
                    )
            elif bool(tier2_sup) and len(ind_tier2_sup | ind_fc_sup_publishers) >= 2:
                final_verdict = "GENUINE"
                has_live = any(a.source_type == "wikipedia_live" for a in tier2_sup)
                cap = 0.88 if has_live else 0.85
                final_conf = round(min(cap, phase1_synthesis.confidence_score), 2)
                reasoning_parts.append(
                    f"Corroborated across {len(ind_tier2_sup)} independent Tier 2 source(s)"
                    + (f" + {len(ind_fc_sup_publishers)} ClaimReview publisher(s)" if ind_fc_sup_publishers else "")
                    + " (secondary reference support only, not Tier 1 primary authority)."
                )
            else:
                final_verdict = "UNVERIFIED"
                final_conf = round(min(0.42, max(0.20, phase1_synthesis.confidence_score * 0.55)), 2)
                if len(ind_tier2_sup) == 1:
                    final_expl = (
                        "Insufficient corroboration: A single Tier 2 Wikipedia/FEVER underlying source cannot independently certify GENUINE "
                        "without a second independent corroborating source or a qualifying Tier 1 official record."
                    )
                    reasoning_parts.append(
                        "Abstained to UNVERIFIED: single underlying Tier 2 source rejected under independent corroboration rule."
                    )
                else:
                    final_expl = (
                        "Insufficient quality corroboration: Supporting candidates lacked Tier 1 or >=2 independent sources including Tier 2 "
                        "documentary provenance to certify GENUINE."
                    )
                    reasoning_parts.append(
                        "Abstained to UNVERIFIED: supporting candidates failed Tiered Sufficiency gates."
                    )

        # Case F: Contradiction Tiered Sufficiency Gate
        elif phase1_synthesis.verdict == "FAKE" or any(a.meets_single_source_criteria for a in tier1_con) or len(ind_tier1_con) >= 2:
            if any(a.meets_single_source_criteria for a in tier1_con) or len(ind_tier1_con) >= 2:
                final_verdict = "FAKE"
                base_cap = 0.88 if tier1_con_single_fc_only else 0.95
                final_conf = round(min(base_cap, max(0.75, phase1_synthesis.confidence_score)), 2)
                strongest_page = strongest_page or tier1_con[0].title_or_page
                reasoning_parts.append("Tier 1 official record directly contradicted the claim under all strict provenance/alignment criteria.")
            elif tier2_con and not tier2_sup and not tier1_sup:
                best_c = max(tier2_con, key=lambda x: x.overall_quality_score)
                sym = best_c.symbolic_alignment
                has_explicit_sym_refute = bool(
                    sym and (sym.has_numeric_conflict or sym.has_exclusive_slot_conflict or sym.has_negation_conflict)
                )
                if len(ind_tier2_con | ind_fc_con_publishers) >= 2 or (
                    has_explicit_sym_refute and best_c.overall_quality_score >= 0.65 and best_c.contradiction_strength >= 0.65
                ):
                    final_verdict = "FAKE"
                    cap = 0.88 if len(ind_tier2_con | ind_fc_con_publishers) >= 2 else 0.84
                    final_conf = round(min(cap, phase1_synthesis.confidence_score), 2)
                    reasoning_parts.append(
                        f"Tier 2 secondary encyclopedic refutation ({len(ind_tier2_con)} source(s)"
                        + (f", +{len(ind_fc_con_publishers)} ClaimReview(s)" if ind_fc_con_publishers else "")
                        + ") with aligned contradiction."
                    )
                else:
                    final_verdict = "UNVERIFIED"
                    final_conf = round(min(0.42, phase1_synthesis.confidence_score * 0.55), 2)
                    final_expl = (
                        "Insufficient contradiction corroboration: Single uncorroborated Tier 2 contradicting source "
                        "without explicit numeric/slot refutation cannot prove FAKE."
                    )
                    reasoning_parts.append(
                        "Abstained to UNVERIFIED: single Tier 2 contradiction lacked corroboration or explicit symbolic conflict."
                    )
            elif len(ind_fc_con_publishers) >= 2 and not tier1_sup and not tier2_sup and not credible_fc_sup:
                best_fc = max(credible_fc_con, key=lambda x: x.overall_quality_score)
                if best_fc.overall_quality_score >= 0.62 and best_fc.subject_entity_alignment >= 0.65:
                    final_verdict = "FAKE"
                    final_conf = 0.72
                    strongest_page = best_fc.title_or_page
                    final_expl = (
                        f"Multi-source external fact-check consensus: {len(ind_fc_con_publishers)} independent fact-checking publishers "
                        "explicitly refuted the claim with high entity/predicate alignment."
                    )
                    reasoning_parts.append(
                        f"Confirmed refutation using {len(ind_fc_con_publishers)} independent non-stale ClaimReview contradictions."
                    )
                else:
                    final_verdict = "UNVERIFIED"
                    final_conf = round(min(0.42, phase1_synthesis.confidence_score * 0.55), 2)
                    reasoning_parts.append("Abstained to UNVERIFIED: external fact-check alignment was insufficient.")
            else:
                final_verdict = "UNVERIFIED"
                final_conf = round(min(0.42, phase1_synthesis.confidence_score * 0.55), 2)
                final_expl = (
                    "Insufficient contradiction quality: Contradicting candidates did not meet Tiered Sufficiency "
                    "criteria to prove FAKE."
                )
                reasoning_parts.append(
                    "Abstained to UNVERIFIED: Tier 3 or low-alignment contradictions cannot force FAKE."
                )

        # Case G: Phase 1 was UNVERIFIED -> Check multi-publisher non-stale Tier 3 ClaimReview consensus ONLY for refutation
        else:
            if len(ind_fc_con_publishers) >= 2 and not tier1_sup and not tier2_sup and not credible_fc_sup:
                best_fc = max(credible_fc_con, key=lambda x: x.overall_quality_score)
                if best_fc.overall_quality_score >= 0.62 and best_fc.subject_entity_alignment >= 0.65:
                    final_verdict = "FAKE"
                    final_conf = 0.72
                    strongest_page = best_fc.title_or_page
                    final_expl = (
                        f"Multi-source external fact-check consensus: {len(ind_fc_con_publishers)} independent fact-checking publishers "
                        "explicitly refuted the material claim with high entity/predicate alignment."
                    )
                    reasoning_parts.append(
                        f"Overrode insufficient local coverage using {len(ind_fc_con_publishers)} independent non-stale ClaimReview contradictions."
                    )
                else:
                    final_verdict = "UNVERIFIED"
                    reasoning_parts.append("Retained UNVERIFIED: external fact-check alignment was insufficient.")
            else:
                final_verdict = "UNVERIFIED"
                if sup_items and all(not (a.is_official_primary or a.is_secondary_encyclopedic) for a in sup_items):
                    reasoning_parts.append(
                        "Only Tier 3 metadata/fact-check supporting items were found; without Tier 1/Tier 2 documentary proof, ClaimReviews cannot establish GENUINE."
                    )
                elif con_items and all(not (a.is_official_primary or a.is_secondary_encyclopedic) for a in con_items):
                    reasoning_parts.append(
                        "Only Tier 3 metadata/single-review contradicting items were found (e.g., 1 ClaimReview or GDELT headline); insufficient to establish FAKE."
                    )
                else:
                    reasoning_parts.append("Evidence across retrieved sources was insufficient or irrelevant; abstained cleanly to UNVERIFIED.")

        if unavailable_providers:
            reasoning_parts.append(
                f"Unavailable/failed providers ({', '.join(unavailable_providers)}) were treated strictly as missing coverage, never as negative evidence."
            )
        if rejected_items:
            reasoning_parts.append(
                f"Filtered out {len(rejected_items)} irrelevant/mismatched item(s) before verdict synthesis."
            )

        # 6. Compare Final Verdict against Separate Initial ML Baseline Tag (for transparency only)
        init_v = initial_signals.preliminary_verdict
        verdict_changed = final_verdict != init_v
        verdict_change_reason: Optional[str] = None
        if final_verdict == "UNVERIFIED" and init_v != "UNVERIFIED":
            decision = "abstained_insufficient"
            verdict_change_reason = (
                f"Preliminary linguistic signal suggested {init_v}, but Second-Pass evidence evaluation abstained to UNVERIFIED "
                "because retrieved evidence was insufficient, lacked required Tier 1/corroborated provenance, or contained conflicts."
            )
        elif verdict_changed:
            decision = "overridden_by_evidence"
            verdict_change_reason = (
                f"Second-Pass evidence evaluation changed preliminary linguistic signal ({init_v}) to {final_verdict} "
                "based on post-retrieval DeBERTa NLI, symbolic alignment, and Tiered Sufficiency rules."
            )
        elif unavailable_providers or conflicts_detected:
            decision = "downgraded_uncertainty"
        else:
            decision = "confirmed_initial" if final_verdict in ("GENUINE", "FAKE", "MISLEADING", "OUTDATED") else "abstained_insufficient"

        second_pass_reasoning = " ".join(reasoning_parts).strip()
        if verdict_change_reason and verdict_change_reason not in final_uncert:
            final_uncert = f"{final_uncert} {verdict_change_reason}".strip() if final_uncert else verdict_change_reason

        updated_synthesis = SynthesisResult(
            verdict=final_verdict,
            confidence_score=final_conf,
            explanation=final_expl,
            uncertainty_explanation=final_uncert,
            conflicting_evidence_detected=conflicts_detected,
            strongest_evidence_page=strongest_page,
            limitations=limitations,
            aligned_assessments=phase1_synthesis.aligned_assessments,
        )

        audit_trail = EvidenceAuditTrail(
            initial_ml_signals=initial_signals,
            nli_evaluation=nli_summary,
            directions_executed=list(ret_meta.get("directions_executed", ["support", "contradict", "neutral"])),
            queries_by_direction=directional_queries.to_dict(),
            retrieval_attempts=attempt_records,
            supporting_evidence=sup_items,
            contradicting_evidence=con_items,
            neutral_evidence=neu_items,
            rejected_irrelevant_evidence=rejected_items,
            conflicts_detected=conflicts_detected,
            conflict_details=conflict_details,
            provider_statuses=provider_statuses,
            unavailable_providers=unavailable_providers,
            evidence_quality_summary=quality_summary,
            second_pass_decision=decision,
            verdict_changed_from_initial=verdict_changed,
            verdict_change_reason=verdict_change_reason,
            second_pass_reasoning=second_pass_reasoning,
            final_verdict=final_verdict,
            final_confidence=final_conf,
            limitations=limitations,
            total_retrieval_attempts=len(attempt_records),
            omitted_retrieval_attempts=0,
        )

        return updated_synthesis, audit_trail


def get_second_pass_evaluator() -> SecondPassEvaluator:
    return SecondPassEvaluator()
