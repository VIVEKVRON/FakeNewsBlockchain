"""
backend/app/services/verification_service.py
Service coordinating hybrid evidence retrieval (FEVER FAISS + public Wikipedia fallback),
calibrated DeBERTa NLI inference, six-class verdict synthesis, and article-level aggregation.
"""

import re
import threading
from typing import Any, Dict, List, Optional, Tuple
from backend.app.schemas.verification import (
    TextVerificationRequest,
    TextVerificationResponse,
    EvidenceSentenceSchema,
    NLIProbabilitiesSchema,
    SubClaimVerdictSchema,
    ModelSignalSchema,
    InitialMLSignalsSchema,
    DebertaNLISummarySchema,
    RetrievalAttemptSchema,
    AuditSourceItemSchema,
    ProviderStatusItemSchema,
    EvidenceQualitySummarySchema,
    EvidenceAuditTrailSchema,
    FactCheckMatchSchema,
    NewsEvidenceSchema,
    GdeltUsageStatusSchema,
    ExternalSourceStatusSchema,
    VerdictEnum,
)
from backend.app.schemas.article import (
    ArticleVerificationRequest,
    ArticleVerificationResponse,
    ArticleClassifierSignal,
    LIARClassifierSignal,
    ExtractedClaimVerification,
)
from backend.app.services.blockchain_service import (
    create_hash_summary_from_text,
    create_hash_summary_from_article,
)
from backend.app.services.external_apis.evidence_aggregator import (
    ExternalAggregationResult,
    ExternalEvidenceAggregator,
    RetrievalAttempt,
)
from backend.app.services.external_apis.quota_db import sanitize_secret_text
from backend.app.utils.logger import logger
from ml.rag.retriever import get_retriever
from ml.inference.claim_verifier import VerifiedEvidence, get_claim_verifier
from ml.inference.verdict_synthesizer import SynthesisResult, get_verdict_synthesizer
from ml.inference.evidence_alignment import extract_subject_entities, split_compound_claims
from ml.inference.evidence_quality import build_directional_queries
from ml.inference.second_pass_synthesizer import (
    EvidenceAuditTrail,
    InitialMLSignals,
    ModelSignalRecord,
    get_second_pass_evaluator,
    map_classifier_to_preliminary_verdict,
)
from ml.inference.article_classifier import get_article_classifier
from ml.inference.claim_classifier import get_claim_classifier
from ml.inference.claim_extractor import get_claim_extractor


def _to_evidence_schema(ve: VerifiedEvidence) -> EvidenceSentenceSchema:
    return EvidenceSentenceSchema(
        rank=ve.rank,
        page=ve.page,
        sentence_id=ve.sentence_id,
        doc_id=ve.doc_id,
        text=ve.text,
        retrieval_similarity=ve.retrieval_similarity,
        nli_label=ve.nli_label,
        nli_confidence=ve.nli_confidence,
        nli_probabilities=NLIProbabilitiesSchema(
            supports=ve.nli_probabilities["supports"],
            refutes=ve.nli_probabilities["refutes"],
            not_enough_info=ve.nli_probabilities["not_enough_info"],
        ),
        source_type=getattr(ve, "source_type", "fever_local"),
        source_url=getattr(ve, "source_url", None),
        publication_date=getattr(ve, "publication_date", "2017-06 (FEVER Wikipedia Corpus)"),
        evidence_role=getattr(ve, "evidence_role", "contextual"),
        alignment_notes=getattr(ve, "alignment_notes", None),
        retrieval_direction=getattr(ve, "retrieval_direction", "neutral"),
    )


def _extract_article_lead_subject(text: str, title: Optional[str]) -> Optional[str]:
    """Extracts primary proper-noun subject phrase from first sentence or title for anaphora resolution."""
    first_sent = text.strip().split(".")[0] if text else ""
    for source in (first_sent, title or ""):
        match = re.match(r"^\s*((?:\d+\s+)?[A-Z][A-Za-z0-9.\-]+(?:\s+(?:and|of|the|for|[A-Z][A-Za-z0-9.\-]+)){0,4})", source)
        if match:
            candidate = match.group(1).strip()
            if len(candidate) >= 3 and candidate.lower() not in {"the", "this", "that", "industry", "analysts"}:
                return candidate
        entities = extract_subject_entities(source)
        if entities:
            return " ".join(entities[:3])
    return None


def _resolve_anaphora_for_retrieval(claim_text: str, lead_subject: Optional[str]) -> str:
    """Expands leading pronouns/generic references ('The series', 'It', 'He') without overwriting distinct named subjects."""
    if not lead_subject:
        return claim_text
    anaphora_pattern = re.compile(
        r"^(?:the\s+(?:series|show|program|programme|film|movie|company|organization|organisation|country|city|platform|pact|accord|treaty|report)|it|he|she|they)\b",
        re.IGNORECASE,
    )
    if anaphora_pattern.match(claim_text.strip()):
        return anaphora_pattern.sub(lead_subject, claim_text.strip(), count=1)
    if lead_subject.lower() not in claim_text.lower():
        if extract_subject_entities(claim_text) and not re.match(
            r"^(?:this|that|these|those|his|her|its|their|such)\b",
            claim_text.strip(),
            re.IGNORECASE,
        ):
            return claim_text
        return f"{lead_subject}: {claim_text}"
    return claim_text


def _compute_factual_materiality(claim_text: str) -> Tuple[float, str]:
    """
    Scores factual materiality based on concrete entities, numerical/year anchors,
    and absence of vague attribution hedges.
    """
    low = claim_text.lower()
    has_hedge = bool(
        re.search(
            r"\b(reportedly|allegedly|rumored|rumoured|some\s+(?:say|claim|observers)|critics\s+note|widely\s+(?:felt|thought))\b",
            low,
        )
    )
    has_year_or_num = bool(re.search(r"\b\d+\b", claim_text))
    entities = extract_subject_entities(claim_text)
    if has_hedge and not (entities and has_year_or_num):
        return 0.65, "peripheral/hedged"
    if entities and has_year_or_num:
        return 1.15, "high-materiality (entity + number)"
    if entities or has_year_or_num:
        return 1.0, "material factual assertion"
    return 0.80, "general assertion"


def _aggregate_multi_claim_verdicts(
    items: List[Tuple[str, SynthesisResult]],
    context_label: str = "sub-claims",
    candidate_weights: Optional[List[Tuple[int, float]]] = None,
) -> Tuple[VerdictEnum, float, str, str]:
    """
    Aggregates individual claim assessments into a defensible six-class verdict.
    When candidate_weights=[(relevance_rank, relevance_score), ...] is provided (article mode),
    weights aggregation by:
      1. Claim centrality (relevance_rank & normalized relevance_score),
      2. Factual materiality (entities, numbers/dates, non-hedged framing),
      3. Evidence strength (calibrated verdict confidence & retrieval support).
    Ensures minor unsupported details do not automatically invalidate strong central support,
    and minor true details never mask material central falsehoods.
    """
    if not items:
        return (
            VerdictEnum.UNVERIFIED,
            0.0,
            f"No verifiable declarative {context_label} could be evaluated.",
            "Empty claim breakdown prevented evidence synthesis.",
        )

    total = len(items)
    verdicts = [VerdictEnum(res.verdict) for _, res in items]

    # When no centrality metadata is passed (compound sub-claims / equal-weight mode),
    # treat all sub-propositions as equally central so partial mismatches stay PARTIALLY_TRUE/UNVERIFIED.
    if not candidate_weights or len(candidate_weights) != total:
        n_genuine = sum(1 for v in verdicts if v == VerdictEnum.GENUINE)
        n_fake = sum(1 for v in verdicts if v == VerdictEnum.FAKE)
        n_misleading = sum(1 for v in verdicts if v == VerdictEnum.MISLEADING)
        n_outdated = sum(1 for v in verdicts if v == VerdictEnum.OUTDATED)
        n_unverified = sum(1 for v in verdicts if v == VerdictEnum.UNVERIFIED)
        avg_conf = sum(res.confidence_score for _, res in items) / total

        if n_genuine > 0 and (n_fake > 0 or n_misleading > 0 or n_outdated > 0):
            conf = round(max(0.55, min(0.85, avg_conf)), 2)
            return (
                VerdictEnum.PARTIALLY_TRUE,
                conf,
                (
                    f"Partially true: {n_genuine} of {total} {context_label} corroborated by documentary evidence, "
                    f"while {n_fake + n_misleading + n_outdated} contradicted, distorted, or outdated assertion(s) were detected."
                ),
                (
                    f"Sub-claim breakdown across {total} {context_label}: {n_genuine} GENUINE, {n_fake} FAKE, "
                    f"{n_misleading} MISLEADING, {n_outdated} OUTDATED, {n_unverified} UNVERIFIED."
                ),
            )
        if n_genuine == total:
            return (
                VerdictEnum.GENUINE,
                round(min(0.94, max(0.70, avg_conf)), 2),
                f"All {total} evaluated {context_label} were corroborated by matching evidence without unresolved contradictions.",
                f"Consistent documentary support across all {total} {context_label}.",
            )
        if n_fake > 0 and n_genuine == 0:
            fake_confs = [res.confidence_score for _, res in items if res.verdict == VerdictEnum.FAKE.value]
            return (
                VerdictEnum.FAKE,
                round(max(fake_confs), 2),
                f"Fact verification identified {n_fake} refuted {context_label} contradicted by retrieved evidence.",
                f"Contradicted {context_label}: {n_fake}/{total}; Unverified: {n_unverified}/{total}.",
            )
        if n_misleading > 0 and n_genuine == 0:
            return (
                VerdictEnum.MISLEADING,
                0.70,
                f"Detected contextual distortion or inaccurate attribution across {n_misleading} of {total} {context_label}.",
                f"Framing or attribute discrepancies identified across {n_misleading}/{total} {context_label}.",
            )
        if n_outdated > 0 and n_genuine == 0:
            out_confs = [res.confidence_score for _, res in items if res.verdict == VerdictEnum.OUTDATED.value]
            return (
                VerdictEnum.OUTDATED,
                round(max(out_confs), 2),
                f"Detected {n_outdated} outdated assertion(s) presenting past roles or rebranded states as current.",
                f"Temporal mismatch found across {n_outdated}/{total} {context_label}.",
            )
        if n_genuine > 0 and n_unverified > 0:
            return (
                VerdictEnum.UNVERIFIED,
                round(avg_conf, 2),
                (
                    f"Partially corroborated ({n_genuine}/{total} {context_label} verified GENUINE), "
                    f"but {n_unverified}/{total} lacked sufficient evidence; overall verdict remains UNVERIFIED."
                ),
                (
                    f"Conservative policy prevents certifying an entire multi-claim statement as GENUINE while "
                    f"{n_unverified} constituent claim(s) remain UNVERIFIED."
                ),
            )
        return (
            VerdictEnum.UNVERIFIED,
            round(min(0.45, avg_conf), 2),
            f"Retrieved evidence did not adequately substantiate any of the {total} evaluated {context_label}.",
            f"All {total} {context_label} remained UNVERIFIED under alignment gating.",
        )

    # Weighted Centrality x Materiality x Evidence Strength Aggregation (Article Mode)
    max_rel_score = max((max(0.1, float(score)) for _, score in candidate_weights), default=1.0)
    weighted_rows = []
    for (c_text, res), (rank, rel_score) in zip(items, candidate_weights):
        norm_rel = max(0.15, min(1.0, float(rel_score) / max_rel_score))
        if rank <= 1:
            rank_decay = 1.0
        elif rank == 2:
            rank_decay = 0.88
        elif rank == 3:
            rank_decay = 0.76
        elif rank == 4:
            rank_decay = 0.38
        else:
            rank_decay = 0.28

        centrality_w = round(0.65 * rank_decay + 0.35 * norm_rel, 3)
        is_central = (rank == 1) or (rank <= 3 and norm_rel >= 0.45 and centrality_w >= 0.58)
        mat_w, mat_desc = _compute_factual_materiality(c_text)
        ev_w = max(0.55, min(1.0, res.confidence_score)) if res.verdict != VerdictEnum.UNVERIFIED.value else 0.70
        combined_w = round(centrality_w * mat_w * ev_w, 3)
        weighted_rows.append({
            "text": c_text,
            "res": res,
            "verdict": VerdictEnum(res.verdict),
            "rank": rank,
            "is_central": is_central,
            "centrality_w": centrality_w,
            "mat_w": mat_w,
            "mat_desc": mat_desc,
            "ev_w": ev_w,
            "weight": combined_w,
        })

    by_verdict = {v: [r for r in weighted_rows if r["verdict"] == v] for v in VerdictEnum}
    central_rows = [r for r in weighted_rows if r["is_central"]]
    minor_rows = [r for r in weighted_rows if not r["is_central"]]

    w_genuine = round(sum(r["weight"] for r in by_verdict[VerdictEnum.GENUINE]), 2)
    w_fake = round(sum(r["weight"] for r in by_verdict[VerdictEnum.FAKE]), 2)
    w_misleading = round(sum(r["weight"] for r in by_verdict[VerdictEnum.MISLEADING]), 2)
    w_outdated = round(sum(r["weight"] for r in by_verdict[VerdictEnum.OUTDATED]), 2)
    w_unverified = round(sum(r["weight"] for r in by_verdict[VerdictEnum.UNVERIFIED]), 2)

    central_genuine = sum(1 for r in central_rows if r["verdict"] == VerdictEnum.GENUINE)
    central_fake = sum(1 for r in central_rows if r["verdict"] == VerdictEnum.FAKE)
    central_misleading = sum(1 for r in central_rows if r["verdict"] == VerdictEnum.MISLEADING)
    central_outdated = sum(1 for r in central_rows if r["verdict"] == VerdictEnum.OUTDATED)
    central_unverified = sum(1 for r in central_rows if r["verdict"] == VerdictEnum.UNVERIFIED)

    minor_genuine = sum(1 for r in minor_rows if r["verdict"] == VerdictEnum.GENUINE)
    minor_unverified = sum(1 for r in minor_rows if r["verdict"] == VerdictEnum.UNVERIFIED)

    weight_summary = (
        f"Weighted aggregation across {total} {context_label} "
        f"(central: {len(central_rows)}, minor: {len(minor_rows)}; "
        f"weights -> GENUINE={w_genuine:.2f}, FAKE={w_fake:.2f}, MISLEADING={w_misleading:.2f}, "
        f"OUTDATED={w_outdated:.2f}, UNVERIFIED={w_unverified:.2f})."
    )

    n_genuine = len(by_verdict[VerdictEnum.GENUINE])
    n_fake = len(by_verdict[VerdictEnum.FAKE])
    n_misleading = len(by_verdict[VerdictEnum.MISLEADING])
    n_outdated = len(by_verdict[VerdictEnum.OUTDATED])
    n_unverified = len(by_verdict[VerdictEnum.UNVERIFIED])

    # 1. Material central falsehood MUST NOT be masked by minor peripheral truths -> FAKE
    if central_fake > 0 and central_genuine == 0:
        fake_confs = [r["res"].confidence_score for r in by_verdict[VerdictEnum.FAKE]]
        minor_note = (
            f" Although {minor_genuine} minor peripheral claim(s) matched background facts, minor truths do not offset central falsification."
            if minor_genuine > 0 else ""
        )
        return (
            VerdictEnum.FAKE,
            round(max(fake_confs), 2),
            f"Material falsehood detected: {central_fake} central claim(s) were directly contradicted by evidence.{minor_note}",
            weight_summary,
        )

    # 2. Central genuine claims + contradictory/misleading/outdated propositions -> PARTIALLY_TRUE
    if (central_genuine > 0 or w_genuine > 0) and (n_fake > 0 or n_misleading > 0 or n_outdated > 0):
        avg_weighted_conf = sum(r["res"].confidence_score * r["weight"] for r in weighted_rows) / max(
            0.01, sum(r["weight"] for r in weighted_rows)
        )
        conf = round(max(0.55, min(0.86, avg_weighted_conf)), 2)
        return (
            VerdictEnum.PARTIALLY_TRUE,
            conf,
            (
                f"Partially true: {central_genuine} central and {minor_genuine} minor claim(s) corroborated, "
                f"while {n_fake} FAKE, {n_misleading} MISLEADING, and {n_outdated} OUTDATED assertion(s) conflicted with evidence."
            ),
            weight_summary,
        )

    # 3. All evaluated claims genuinely corroborated -> GENUINE
    if n_genuine == total:
        w_conf = sum(r["res"].confidence_score * r["weight"] for r in weighted_rows) / max(0.01, w_genuine)
        return (
            VerdictEnum.GENUINE,
            round(min(0.94, max(0.72, w_conf)), 2),
            f"All {total} evaluated {context_label} ({central_genuine} central) were corroborated without unresolved contradictions.",
            weight_summary,
        )

    # 4. Strong central GENUINE support + ONLY minor/peripheral UNVERIFIED details -> GENUINE (with uncertainty note)
    if central_genuine >= 1 and central_unverified == 0 and minor_unverified > 0 and w_genuine >= 1.4 * w_unverified:
        gen_conf = sum(r["res"].confidence_score * r["weight"] for r in by_verdict[VerdictEnum.GENUINE]) / max(0.01, w_genuine)
        ratio_adj = 0.88 + 0.12 * (w_genuine / max(0.01, w_genuine + w_unverified))
        minor_texts = "; ".join(f"'{r['text'][:70]}'" for r in minor_rows if r["verdict"] == VerdictEnum.UNVERIFIED)
        return (
            VerdictEnum.GENUINE,
            round(min(0.90, max(0.68, gen_conf * ratio_adj)), 2),
            (
                f"Supported overall: all {central_genuine} central claim(s) were corroborated by high-strength evidence; "
                f"{minor_unverified} minor peripheral detail(s) could not be verified and did not invalidate the core article."
            ),
            f"{weight_summary} Unverified minor detail(s): {minor_texts}.",
        )

    # 5. Misleading or Outdated without corroborated truths
    if n_misleading > 0 and n_genuine == 0:
        return (
            VerdictEnum.MISLEADING,
            0.70,
            f"Detected contextual distortion across {central_misleading} central / {n_misleading} total {context_label}.",
            weight_summary,
        )
    if n_outdated > 0 and n_genuine == 0:
        out_confs = [r["res"].confidence_score for r in by_verdict[VerdictEnum.OUTDATED]]
        return (
            VerdictEnum.OUTDATED,
            round(max(out_confs), 2),
            f"Detected {n_outdated} outdated assertion(s) framing expired roles or states as current.",
            weight_summary,
        )

    # 6. Insufficient central evidence or mixed central GENUINE + central UNVERIFIED -> UNVERIFIED
    avg_conf = sum(r["res"].confidence_score * r["weight"] for r in weighted_rows) / max(0.01, sum(r["weight"] for r in weighted_rows))
    if n_genuine > 0 and central_unverified > 0:
        return (
            VerdictEnum.UNVERIFIED,
            round(min(0.55, avg_conf), 2),
            (
                f"Inconclusive central evidence: {central_genuine} central claim(s) verified GENUINE, "
                f"but {central_unverified} central claim(s) lacked sufficient documentary evidence; article remains UNVERIFIED."
            ),
            weight_summary,
        )
    return (
        VerdictEnum.UNVERIFIED,
        round(min(0.45, avg_conf), 2),
        f"Insufficient evidence across central propositions ({central_unverified} central UNVERIFIED); cannot substantiate article.",
        weight_summary,
    )


def _to_external_schemas(
    agg: ExternalAggregationResult,
) -> Tuple[List[FactCheckMatchSchema], List[NewsEvidenceSchema], ExternalSourceStatusSchema]:
    fc_schemas = [
        FactCheckMatchSchema(
            claim_text=m.claim_text,
            review_title=m.review_title,
            publisher_name=m.publisher_name,
            publisher_site=m.publisher_site,
            reviewer_name=m.reviewer_name,
            rating_text=m.rating_text,
            review_url=m.review_url,
            review_publication_date=m.review_publication_date,
            claim_appearance_date=m.claim_appearance_date,
            original_claim_author=m.original_claim_author,
            language_code=m.language_code,
            retrieved_at=m.retrieved_at,
            is_stale=m.is_stale,
            stale_reason=m.stale_reason,
            is_conflicting=m.is_conflicting,
        )
        for m in agg.fact_check_matches
    ]
    news_schemas = [
        NewsEvidenceSchema(
            title=a.title,
            url=a.url,
            domain=a.domain,
            published_at=a.published_at,
            language=a.language,
            source_country=a.source_country,
            search_query=a.search_query,
            search_window=a.search_window,
            retrieved_at=a.retrieved_at,
            syndicated_count=a.syndicated_count,
        )
        for a in agg.news_evidence
    ]
    usage_schema = (
        GdeltUsageStatusSchema(
            **agg.gdelt_usage.to_dict(),
            google_fact_check_available=agg.google_available,
        )
        if agg.gdelt_usage is not None
        else None
    )
    status_schema = ExternalSourceStatusSchema(
        google_fact_check_status=agg.google_status,
        google_fact_check_available=agg.google_available,
        google_fact_check_error=agg.google_error,
        gdelt_status=agg.gdelt_status,
        gdelt_error=agg.gdelt_error,
        has_conflicting_fact_checks=agg.has_conflicting_fact_checks,
        has_stale_fact_checks=agg.has_stale_fact_checks,
        gdelt_conflicting_coverage=agg.gdelt_conflicting_coverage,
        duplicates_collapsed=agg.duplicates_collapsed,
        gdelt_usage=usage_schema,
        supplementary_notes=list(agg.supplementary_notes),
    )
    return fc_schemas, news_schemas, status_schema


def _to_audit_source_schema(item) -> AuditSourceItemSchema:
    return AuditSourceItemSchema(
        source_type=item.source_type,
        source_name=item.source_name,
        title_or_page=item.title_or_page,
        text_excerpt=item.text_excerpt,
        url=item.url,
        publication_date=item.publication_date,
        retrieved_at=item.retrieved_at,
        retrieval_direction=item.retrieval_direction,
        stance=item.stance,
        is_relevant=item.is_relevant,
        rejection_reason=item.rejection_reason,
        relevance_score=item.relevance_score,
        subject_entity_alignment=item.subject_entity_alignment,
        predicate_alignment=item.predicate_alignment,
        temporal_relevance=item.temporal_relevance,
        temporal_status=item.temporal_status,
        geographic_relevance=item.geographic_relevance,
        geographic_status=item.geographic_status,
        source_reliability_tier=item.source_reliability_tier,
        evidence_tier=getattr(item, "evidence_tier", "TIER_3_SECONDARY_OR_METADATA"),
        meets_single_source_criteria=bool(getattr(item, "meets_single_source_criteria", False)),
        provenance_weight=item.provenance_weight,
        evidence_specificity=item.evidence_specificity,
        independent_group_key=item.independent_group_key,
        contradiction_strength=item.contradiction_strength,
        source_freshness=item.source_freshness,
        overall_quality_score=item.overall_quality_score,
        alignment_notes=item.alignment_notes,
        ml_nli_label=getattr(item, "ml_nli_label", "NOT ENOUGH INFO"),
        ml_nli_confidence=float(getattr(item, "ml_nli_confidence", 0.0)),
        ml_nli_probabilities=dict(getattr(item, "ml_nli_probabilities", {}) or {}),
    )


def _to_model_signal_schema(sig: ModelSignalRecord) -> ModelSignalSchema:
    return ModelSignalSchema(
        model_name=sig.model_name,
        dataset_origin=sig.dataset_origin,
        applicable_input_type=sig.applicable_input_type,
        applicable=sig.applicable,
        prediction=sig.prediction,
        confidence=sig.confidence,
        probabilities=dict(sig.probabilities),
        raw_logits=dict(sig.raw_logits),
        preliminary_verdict_tag=sig.preliminary_verdict_tag,
        disclaimer=sig.disclaimer,
    )


def _derive_provider_status_from_attempts(
    attempts: List[Any],
    provider: str,
    fallback_status: str,
) -> str:
    """Derives claim-scoped provider status strictly from that claim's attempts."""
    matching = [a for a in attempts if getattr(a, "provider", None) == provider]
    if not matching:
        return fallback_status
    outcomes = [str(getattr(a, "outcome", "")) for a in matching]
    if "cache_hit" in outcomes and all(o in ("cache_hit", "skipped_by_policy", "no_results") for o in outcomes):
        return "ok_cached"
    if "success_with_results" in outcomes:
        return "ok"
    if "quota_exhausted" in outcomes:
        return "quota_exhausted"
    if "timeout" in outcomes:
        return "timeout"
    if "unavailable_no_api_key" in outcomes:
        return "unavailable_no_api_key"
    if "network_error" in outcomes:
        return "network_error"
    if "no_results" in outcomes:
        return "no_results"
    if all(o == "skipped_by_policy" for o in outcomes):
        first_reason = str(getattr(matching[0], "reason", "") or "")
        return first_reason if "skipped_" in first_reason else "skipped_by_policy"
    return fallback_status


def _build_claim_external_meta(
    agg: ExternalAggregationResult,
    claim_id: str,
    claim_text: str,
) -> Tuple[List[Any], List[Any], Dict[str, Any]]:
    """
    Constructs strictly claim-isolated external evidence lists and metadata so external
    ClaimReviews, GDELT articles, or conflicts from Claim A cannot leak to Claim B.
    """
    has_scoped_data = bool(
        claim_id in getattr(agg, "retrieval_attempts_by_claim", {})
        or claim_id in getattr(agg, "fact_check_matches_by_claim", {})
        or claim_id in getattr(agg, "news_evidence_by_claim", {})
    )
    if has_scoped_data:
        fc_matches = list(agg.fact_check_matches_by_claim.get(claim_id, []))
        news_ev = list(agg.news_evidence_by_claim.get(claim_id, []))
        claim_attempts = list(agg.retrieval_attempts_by_claim.get(claim_id, []))
        has_fc_conflict = bool(agg.conflicting_fact_checks_by_claim.get(claim_id, False))
        has_fc_stale = bool(agg.stale_fact_checks_by_claim.get(claim_id, False))
        gd_conflict = bool(agg.gdelt_conflicting_by_claim.get(claim_id, False))
        dupes = int(agg.duplicates_collapsed_by_claim.get(claim_id, 0))
        fc_dirs = dict(agg.fact_check_directions_by_claim.get(claim_id, {}))
        google_st = _derive_provider_status_from_attempts(claim_attempts, "google_fact_check", agg.google_status)
        gdelt_st = _derive_provider_status_from_attempts(claim_attempts, "gdelt", agg.gdelt_status)
        selections = [
            s for s in agg.gdelt_claim_selections
            if s.get("claim_id") == claim_id or (not s.get("claim_id") and s.get("claim") == claim_text)
        ]
    else:
        # Fallback solely for lightweight test mocks that return a bare ExternalAggregationResult
        norm_c = re.sub(r"\s+", " ", claim_text or "").strip().lower()
        fc_matches = [
            m for m in agg.fact_check_matches
            if not getattr(m, "claim_id", None) or getattr(m, "claim_id") == claim_id
        ]
        news_ev = [
            a for a in agg.news_evidence
            if not getattr(a, "claim_id", None) or getattr(a, "claim_id") == claim_id
        ]
        claim_attempts = [
            att for att in agg.retrieval_attempts
            if (getattr(att, "claim_id", None) == claim_id)
            or (
                not getattr(att, "claim_id", None)
                and (not getattr(att, "claim_text", None) or re.sub(r"\s+", " ", getattr(att, "claim_text", "")).strip().lower() == norm_c)
            )
        ]
        has_fc_conflict = bool(agg.has_conflicting_fact_checks) if fc_matches or not agg.fact_check_matches else False
        has_fc_stale = bool(agg.has_stale_fact_checks) if fc_matches else False
        gd_conflict = bool(agg.gdelt_conflicting_coverage) if news_ev else False
        dupes = agg.duplicates_collapsed if news_ev else 0
        fc_dirs = dict(agg.fact_check_directions)
        google_st = agg.google_status
        gdelt_st = agg.gdelt_status
        selections = [s for s in agg.gdelt_claim_selections if s.get("claim") == claim_text]

    ext_meta = {
        "google_status": google_st,
        "google_error": agg.google_error if not fc_matches else None,
        "gdelt_status": gdelt_st,
        "gdelt_error": agg.gdelt_error if not news_ev else None,
        "has_conflicting_fact_checks": has_fc_conflict,
        "has_stale_fact_checks": has_fc_stale,
        "gdelt_conflicting_coverage": gd_conflict,
        "duplicates_collapsed": dupes,
        "retrieval_attempts": claim_attempts,
        "fact_check_directions": fc_dirs,
        "gdelt_claim_selections": selections,
    }
    return fc_matches, news_ev, ext_meta


def _to_audit_trail_schema(
    trail: EvidenceAuditTrail,
    *,
    gdelt_claim_selections: Optional[List[Dict[str, Any]]] = None,
) -> EvidenceAuditTrailSchema:
    sigs = trail.initial_ml_signals
    nli_ev = trail.nli_evaluation
    qs = trail.evidence_quality_summary
    return EvidenceAuditTrailSchema(
        initial_ml_signals=InitialMLSignalsSchema(
            liar_signal=_to_model_signal_schema(sigs.liar_signal),
            isot_signal=_to_model_signal_schema(sigs.isot_signal),
            preliminary_verdict=sigs.preliminary_verdict,
            note=sigs.note,
        ),
        nli_evaluation=DebertaNLISummarySchema(
            model_name=nli_ev.model_name,
            evaluation_stage=nli_ev.evaluation_stage,
            pairs_evaluated=nli_ev.pairs_evaluated,
            raw_label_counts=dict(nli_ev.raw_label_counts),
            calibrated_label_counts=dict(nli_ev.calibrated_label_counts),
            max_raw_probability=nli_ev.max_raw_probability,
            disclaimer=nli_ev.disclaimer,
        ),
        directions_executed=list(trail.directions_executed),
        queries_by_direction=dict(trail.queries_by_direction),
        retrieval_attempts=[
            RetrievalAttemptSchema(
                provider=ra.provider,
                direction=ra.direction,
                query=ra.query,
                outcome=ra.outcome,
                available=ra.available,
                from_cache=ra.from_cache,
                items_retrieved=ra.items_retrieved,
                relevant_items=ra.relevant_items,
                reason=ra.reason,
                claim_text=ra.claim_text,
                claim_id=getattr(ra, "claim_id", None),
            )
            for ra in trail.retrieval_attempts
        ],
        gdelt_claim_selections=list(gdelt_claim_selections or []),
        supporting_evidence=[_to_audit_source_schema(i) for i in trail.supporting_evidence],
        contradicting_evidence=[_to_audit_source_schema(i) for i in trail.contradicting_evidence],
        neutral_evidence=[_to_audit_source_schema(i) for i in trail.neutral_evidence],
        rejected_irrelevant_evidence=[_to_audit_source_schema(i) for i in trail.rejected_irrelevant_evidence],
        conflicts_detected=trail.conflicts_detected,
        conflict_details=list(trail.conflict_details),
        provider_statuses=[
            ProviderStatusItemSchema(
                provider=p.provider,
                status=p.status,
                available=p.available,
                items_retrieved=p.items_retrieved,
                relevant_items=p.relevant_items,
                error_or_reason=p.error_or_reason,
            )
            for p in trail.provider_statuses
        ],
        unavailable_providers=list(trail.unavailable_providers),
        evidence_quality_summary=EvidenceQualitySummarySchema(
            support_count=qs.support_count,
            contradict_count=qs.contradict_count,
            neutral_count=qs.neutral_count,
            independent_supporting_sources=qs.independent_supporting_sources,
            independent_contradicting_sources=qs.independent_contradicting_sources,
            rejected_irrelevant_count=qs.rejected_irrelevant_count,
            syndicated_duplicates_collapsed=qs.syndicated_duplicates_collapsed,
            max_support_quality=qs.max_support_quality,
            max_contradict_quality=qs.max_contradict_quality,
            temporal_mismatch_detected=qs.temporal_mismatch_detected,
            geographic_mismatch_detected=qs.geographic_mismatch_detected,
            tier1_official_primary_count=qs.tier1_official_primary_count,
            tier2_encyclopedic_count=qs.tier2_encyclopedic_count,
            tier3_secondary_or_metadata_count=qs.tier3_secondary_or_metadata_count,
            primary_official_sources_available=qs.primary_official_sources_available,
            claim_requires_primary_record=qs.claim_requires_primary_record,
            primary_record_need_reason=qs.primary_record_need_reason,
            methodology_note=qs.methodology_note,
        ),
        second_pass_decision=trail.second_pass_decision,
        verdict_changed_from_initial=trail.verdict_changed_from_initial,
        verdict_change_reason=trail.verdict_change_reason,
        second_pass_reasoning=trail.second_pass_reasoning,
        final_verdict=trail.final_verdict,
        final_confidence=trail.final_confidence,
        total_retrieval_attempts=getattr(trail, "total_retrieval_attempts", len(trail.retrieval_attempts)),
        omitted_retrieval_attempts=getattr(trail, "omitted_retrieval_attempts", 0),
    )


def _rollup_multi_claim_audit_trail(
    sub_trails: List[EvidenceAuditTrailSchema],
    initial_signals: InitialMLSignalsSchema,
    final_verdict: str,
    final_confidence: float,
    summary_reasoning: str,
    gdelt_claim_selections: Optional[List[Dict[str, Any]]] = None,
) -> Optional[EvidenceAuditTrailSchema]:
    if not sub_trails:
        return None
    seen_sup, seen_con, seen_neu, seen_rej = set(), set(), set(), set()
    sup_all, con_all, neu_all, rej_all = [], [], [], []
    conflicts = []
    unavail = []
    attempts_all: List[RetrievalAttemptSchema] = []
    seen_attempt_keys = set()
    raw_nli_sum = {"SUPPORTS": 0, "REFUTES": 0, "NOT ENOUGH INFO": 0}
    cal_nli_sum = {"SUPPORTS": 0, "REFUTES": 0, "NOT ENOUGH INFO": 0}
    pairs_total = 0
    max_nli_p = 0.0

    for st in sub_trails:
        pairs_total += st.nli_evaluation.pairs_evaluated
        max_nli_p = max(max_nli_p, st.nli_evaluation.max_raw_probability)
        for lbl, cnt in st.nli_evaluation.raw_label_counts.items():
            raw_nli_sum[lbl] = raw_nli_sum.get(lbl, 0) + cnt
        for lbl, cnt in st.nli_evaluation.calibrated_label_counts.items():
            cal_nli_sum[lbl] = cal_nli_sum.get(lbl, 0) + cnt
        for att in st.retrieval_attempts:
            akey = (att.claim_id or att.claim_text or "", att.provider, att.direction, att.query, att.outcome)
            if akey not in seen_attempt_keys:
                seen_attempt_keys.add(akey)
                attempts_all.append(att)
        for item in st.supporting_evidence:
            k = (item.source_type, item.title_or_page, item.text_excerpt[:80])
            if k not in seen_sup:
                seen_sup.add(k)
                sup_all.append(item)
        for item in st.contradicting_evidence:
            k = (item.source_type, item.title_or_page, item.text_excerpt[:80])
            if k not in seen_con:
                seen_con.add(k)
                con_all.append(item)
        for item in st.neutral_evidence:
            k = (item.source_type, item.title_or_page, item.text_excerpt[:80])
            if k not in seen_neu:
                seen_neu.add(k)
                neu_all.append(item)
        for item in st.rejected_irrelevant_evidence:
            k = (item.source_type, item.title_or_page, item.text_excerpt[:80])
            if k not in seen_rej:
                seen_rej.add(k)
                rej_all.append(item)
        for c in st.conflict_details:
            if c not in conflicts:
                conflicts.append(c)
        for u in st.unavailable_providers:
            if u not in unavail:
                unavail.append(u)

    verdict_changed = final_verdict != initial_signals.preliminary_verdict
    if final_verdict == "UNVERIFIED" and initial_signals.preliminary_verdict != "UNVERIFIED":
        decision = "abstained_insufficient"
        change_reason = f"Preliminary linguistic signal ({initial_signals.preliminary_verdict}) abstained to UNVERIFIED across aggregated claims due to insufficient or non-primary evidence."
    elif verdict_changed:
        decision = "overridden_by_evidence"
        change_reason = f"Second-Pass multi-claim evaluation changed preliminary linguistic signal ({initial_signals.preliminary_verdict}) to {final_verdict}."
    elif conflicts or unavail or any(st.conflicts_detected for st in sub_trails):
        decision = "downgraded_uncertainty"
        change_reason = None
    else:
        decision = "confirmed_initial"
        change_reason = None

    first_qs = sub_trails[0].evidence_quality_summary
    rel_all = sup_all + con_all + neu_all
    t1_c = sum(1 for i in rel_all if i.evidence_tier == "TIER_1_PRIMARY_OFFICIAL")
    t2_c = sum(1 for i in rel_all if i.evidence_tier == "TIER_2_SECONDARY_ENCYCLOPEDIC")
    t3_c = sum(1 for i in rel_all if i.evidence_tier == "TIER_3_SECONDARY_OR_METADATA")
    return EvidenceAuditTrailSchema(
        initial_ml_signals=initial_signals,
        nli_evaluation=DebertaNLISummarySchema(
            model_name=sub_trails[0].nli_evaluation.model_name,
            evaluation_stage="post_retrieval_claim_evidence_pair",
            pairs_evaluated=pairs_total,
            raw_label_counts=raw_nli_sum,
            calibrated_label_counts=cal_nli_sum,
            max_raw_probability=round(max_nli_p, 4),
            disclaimer=sub_trails[0].nli_evaluation.disclaimer,
        ),
        directions_executed=list(sub_trails[0].directions_executed),
        queries_by_direction=dict(sub_trails[0].queries_by_direction),
        retrieval_attempts=attempts_all,
        gdelt_claim_selections=list(gdelt_claim_selections or sub_trails[0].gdelt_claim_selections),
        supporting_evidence=sup_all[:12],
        contradicting_evidence=con_all[:12],
        neutral_evidence=neu_all[:10],
        rejected_irrelevant_evidence=rej_all[:8],
        conflicts_detected=any(st.conflicts_detected for st in sub_trails) or bool(conflicts),
        conflict_details=conflicts,
        provider_statuses=list(sub_trails[0].provider_statuses),
        unavailable_providers=unavail,
        evidence_quality_summary=EvidenceQualitySummarySchema(
            support_count=len(sup_all),
            contradict_count=len(con_all),
            neutral_count=len(neu_all),
            independent_supporting_sources=len({i.independent_group_key for i in sup_all}),
            independent_contradicting_sources=len({i.independent_group_key for i in con_all}),
            rejected_irrelevant_count=len(rej_all),
            syndicated_duplicates_collapsed=max((st.evidence_quality_summary.syndicated_duplicates_collapsed for st in sub_trails), default=0),
            max_support_quality=max((i.overall_quality_score for i in sup_all), default=0.0),
            max_contradict_quality=max((i.overall_quality_score for i in con_all), default=0.0),
            temporal_mismatch_detected=any(st.evidence_quality_summary.temporal_mismatch_detected for st in sub_trails),
            geographic_mismatch_detected=any(st.evidence_quality_summary.geographic_mismatch_detected for st in sub_trails),
            tier1_official_primary_count=t1_c,
            tier2_encyclopedic_count=t2_c,
            tier3_secondary_or_metadata_count=t3_c,
            primary_official_sources_available=(t1_c > 0),
            claim_requires_primary_record=any(st.evidence_quality_summary.claim_requires_primary_record for st in sub_trails),
            primary_record_need_reason=next(
                (st.evidence_quality_summary.primary_record_need_reason for st in sub_trails if st.evidence_quality_summary.primary_record_need_reason),
                None,
            ),
            methodology_note=first_qs.methodology_note,
        ),
        second_pass_decision=decision,
        verdict_changed_from_initial=verdict_changed,
        verdict_change_reason=change_reason,
        second_pass_reasoning=summary_reasoning,
        final_verdict=final_verdict,
        final_confidence=final_confidence,
        total_retrieval_attempts=len(attempts_all),
        omitted_retrieval_attempts=0,
    )


class VerificationService:
    def __init__(self):
        self.retriever = get_retriever()
        self.verifier = get_claim_verifier()
        self.synthesizer = get_verdict_synthesizer()
        self.second_pass_evaluator = get_second_pass_evaluator()
        self.article_classifier = get_article_classifier()
        self.claim_classifier = get_claim_classifier()
        self.claim_extractor = get_claim_extractor()
        self.external_aggregator = ExternalEvidenceAggregator()

    def _collect_external_safe(
        self,
        claims: List[str],
        *,
        source_label: str,
        max_fact_check_queries: int = 2,
        max_gdelt_queries: int = 1,
        gdelt_eligible_claims: Optional[List[str]] = None,
        gdelt_skipped_claims: Optional[List[Any]] = None,
        claim_ids: Optional[List[str]] = None,
    ) -> ExternalAggregationResult:
        resolved_ids = [
            claim_ids[i] if (claim_ids and i < len(claim_ids) and claim_ids[i]) else f"claim_{i + 1}"
            for i in range(len(claims))
        ]
        try:
            return self.external_aggregator.collect_independent_external_evidence(
                claims=claims,
                source_label=source_label,
                max_fact_check_queries=max_fact_check_queries,
                max_gdelt_queries=max_gdelt_queries,
                gdelt_eligible_claims=gdelt_eligible_claims,
                gdelt_skipped_claims=gdelt_skipped_claims,
                claim_ids=resolved_ids,
            )
        except Exception as ext_exc:
            safe_exc = sanitize_secret_text(str(ext_exc))
            reason_msg = f"external_aggregator_exception: {safe_exc or type(ext_exc).__name__}"
            logger.warning(f"External evidence collection degraded safely (non-fatal): {safe_exc}")
            failed_attempts: List[RetrievalAttempt] = []
            by_claim_attempts: Dict[str, List[RetrievalAttempt]] = {}
            for cid, cl in zip(resolved_ids, claims):
                c_txt = (cl or "").strip()
                c_atts = [
                    RetrievalAttempt(
                        provider="google_fact_check",
                        direction="neutral",
                        query=c_txt[:280],
                        outcome="network_error",
                        available=False,
                        from_cache=False,
                        items_retrieved=0,
                        relevant_items=0,
                        reason=reason_msg,
                        claim_text=c_txt,
                        claim_id=cid,
                    ),
                    RetrievalAttempt(
                        provider="gdelt",
                        direction="neutral",
                        query=c_txt[:120],
                        outcome="network_error",
                        available=False,
                        from_cache=False,
                        items_retrieved=0,
                        relevant_items=0,
                        reason=reason_msg,
                        claim_text=c_txt,
                        claim_id=cid,
                    ),
                ]
                failed_attempts.extend(c_atts)
                by_claim_attempts[cid] = c_atts
            return ExternalAggregationResult(
                google_status="network_error",
                google_available=False,
                google_error="Google Fact Check lookup unavailable.",
                gdelt_status="network_error",
                gdelt_error="GDELT lookup unavailable.",
                retrieval_attempts=failed_attempts,
                retrieval_attempts_by_claim=by_claim_attempts,
            )

    def _evaluate_single_claim(
        self,
        claim: str,
        top_k: int = 5,
        retrieval_query: Optional[str] = None,
    ) -> Tuple[SynthesisResult, List[EvidenceSentenceSchema]]:
        """Legacy helper running independent evaluation cleanly for single claims."""
        synthesis, ev_schemas, _, _ = self._evaluate_single_claim_ieve(
            claim=claim,
            top_k=top_k,
            retrieval_query=retrieval_query,
        )
        return synthesis, ev_schemas

    def _evaluate_single_claim_ieve(
        self,
        claim: str,
        top_k: int = 5,
        retrieval_query: Optional[str] = None,
        fact_check_matches: Optional[List[Any]] = None,
        news_evidence: Optional[List[Any]] = None,
        external_meta: Optional[Dict[str, Any]] = None,
        isot_res: Optional[Any] = None,
        claim_id: Optional[str] = None,
    ):
        """
        Full prediction-independent IEVE evaluation for one claim:
          1. Separate Preliminary ML linguistic signals (LIAR BERT / optional article ISOT BERT)
             recorded without combination — NEVER filters retrieval.
          2. Independent support/contradict/neutral query construction & retrieval
          3. Batched DeBERTa NLI inference (strictly post-retrieval evaluation stage)
          4. Second-Pass Tiered Sufficiency & verdict synthesis + audit trail
        """
        liar_res = self.claim_classifier.classify(claim)
        liar_sig = ModelSignalRecord(
            model_name=liar_res.model_name,
            dataset_origin="LIAR",
            applicable_input_type="short_claim",
            applicable=True,
            prediction=liar_res.prediction,
            confidence=liar_res.confidence,
            probabilities=dict(liar_res.probabilities),
            raw_logits=dict(getattr(liar_res, "raw_logits", {}) or {}),
            preliminary_verdict_tag=map_classifier_to_preliminary_verdict(liar_prediction=liar_res.prediction),
            disclaimer=liar_res.disclaimer,
        )
        if isot_res is not None:
            isot_sig = ModelSignalRecord(
                model_name=isot_res.model_name,
                dataset_origin="ISOT",
                applicable_input_type="full_article",
                applicable=True,
                prediction=isot_res.prediction,
                confidence=isot_res.confidence,
                probabilities=dict(isot_res.probabilities),
                raw_logits=dict(getattr(isot_res, "raw_logits", {}) or {}),
                preliminary_verdict_tag=map_classifier_to_preliminary_verdict(isot_prediction=isot_res.prediction),
                disclaimer=isot_res.distribution_shift_warning,
            )
        else:
            isot_sig = ModelSignalRecord(
                model_name="google-bert/bert-base-uncased",
                dataset_origin="ISOT",
                applicable_input_type="full_article",
                applicable=False,
                prediction=None,
                confidence=None,
                probabilities={},
                raw_logits={},
                preliminary_verdict_tag=None,
                disclaimer="ISOT BERT applies to full articles only; omitted cleanly on standalone short text claims.",
            )

        initial_signals = InitialMLSignals(
            liar_signal=liar_sig,
            isot_signal=isot_sig,
            preliminary_verdict=liar_sig.preliminary_verdict_tag or "UNVERIFIED",
        )

        search_text = retrieval_query or claim
        dir_queries = build_directional_queries(search_text)
        evidence_sentences, retrieval_meta = self.retriever.retrieve_independent(
            search_text,
            dir_queries.to_dict(),
            top_k=top_k,
        )
        verified_evidence = self.verifier.verify(search_text, evidence_sentences)
        phase1_synthesis = self.synthesizer.synthesize(search_text, verified_evidence, retrieval_meta=retrieval_meta)

        final_synthesis, audit_trail = self.second_pass_evaluator.evaluate(
            claim=search_text,
            initial_signals=initial_signals,
            directional_queries=dir_queries,
            documentary_evidence=verified_evidence,
            phase1_synthesis=phase1_synthesis,
            fact_check_matches=fact_check_matches,
            news_evidence=news_evidence,
            retrieval_meta=retrieval_meta,
            external_meta=external_meta,
            claim_id=claim_id,
        )
        evidence_schemas = [_to_evidence_schema(ve) for ve in verified_evidence]
        ext_sel = (external_meta or {}).get("gdelt_claim_selections")
        audit_schema = _to_audit_trail_schema(audit_trail, gdelt_claim_selections=ext_sel)
        return final_synthesis, evidence_schemas, audit_schema, liar_res

    def verify_text_claim(self, request: TextVerificationRequest) -> TextVerificationResponse:
        claim = request.claim
        top_k = request.top_k
        logger.info(f"Processing IEVE text verification: '{claim[:80]}...' (top_k={top_k})")

        sub_claims = split_compound_claims(claim)
        ext_claims = [claim] if len(sub_claims) <= 1 else sub_claims
        ext_claim_ids = ["claim_1"] if len(sub_claims) <= 1 else [f"sub_{i}" for i in range(1, len(ext_claims) + 1)]
        gd_eligible_text = ext_claims[:1] if len(sub_claims) > 1 else None
        gd_skipped_text = (
            [
                (
                    f"sub_{i}",
                    c_txt,
                    "skipped_compound_gdelt_cap_max1: excluded by 1-GDELT-query-per-text-claim conservation cap",
                )
                for i, c_txt in enumerate(ext_claims[1:], 2)
            ]
            if len(sub_claims) > 1
            else None
        )

        # Prediction-independent external evidence collection BEFORE second-pass synthesis
        agg = self._collect_external_safe(
            claims=ext_claims,
            source_label="verify_text",
            max_fact_check_queries=2,
            max_gdelt_queries=1,
            gdelt_eligible_claims=gd_eligible_text,
            gdelt_skipped_claims=gd_skipped_text,
            claim_ids=ext_claim_ids,
        )
        fc_schemas, news_schemas, ext_status_schema = _to_external_schemas(agg)

        audit_schema: Optional[EvidenceAuditTrailSchema] = None
        if len(sub_claims) <= 1:
            cl_fc, cl_news, cl_ext_meta = _build_claim_external_meta(agg, "claim_1", claim)
            synthesis, evidence_schemas, audit_schema, _ = self._evaluate_single_claim_ieve(
                claim,
                top_k=top_k,
                fact_check_matches=cl_fc,
                news_evidence=cl_news,
                external_meta=cl_ext_meta,
                claim_id="claim_1",
            )
            final_verdict = VerdictEnum(synthesis.verdict)
            final_conf = synthesis.confidence_score
            final_explanation = synthesis.explanation
            final_uncertainty = synthesis.uncertainty_explanation
            conflicting = synthesis.conflicting_evidence_detected
            strongest_page = synthesis.strongest_evidence_page
            limitations = list(synthesis.limitations)
            sub_verdict_schemas: List[SubClaimVerdictSchema] = []
        else:
            logger.info(f"Decomposed compound claim into {len(sub_claims)} sub-claims.")
            sub_pairs: List[Tuple[str, SynthesisResult]] = []
            sub_verdict_schemas = []
            sub_trails: List[EvidenceAuditTrailSchema] = []
            combined_evidence: List[EvidenceSentenceSchema] = []
            seen_ev_keys = set()
            limitations = list(self.synthesizer.DEFAULT_LIMITATIONS)

            per_claim_k = max(3, min(top_k, 5))
            for s_idx, sub in enumerate(sub_claims, 1):
                cid = f"sub_{s_idx}"
                sub_fc, sub_news, sub_ext_meta = _build_claim_external_meta(agg, cid, sub)
                s_res, s_ev, s_audit, _ = self._evaluate_single_claim_ieve(
                    sub,
                    top_k=per_claim_k,
                    fact_check_matches=sub_fc,
                    news_evidence=sub_news,
                    external_meta=sub_ext_meta,
                    claim_id=cid,
                )
                sub_pairs.append((sub, s_res))
                sub_trails.append(s_audit)
                sub_verdict_schemas.append(
                    SubClaimVerdictSchema(
                        claim=sub,
                        verdict=VerdictEnum(s_res.verdict),
                        confidence_score=s_res.confidence_score,
                        explanation=s_res.explanation,
                        uncertainty_explanation=s_res.uncertainty_explanation,
                        evidence=s_ev[:3],
                        evidence_audit_trail=s_audit,
                    )
                )
                for ev_item in s_ev:
                    key = (ev_item.doc_id, ev_item.text[:80])
                    if key not in seen_ev_keys:
                        seen_ev_keys.add(key)
                        combined_evidence.append(ev_item)

            combined_evidence.sort(key=lambda e: e.retrieval_similarity, reverse=True)
            for idx, ev_item in enumerate(combined_evidence[:10], 1):
                ev_item.rank = idx
            evidence_schemas = combined_evidence[:10]

            final_verdict, final_conf, final_explanation, final_uncertainty = _aggregate_multi_claim_verdicts(
                sub_pairs, context_label="sub-claims"
            )
            conflicting = any(res.conflicting_evidence_detected for _, res in sub_pairs) or final_verdict == VerdictEnum.PARTIALLY_TRUE
            strongest_page = evidence_schemas[0].page if evidence_schemas else None
            if sub_trails:
                audit_schema = _rollup_multi_claim_audit_trail(
                    sub_trails,
                    initial_signals=sub_trails[0].initial_ml_signals,
                    final_verdict=final_verdict.value,
                    final_confidence=final_conf,
                    summary_reasoning=final_explanation,
                    gdelt_claim_selections=agg.gdelt_claim_selections,
                )

        if agg.has_conflicting_fact_checks or agg.gdelt_conflicting_coverage:
            conflicting = True
        if agg.supplementary_notes:
            notes_joined = " ".join(agg.supplementary_notes)
            final_uncertainty = f"{final_uncertainty} {notes_joined}".strip() if final_uncertainty else notes_joined
        for lim in agg.limitations:
            if lim not in limitations:
                limitations.append(lim)

        resp = TextVerificationResponse(
            claim=claim,
            verdict=final_verdict,
            confidence_score=final_conf,
            explanation=final_explanation,
            uncertainty_explanation=final_uncertainty,
            conflicting_evidence_detected=conflicting,
            strongest_evidence_page=strongest_page,
            evidence=evidence_schemas,
            claim_verdicts=sub_verdict_schemas,
            fact_check_matches=fc_schemas,
            news_evidence=news_schemas,
            external_source_status=ext_status_schema,
            evidence_audit_trail=audit_schema,
            limitations=limitations,
        )
        try:
            summary = create_hash_summary_from_text(claim, resp)
            resp.blockchain_hash = summary.model_dump()
            from backend.app.database.repository import save_verification_record
            save_verification_record(
                verification_id=resp.verification_id,
                content_type="text",
                title=None,
                content_preview=claim[:200],
                original_content=claim,
                verdict=resp.verdict.value,
                confidence_score=resp.confidence_score,
                explanation=resp.explanation,
                evidence_data=[e.model_dump() for e in resp.evidence],
                canonical_record_dict=resp.blockchain_hash["canonical_record"],
                record_hash=resp.blockchain_hash["record_hash"],
                created_at=resp.created_at,
            )
        except Exception as e:
            logger.warning(f"Could not compute or persist canonical verification hash: {e}")
        return resp

    def verify_article(self, request: ArticleVerificationRequest) -> ArticleVerificationResponse:
        logger.info(f"Verifying article via IEVE: '{request.title or 'Untitled'}' ({len(request.text)} chars)")

        # 1. ISOT Statistical Article Classification (Preliminary Signal — NEVER filters retrieval)
        isot_res = self.article_classifier.classify(request.text, title=request.title)

        # 2. Factual Claim Extraction & Subject Context Detection
        candidate_claims = self.claim_extractor.extract_claims(
            request.text,
            title=request.title,
            max_claims=request.max_claims,
        )
        lead_subject = _extract_article_lead_subject(request.text, request.title)

        # 2.5 Prediction-independent external evidence collection BEFORE second-pass synthesis
        # Decision 2 Option A: up to 2 neutral GDELT claims selected strictly by centrality x materiality;
        # ALL extracted claims receive Google Fact Check + bidirectional local FAISS + Wikipedia fallback.
        all_claim_entries: List[Tuple[str, str]] = [
            (f"claim_{idx}", c.text.strip())
            for idx, c in enumerate(candidate_claims, 1)
            if c.text and c.text.strip()
        ]
        if not all_claim_entries and request.title and request.title.strip():
            all_claim_entries = [("claim_1", request.title.strip())]
        all_claim_texts = [txt for _, txt in all_claim_entries]
        all_claim_ids = [cid for cid, _ in all_claim_entries]

        max_rel = max((max(0.1, float(c.relevance_score)) for c in candidate_claims), default=1.0)
        scored_gdelt_pool: List[Tuple[float, str, str]] = []
        for rank_idx, cand in enumerate(candidate_claims, 1):
            c_txt = (cand.text or "").strip()
            if not c_txt:
                continue
            cid = f"claim_{rank_idx}"
            norm_rel = max(0.15, min(1.0, float(cand.relevance_score) / max_rel))
            rank_decay = 1.0 if rank_idx == 1 else (0.88 if rank_idx == 2 else (0.76 if rank_idx == 3 else 0.38))
            centrality_w = 0.65 * rank_decay + 0.35 * norm_rel
            mat_w, _ = _compute_factual_materiality(c_txt)
            scored_gdelt_pool.append((round(centrality_w * mat_w, 4), cid, c_txt))

        scored_gdelt_pool.sort(key=lambda item: item[0], reverse=True)
        gdelt_eligible = [txt for _, _, txt in scored_gdelt_pool[:2]]
        if not gdelt_eligible and all_claim_texts:
            gdelt_eligible = all_claim_texts[:2]
        gdelt_skipped = [
            (
                cid,
                txt,
                "skipped_article_gdelt_cap_max2: excluded to respect 2-GDELT-query-per-article quota conservation cap (lower centrality x materiality than top 2 claims)",
            )
            for _, cid, txt in scored_gdelt_pool[2:]
        ]

        agg = self._collect_external_safe(
            claims=all_claim_texts,
            source_label="verify_article",
            max_fact_check_queries=max(2, len(all_claim_texts) * 2),
            max_gdelt_queries=2,
            gdelt_eligible_claims=gdelt_eligible,
            gdelt_skipped_claims=gdelt_skipped,
            claim_ids=all_claim_ids,
        )
        fc_schemas, news_schemas, ext_status_schema = _to_external_schemas(agg)

        extracted_results: List[ExtractedClaimVerification] = []
        claim_pairs: List[Tuple[str, SynthesisResult]] = []
        candidate_weights: List[Tuple[int, float]] = []
        claim_trails: List[EvidenceAuditTrailSchema] = []

        # 3. Verify each candidate claim independently through full IEVE pass (isolated per claim_id)
        for rank, candidate in enumerate(candidate_claims, 1):
            cid = f"claim_{rank}"
            resolved_query = _resolve_anaphora_for_retrieval(candidate.text, lead_subject)
            cl_fc, cl_news, cl_ext_meta = _build_claim_external_meta(agg, cid, candidate.text)
            synthesis, ev_schemas, claim_audit, liar_res = self._evaluate_single_claim_ieve(
                candidate.text,
                top_k=3,
                retrieval_query=resolved_query,
                fact_check_matches=cl_fc,
                news_evidence=cl_news,
                external_meta=cl_ext_meta,
                isot_res=isot_res,
                claim_id=cid,
            )
            claim_pairs.append((candidate.text, synthesis))
            candidate_weights.append((rank, candidate.relevance_score))
            claim_trails.append(claim_audit)

            liar_signal = LIARClassifierSignal(
                model=liar_res.model_name,
                prediction=liar_res.prediction,
                confidence=liar_res.confidence,
                probabilities=liar_res.probabilities,
                disclaimer=liar_res.disclaimer,
            )

            extracted_results.append(
                ExtractedClaimVerification(
                    claim=candidate.text,
                    relevance_rank=rank,
                    verdict=VerdictEnum(synthesis.verdict),
                    confidence_score=synthesis.confidence_score,
                    explanation=synthesis.explanation,
                    uncertainty_explanation=synthesis.uncertainty_explanation,
                    evidence=ev_schemas,
                    liar_signal=liar_signal,
                    evidence_audit_trail=claim_audit,
                )
            )

        # 4. Article-Level Weighted Six-Class Verdict Aggregation (centrality x materiality x evidence)
        overall_verdict, overall_conf, explanation, uncertainty = _aggregate_multi_claim_verdicts(
            claim_pairs,
            context_label="extracted claims",
            candidate_weights=candidate_weights,
        )

        limitations = [
            "Article verification evaluates extracted core claims via prediction-independent directional FEVER FAISS + Wikipedia retrieval, external Fact Checks/GDELT, and Second-Pass synthesis.",
            "ISOT article predictions reflect stylistic pattern similarity and cannot determine factual truth on their own.",
            "LIAR claim classifications (~26.8% benchmark accuracy) are strictly exploratory linguistic signals.",
            "Absence of matching evidence in knowledge sources defaults to UNVERIFIED, never proof of falsehood.",
        ]

        if agg.supplementary_notes:
            notes_joined = " ".join(agg.supplementary_notes)
            uncertainty = f"{uncertainty} {notes_joined}".strip() if uncertainty else notes_joined
        for lim in agg.limitations:
            if lim not in limitations:
                limitations.append(lim)

        isot_art_sig = ModelSignalSchema(
            model_name=isot_res.model_name,
            dataset_origin="ISOT",
            applicable_input_type="full_article",
            applicable=True,
            prediction=isot_res.prediction,
            confidence=isot_res.confidence,
            probabilities=dict(isot_res.probabilities),
            raw_logits=dict(getattr(isot_res, "raw_logits", {}) or {}),
            preliminary_verdict_tag=map_classifier_to_preliminary_verdict(isot_prediction=isot_res.prediction),
            disclaimer=isot_res.distribution_shift_warning,
        )
        lead_liar_sig = (
            claim_trails[0].initial_ml_signals.liar_signal
            if claim_trails
            else ModelSignalSchema(
                model_name="bert-base-uncased",
                dataset_origin="LIAR",
                applicable_input_type="short_claim",
                applicable=False,
                disclaimer="No extracted claims were available for LIAR claim signal scoring.",
            )
        )
        art_initial_signals = InitialMLSignalsSchema(
            liar_signal=lead_liar_sig,
            isot_signal=isot_art_sig,
            preliminary_verdict=isot_art_sig.preliminary_verdict_tag or "UNVERIFIED",
        )
        article_audit_trail = _rollup_multi_claim_audit_trail(
            claim_trails,
            initial_signals=art_initial_signals,
            final_verdict=overall_verdict.value,
            final_confidence=overall_conf,
            summary_reasoning=explanation,
            gdelt_claim_selections=agg.gdelt_claim_selections,
        )

        art_resp = ArticleVerificationResponse(
            title=request.title,
            overall_verdict=overall_verdict,
            overall_confidence=overall_conf,
            summary_explanation=explanation,
            uncertainty_explanation=uncertainty,
            article_classifier=ArticleClassifierSignal(
                model=isot_res.model_name,
                prediction=isot_res.prediction,
                confidence=isot_res.confidence,
                probabilities=isot_res.probabilities,
                distribution_shift_warning=isot_res.distribution_shift_warning,
            ),
            claims_analyzed=len(extracted_results),
            extracted_claims=extracted_results,
            fact_check_matches=fc_schemas,
            news_evidence=news_schemas,
            external_source_status=ext_status_schema,
            evidence_audit_trail=article_audit_trail,
            limitations=limitations,
        )
        try:
            summary = create_hash_summary_from_article(request.text, art_resp)
            art_resp.blockchain_hash = summary.model_dump()
            from backend.app.database.repository import save_verification_record
            save_verification_record(
                verification_id=art_resp.article_id,
                content_type="article",
                title=art_resp.title,
                content_preview=(art_resp.title or request.text[:200]),
                original_content=request.text,
                verdict=art_resp.overall_verdict.value,
                confidence_score=art_resp.overall_confidence,
                explanation=art_resp.summary_explanation,
                evidence_data=[c.model_dump() for c in art_resp.extracted_claims],
                canonical_record_dict=art_resp.blockchain_hash["canonical_record"],
                record_hash=art_resp.blockchain_hash["record_hash"],
                created_at=art_resp.created_at,
            )
        except Exception as e:
            logger.warning(f"Could not compute or persist canonical article verification hash: {e}")
        return art_resp


_service_instance = None
_service_lock = threading.Lock()


def get_verification_service() -> VerificationService:
    global _service_instance
    if _service_instance is None:
        with _service_lock:
            if _service_instance is None:
                _service_instance = VerificationService()
    return _service_instance
