"""
ml/inference/evidence_quality.py

Prediction-independent directional query builder and multi-dimensional Evidence Quality Engine
for the Independent Evidence Verification Engine (IEVE).

Design principles:
  - Directional query builders NEVER accept any initial ML verdict/prediction as input.
  - Evaluates every retrieved item (FEVER, Wikipedia, Google Fact Check, GDELT) along
    transparent, documented quality dimensions kept strictly separate from ML model confidence.
  - Syndicated copies collapse via canonical source groups and never inflate corroboration count.
  - Geographic/jurisdictional, temporal, entity, and predicate alignment gates reject irrelevant matches.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from ml.inference.claim_verifier import VerifiedEvidence
from ml.inference.evidence_alignment import (
    AlignedEvidenceAssessment,
    MUTUALLY_EXCLUSIVE_GROUPS,
    claim_asserts_current_state,
    evaluate_evidence_alignment,
    extract_orbital_relations,
    extract_subject_entities,
    normalize_content_tokens,
)
from ml.inference.verdict_synthesizer import BROADCASTER_NETWORKS


_YEAR_RE = re.compile(r"\b((?:18|19|20)\d{2})\b")

_DIRECTIONAL_STOP = {
    "the", "is", "are", "was", "were", "be", "been", "being", "a", "an", "and",
    "or", "of", "in", "on", "at", "to", "for", "from", "by", "with", "as",
    "that", "this", "these", "those", "it", "its", "has", "have", "had",
    "did", "does", "do", "will", "would", "can", "could", "should", "may",
    "what", "when", "where", "which", "who", "how", "while", "whereas", "however",
    "not", "no", "never", "only", "solely", "exclusively", "all", "every", "always",
}

_GEO_LOCATION_TOKENS: Set[str] = set().union(*MUTUALLY_EXCLUSIVE_GROUPS[1:4], MUTUALLY_EXCLUSIVE_GROUPS[7])

TIER_1_PRIMARY_OFFICIAL = "TIER_1_PRIMARY_OFFICIAL"
TIER_2_SECONDARY_ENCYCLOPEDIC = "TIER_2_SECONDARY_ENCYCLOPEDIC"
TIER_3_SECONDARY_OR_METADATA = "TIER_3_SECONDARY_OR_METADATA"

# Documented source provenance reliability tiers: (descriptor, evidence_tier, provenance_weight)
SOURCE_RELIABILITY_TIERS: Dict[str, Tuple[str, str, float]] = {
    "official_record": ("official_first_party_record", TIER_1_PRIMARY_OFFICIAL, 0.95),
    "institutional_document": ("official_institutional_document", TIER_1_PRIMARY_OFFICIAL, 0.95),
    "wikipedia_live": ("secondary_encyclopedic_live", TIER_2_SECONDARY_ENCYCLOPEDIC, 0.78),
    "fever_local": ("secondary_encyclopedic_snapshot_2017", TIER_2_SECONDARY_ENCYCLOPEDIC, 0.68),
    "google_fact_check": ("third_party_fact_check_review", TIER_3_SECONDARY_OR_METADATA, 0.58),
    "gdelt": ("news_coverage_metadata_only", TIER_3_SECONDARY_OR_METADATA, 0.30),
    "rss": ("news_feed_metadata_only", TIER_3_SECONDARY_OR_METADATA, 0.30),
}

SOURCE_METHODOLOGY_NOTE = (
    "Tiered Source Provenance Policy: Tier 1 is reserved strictly for first-party official/institutional records; "
    "Wikipedia (wikipedia_live) and the 2017 FEVER corpus (fever_local) are Tier 2 secondary encyclopedic references "
    "that never automatically qualify for single-source primary-authority certification; single Google Fact Check reviews "
    "and GDELT headlines are Tier 3 secondary/coverage metadata unless independently corroborated. Note: the four "
    "currently configured retrieval channels provide Tier 2/3 coverage and do NOT supply Tier 1 official primary records."
)

_PRIMARY_RECORD_NEED_PATTERNS: Tuple[Tuple[re.Pattern, str], ...] = (
    (
        re.compile(r"\b(leaked\s+(?:memo|document|email|cable|report)|confidential\s+(?:memo|report|filing)|classified\s+(?:document|order|memo))\b", re.IGNORECASE),
        "Claim asserts confidential/leaked/classified institutional records requiring a Tier 1 primary document.",
    ),
    (
        re.compile(r"\b(supreme\s+court\s+ruled|court\s+(?:ruled|ordered|dismissed|upheld|verdict|indictment)|subpoena(?:ed)?)\b", re.IGNORECASE),
        "Claim asserts a formal judicial ruling/order requiring a Tier 1 court or official record.",
    ),
    (
        re.compile(r"\b(fda|sec|epa|irs|treasury|pentagon|doj|fbi|central\s+bank|federal\s+reserve|parliament|congress|ministry|regulator)\b.{0,50}\b(approved|fined|indicted|audited|enacted|passed|sanctioned|raised|cut|certified|issued|banned)\b", re.IGNORECASE),
        "Claim asserts formal institutional/regulatory action requiring a Tier 1 official record.",
    ),
    (
        re.compile(r"\b(executive\s+order|official\s+(?:audit|treaty|statute|budget|filing|transcript|clinical\s+trial)|audited\s+financial)\b", re.IGNORECASE),
        "Claim references official statutory, treaty, audit, or clinical filing data requiring Tier 1 verification.",
    ),
)


def claim_requires_official_primary_record(claim_text: str) -> Tuple[bool, Optional[str]]:
    """
    Identifies assertions whose material truth depends on an official first-party institutional,
    regulatory, judicial, statutory, or internal primary document not supplied by Tier 2/3 channels.
    """
    clean = (claim_text or "").strip()
    if not clean:
        return False, None
    for pat, reason in _PRIMARY_RECORD_NEED_PATTERNS:
        if pat.search(clean):
            return True, reason
    return False, None


@dataclass
class DirectionalQueries:
    """Prediction-independent retrieval formulations derived purely from claim semantics."""
    neutral_query: str
    support_query: str
    contradiction_query: str
    factcheck_support_query: str = ""
    factcheck_contradict_query: str = ""
    gdelt_neutral_query: str = ""

    def to_dict(self) -> Dict[str, str]:
        return {
            "neutral": self.neutral_query,
            "support": self.support_query,
            "contradict": self.contradiction_query,
            "factcheck_support": self.factcheck_support_query,
            "factcheck_contradict": self.factcheck_contradict_query,
            "gdelt_neutral": self.gdelt_neutral_query,
        }


def build_directional_queries(claim_text: str) -> DirectionalQueries:
    """
    Constructs independent neutral, support-oriented, and contradiction-oriented retrieval
    queries from claim text WITHOUT inspecting any ML prediction or preliminary verdict.
    """
    clean = re.sub(r"\s+", " ", (claim_text or "").strip())
    if not clean:
        return DirectionalQueries(neutral_query="", support_query="", contradiction_query="")

    entities = extract_subject_entities(clean)
    tokens = re.findall(r"[A-Za-z0-9\-]+", clean)
    content_tokens = [t for t in tokens if t.lower() not in _DIRECTIONAL_STOP and len(t) >= 2]
    years = _YEAR_RE.findall(clean)

    # 1. Neutral query: concise entities + core subject terms (no stance terms)
    neutral_parts: List[str] = []
    seen_n: Set[str] = set()
    for ent in entities:
        for part in ent.split():
            if part.lower() not in seen_n and part.lower() not in _DIRECTIONAL_STOP:
                seen_n.add(part.lower())
                neutral_parts.append(part)
    for tok in content_tokens:
        if len(neutral_parts) >= 6:
            break
        if tok.lower() not in seen_n and not _YEAR_RE.match(tok):
            seen_n.add(tok.lower())
            neutral_parts.append(tok)
    neutral_query = " ".join(neutral_parts[:6]).strip() or clean[:120]

    # 2. Support-oriented query: full claim assertion (preserving numbers, dates, predicate)
    support_query = clean[:220]

    # 3. Contradiction-oriented query: challenge/correction/alternative-outcome formulation
    subject_prefix = " ".join(neutral_parts[:4]) if neutral_parts else clean[:80]
    low = clean.lower()

    # Strip potentially false specific year / broadcaster / negation from core assertion
    # so retrieval can surface actual alternative dates, channels, or officeholders
    if claim_asserts_current_state(clean):
        role_hits = [
            w for w in content_tokens
            if w.lower() in {"president", "prime", "minister", "ceo", "chancellor", "king", "queen", "currency", "shuttle", "company", "parent"}
        ]
        role_str = " ".join(role_hits[:2])
        contradiction_query = f"{subject_prefix} {role_str} former ended retired replaced successor".strip()
    elif any(net in low for net in BROADCASTER_NETWORKS):
        non_net_tokens = [t for t in content_tokens if t.lower() not in BROADCASTER_NETWORKS]
        contradiction_query = f"{' '.join(non_net_tokens[:5])} network broadcast aired original".strip()
    elif years:
        non_year_tokens = [t for t in content_tokens if t not in years]
        contradiction_query = f"{' '.join(non_year_tokens[:5])} concluded ended date revision false".strip()
    elif any(neg in low.split() for neg in ("not", "never", "no")):
        aff_tokens = [t for t in content_tokens if t.lower() not in {"not", "never", "no"}]
        contradiction_query = " ".join(aff_tokens[:6]).strip()
    else:
        contradiction_query = f"{subject_prefix} false denied debunked correction".strip()

    contradiction_query = re.sub(r"\s+", " ", contradiction_query).strip()
    fc_support = clean[:280]
    fc_contra_core = " ".join(neutral_parts[:5]).strip() or clean[:120]
    if contradiction_query.lower() != fc_support.lower() and contradiction_query.lower() != neutral_query.lower():
        fc_contradict = f"{fc_contra_core} false fact check" if len(fc_contra_core.split()) <= 3 else fc_contra_core
    else:
        fc_contradict = fc_contra_core

    return DirectionalQueries(
        neutral_query=neutral_query,
        support_query=support_query,
        contradiction_query=contradiction_query,
        factcheck_support_query=fc_support,
        factcheck_contradict_query=fc_contradict[:280],
        gdelt_neutral_query=neutral_query[:120],
    )


@dataclass
class EvidenceQualityAssessment:
    """Multi-dimensional assessment for a single candidate evidence item."""
    source_type: str
    source_name: str
    title_or_page: str
    text_excerpt: str
    url: Optional[str]
    publication_date: Optional[str]
    retrieved_at: str
    retrieval_direction: str  # support_oriented, contradiction_oriented, neutral
    stance: str  # supporting, contradicting, neutral
    is_relevant: bool
    rejection_reason: Optional[str]
    relevance_score: float
    subject_entity_alignment: float
    predicate_alignment: float
    temporal_relevance: float
    temporal_status: str
    geographic_relevance: float
    geographic_status: str
    source_reliability_tier: str
    provenance_weight: float
    evidence_specificity: float
    independent_group_key: str
    contradiction_strength: float
    source_freshness: str
    overall_quality_score: float
    alignment_notes: str
    evidence_tier: str = TIER_3_SECONDARY_OR_METADATA
    is_official_primary: bool = False
    is_secondary_encyclopedic: bool = False
    meets_single_source_criteria: bool = False
    ml_nli_confidence: float = 0.0
    ml_nli_label: str = "NOT ENOUGH INFO"
    ml_nli_probabilities: Dict[str, float] = field(default_factory=dict)
    symbolic_alignment: Optional[AlignedEvidenceAssessment] = None
    is_stale: bool = False


def _assess_geographic_relevance(claim: str, evidence_text: str) -> Tuple[float, str]:
    c_words = set(re.findall(r"[a-z]+", claim.lower()))
    e_words = set(re.findall(r"[a-z]+", evidence_text.lower()))
    c_geos = c_words.intersection(_GEO_LOCATION_TOKENS)
    if not c_geos:
        return 1.0, "not_applicable"
    e_geos = e_words.intersection(_GEO_LOCATION_TOKENS)
    if c_geos.intersection(e_geos):
        return 1.0, "aligned"
    # Check conflicting mutually exclusive location groups (countries, cities, continents)
    for grp in (MUTUALLY_EXCLUSIVE_GROUPS[1], MUTUALLY_EXCLUSIVE_GROUPS[2], MUTUALLY_EXCLUSIVE_GROUPS[7]):
        c_hit = c_geos.intersection(grp)
        e_hit = e_geos.intersection(grp)
        if c_hit and e_hit and not c_hit.intersection(e_hit):
            return 0.25, f"mismatch({','.join(sorted(c_hit))} vs {','.join(sorted(e_hit))})"
    return 0.65, "partial_or_implicit"


def _compute_specificity(text: str, source_type: str) -> float:
    clean = (text or "").strip()
    if not clean:
        return 0.0
    words = clean.split()
    has_num_or_year = bool(re.search(r"\d+", clean))
    has_proper = len(re.findall(r"\b[A-Z][a-z]{2,}\b", clean)) >= 2
    if source_type in ("gdelt", "rss"):
        # Headlines alone lack body evidence & verification depth
        return round(min(0.45, 0.25 + (0.08 if has_num_or_year else 0.0) + (0.08 if has_proper else 0.0)), 2)
    if len(words) < 6:
        return 0.35
    score = 0.50
    if len(words) >= 12:
        score += 0.15
    if has_num_or_year:
        score += 0.15
    if has_proper:
        score += 0.10
    if source_type == "google_fact_check":
        score = min(score, 0.78)
    return round(min(1.0, score), 2)


def _freshness_label(source_type: str, pub_date: Optional[str], is_stale: bool = False) -> Tuple[str, float]:
    if is_stale:
        return "stale", 0.30
    if source_type == "wikipedia_live":
        return "live_wiki_revision", 0.92
    if source_type == "fever_local":
        return "snapshot_2017_06", 0.55
    if source_type == "gdelt":
        return "recent_news_window", 0.80
    if source_type == "google_fact_check":
        if pub_date and re.search(r"\b202[3-9]\b", str(pub_date)):
            return "recent_fact_check", 0.85
        if pub_date:
            return "dated_fact_check", 0.60
        return "undated_fact_check", 0.45
    return "unknown", 0.50


def _has_explicit_directional_orbital_conflict(
    claim: str,
    ve: VerifiedEvidence,
    sym: AlignedEvidenceAssessment,
) -> bool:
    """
    Confirms an explicit, validated subject-object directional reversal conflict
    using both alignment metadata and extracted directed orbital relations.
    """
    if sym.calibrated_nli != "REFUTES" or sym.evidence_role != "contradicting":
        return False
    if not sym.has_exclusive_slot_conflict or sym.missing_primary_entity or not sym.entity_matched:
        return False
    reason_low = (sym.alignment_reason or "").lower()
    if "orbital" not in reason_low or "revers" not in reason_low:
        return False

    claim_rels = extract_orbital_relations(claim)
    if not claim_rels:
        return False
    ev_rels = extract_orbital_relations(ve.text or "", page_hint=ve.page or "")
    if not ev_rels:
        return False

    reversed_hit = any((c_obj, c_subj) in ev_rels for c_subj, c_obj in claim_rels)
    same_dir_hit = any((c_subj, c_obj) in ev_rels for c_subj, c_obj in claim_rels)
    return reversed_hit and not same_dir_hit


def _compute_documentary_contradiction_strength(
    claim: str,
    ve: VerifiedEvidence,
    sym: AlignedEvidenceAssessment,
    *,
    is_relevant: bool,
    subj_align: float,
    pred_align: float,
    specificity: float,
    geo_status: str,
) -> float:
    """
    Computes contradiction strength from the final calibrated label and validated
    alignment metadata without overwriting raw NLI probabilities or treating every
    alignment override as automatically strong.
    """
    sim = float(ve.retrieval_similarity)
    if not is_relevant or sym.calibrated_nli != "REFUTES" or sim < 0.48:
        return 0.0

    r_prob = float((ve.nli_probabilities or {}).get("refutes", ve.nli_confidence))
    has_sym_conflict = (
        sym.has_exclusive_slot_conflict
        or sym.has_numeric_conflict
        or sym.has_negation_conflict
    )
    conflict_boost = 0.15 if has_sym_conflict else 0.0
    raw_based_strength = round(min(1.0, 0.45 * sim + 0.45 * r_prob + conflict_boost), 2)

    valid_entity = sym.entity_matched and not sym.missing_primary_entity and subj_align >= 0.65
    strong_relevance = (
        sim >= 0.50
        and pred_align >= 0.50
        and sym.overlap_ratio >= 0.45
        and specificity >= 0.48
        and not geo_status.startswith("mismatch")
    )
    if valid_entity and strong_relevance and _has_explicit_directional_orbital_conflict(claim, ve, sym):
        # Capped at 0.64 (< 0.65) so an override lacking raw NLI REFUTES still requires
        # independent multi-source corroboration instead of single-source Tier 2 shortcut.
        aligned_directional_strength = round(
            min(0.64, 0.32 * sim + 0.14 * subj_align + 0.14 * pred_align + 0.10 * sym.overlap_ratio),
            2,
        )
        return max(raw_based_strength, aligned_directional_strength)

    return raw_based_strength


def evaluate_documentary_evidence(
    claim: str,
    ve: VerifiedEvidence,
    *,
    retrieval_direction: str = "neutral",
    retrieved_at: Optional[str] = None,
) -> EvidenceQualityAssessment:
    """Evaluates a FEVER/Wikipedia VerifiedEvidence sentence across all quality dimensions."""
    now_iso = retrieved_at or datetime.now(timezone.utc).isoformat()
    sym = evaluate_evidence_alignment(claim, ve)
    # Sync calibrated status back onto VerifiedEvidence for backward API compatibility
    ve.nli_label = sym.calibrated_nli
    ve.evidence_role = sym.evidence_role
    ve.alignment_notes = sym.alignment_reason

    c_toks = normalize_content_tokens(claim, stem=True)
    e_toks = normalize_content_tokens(ve.text, stem=True)
    c_ents = {w.lower() for e in extract_subject_entities(claim) for w in e.split() if len(w) >= 3}
    haystack = f"{ve.page} {ve.text}".lower()

    if sym.missing_primary_entity or not sym.entity_matched:
        subj_align = 0.15
    elif c_ents:
        matched_cnt = sum(1 for ent in c_ents if ent in haystack)
        subj_align = round(min(1.0, max(0.65, matched_cnt / max(1, len(c_ents)))), 2)
    else:
        subj_align = 0.78

    if c_toks:
        overlap_ratio = len(c_toks.intersection(e_toks)) / max(1, len(c_toks))
    else:
        overlap_ratio = 0.0

    if sym.has_negation_conflict or sym.has_exclusive_slot_conflict or sym.has_numeric_conflict:
        pred_align = round(max(0.75, min(1.0, overlap_ratio + 0.40)), 2)
    elif sym.calibrated_nli == "SUPPORTS":
        pred_align = round(max(0.60, min(1.0, overlap_ratio + 0.35)), 2)
    elif sym.calibrated_nli == "REFUTES":
        pred_align = round(max(0.60, min(1.0, overlap_ratio + 0.30)), 2)
    else:
        pred_align = round(min(0.55, overlap_ratio), 2)

    is_current_claim = claim_asserts_current_state(claim)
    if sym.shows_historical_end and is_current_claim:
        temp_rel, temp_status = 0.90, "historical_end_detected"
    elif ve.source_type == "fever_local" and is_current_claim:
        temp_rel, temp_status = 0.35, "stale_2017_snapshot_for_current_claim"
    else:
        temp_rel, temp_status = 0.88, "temporally_aligned"

    geo_rel, geo_status = _assess_geographic_relevance(claim, f"{ve.page} {ve.text}")
    tier_name, evidence_tier, prov_weight = SOURCE_RELIABILITY_TIERS.get(
        ve.source_type, ("unclassified_secondary", TIER_3_SECONDARY_OR_METADATA, 0.40)
    )
    specificity = _compute_specificity(ve.text, ve.source_type)
    fresh_label, fresh_score = _freshness_label(ve.source_type, ve.publication_date)

    # Rejection checks
    is_relevant = True
    rejection_reason = None
    if sym.missing_primary_entity or not sym.entity_matched:
        is_relevant = False
        rejection_reason = "primary_subject_entity_mismatch"
    elif ve.retrieval_similarity < 0.40:
        is_relevant = False
        rejection_reason = f"low_semantic_similarity({ve.retrieval_similarity:.2f})"
    elif geo_status.startswith("mismatch") and sym.calibrated_nli == "SUPPORTS":
        # Geographic mismatch prevents support transfer across distinct regions/countries
        is_relevant = False
        rejection_reason = f"geographic_{geo_status}"

    # Stance & contradiction strength
    if not is_relevant:
        stance = "neutral"
        contradiction_strength = 0.0
    elif sym.calibrated_nli == "SUPPORTS" and ve.retrieval_similarity >= 0.48:
        stance = "supporting"
        contradiction_strength = 0.0
    elif sym.calibrated_nli == "REFUTES" and ve.retrieval_similarity >= 0.48:
        stance = "contradicting"
        contradiction_strength = _compute_documentary_contradiction_strength(
            claim,
            ve,
            sym,
            is_relevant=is_relevant,
            subj_align=subj_align,
            pred_align=pred_align,
            specificity=specificity,
            geo_status=geo_status,
        )
    else:
        stance = "neutral"
        contradiction_strength = 0.0

    is_official_primary = evidence_tier == TIER_1_PRIMARY_OFFICIAL
    is_secondary_encyclopedic = evidence_tier == TIER_2_SECONDARY_ENCYCLOPEDIC
    tier_cap = 1.00 if is_official_primary else (0.86 if ve.source_type == "wikipedia_live" else (0.82 if ve.source_type == "fever_local" else 0.72))

    # Overall quality (kept completely separate from DeBERTa/classifier softmax)
    overall_q = round(
        max(
            0.0,
            min(
                tier_cap,
                0.28 * subj_align
                + 0.22 * pred_align
                + 0.15 * temp_rel
                + 0.15 * prov_weight
                + 0.10 * specificity
                + 0.10 * min(geo_rel, fresh_score),
            ),
        ),
        2,
    )
    if not is_relevant:
        overall_q = round(min(0.29, overall_q), 2)

    is_stale = temp_status == "stale_2017_snapshot_for_current_claim"
    # Strictly only Tier 1 official first-party records can satisfy single-source primary certification
    meets_single = bool(
        is_official_primary
        and is_relevant
        and not is_stale
        and float(ve.retrieval_similarity) >= 0.55
        and subj_align >= 0.70
        and pred_align >= 0.65
        and temp_rel >= 0.75
        and specificity >= 0.58
    )

    page_norm = re.sub(r"\W+", "", (ve.page or "").lower())
    if is_official_primary:
        group_key = f"official:{page_norm or ve.doc_id}"
    elif ve.source_type in ("wikipedia_live", "fever_local"):
        # Deduplicate multiple passages or FEVER/live-Wikipedia mirrors of the same underlying page
        group_key = f"wiki_page:{page_norm or ve.doc_id}"
    else:
        group_key = f"{ve.source_type}:{page_norm or ve.doc_id}"

    src_name = (
        "Official Institutional Record"
        if is_official_primary
        else ("Wikipedia Live API (Tier 2 Secondary)" if ve.source_type == "wikipedia_live" else "Local FEVER Corpus (Tier 2 Snapshot)")
    )

    return EvidenceQualityAssessment(
        source_type=ve.source_type,
        source_name=src_name,
        title_or_page=ve.page,
        text_excerpt=ve.text[:320],
        url=ve.source_url,
        publication_date=ve.publication_date,
        retrieved_at=now_iso,
        retrieval_direction=retrieval_direction,
        stance=stance,
        is_relevant=is_relevant,
        rejection_reason=rejection_reason,
        relevance_score=round(float(ve.retrieval_similarity), 4),
        subject_entity_alignment=subj_align,
        predicate_alignment=pred_align,
        temporal_relevance=temp_rel,
        temporal_status=temp_status,
        geographic_relevance=geo_rel,
        geographic_status=geo_status,
        source_reliability_tier=tier_name,
        provenance_weight=prov_weight,
        evidence_specificity=specificity,
        independent_group_key=group_key,
        contradiction_strength=contradiction_strength,
        source_freshness=fresh_label,
        overall_quality_score=overall_q,
        alignment_notes=sym.alignment_reason,
        evidence_tier=evidence_tier,
        is_official_primary=is_official_primary,
        is_secondary_encyclopedic=is_secondary_encyclopedic,
        meets_single_source_criteria=meets_single,
        ml_nli_confidence=round(float(ve.nli_confidence), 4),
        ml_nli_label=sym.calibrated_nli,
        ml_nli_probabilities={k: round(float(v), 4) for k, v in (ve.nli_probabilities or {}).items()},
        symbolic_alignment=sym,
        is_stale=is_stale,
    )


def _rating_stance_for_fact_check(rating_text: Optional[str]) -> str:
    if not rating_text:
        return "neutral"
    low = rating_text.strip().lower()
    if any(w in low for w in ("pants on fire", "pants-fire", "false", "fake", "fabricated", "hoax", "altered", "incorrect", "misleading", "distorted")):
        return "contradicting"
    if any(w in low for w in ("true", "correct", "accurate", "verified")) and not any(w in low for w in ("mostly false", "half", "partly", "not true")):
        return "supporting"
    return "neutral"


def evaluate_fact_check_quality(claim: str, match: Any, *, retrieval_direction: str = "neutral") -> EvidenceQualityAssessment:
    """Evaluates a Google Fact Check ClaimReview match across all dimensions (third-party assessment only)."""
    claim_toks = normalize_content_tokens(claim, stem=True)
    review_text = f"{match.claim_text or ''} {match.review_title or ''}".strip()
    rev_toks = normalize_content_tokens(review_text, stem=True)

    c_ents = {w.lower() for e in extract_subject_entities(claim) for w in e.split() if len(w) >= 3}
    hay = review_text.lower()
    if c_ents:
        subj_align = round(sum(1 for e in c_ents if e in hay) / max(1, len(c_ents)), 2)
    else:
        subj_align = round(len(claim_toks.intersection(rev_toks)) / max(1, len(claim_toks)), 2)

    pred_align = round(len(claim_toks.intersection(rev_toks)) / max(1, len(claim_toks)), 2)
    is_relevant = subj_align >= 0.40 and pred_align >= 0.25
    rejection_reason = None if is_relevant else "low_claim_overlap_with_fact_check_review"

    temp_rel = 0.35 if match.is_stale else 0.80
    temp_status = "stale_review" if match.is_stale else "review_dated"
    geo_rel, geo_status = _assess_geographic_relevance(claim, review_text)
    tier_name, fc_tier, prov_weight = SOURCE_RELIABILITY_TIERS["google_fact_check"]
    specificity = _compute_specificity(review_text, "google_fact_check")
    fresh_label, fresh_score = _freshness_label("google_fact_check", match.review_publication_date, is_stale=match.is_stale)

    stance = _rating_stance_for_fact_check(match.rating_text) if is_relevant else "neutral"
    contradiction_strength = 0.65 if stance == "contradicting" and not match.is_stale else (0.35 if stance == "contradicting" else 0.0)

    overall_q = round(
        min(
            0.74,  # Single third-party ClaimReview never equals primary verification truth alone
            0.28 * subj_align + 0.22 * pred_align + 0.15 * temp_rel + 0.15 * prov_weight + 0.10 * specificity + 0.10 * min(geo_rel, fresh_score),
        ),
        2,
    )
    if not is_relevant:
        overall_q = round(min(0.25, overall_q), 2)

    pub_key = re.sub(r"\W+", "", (match.publisher_name or match.publisher_site or "fc").lower())
    return EvidenceQualityAssessment(
        source_type="google_fact_check",
        source_name=match.publisher_name or match.publisher_site or "Google Fact Check Publisher",
        title_or_page=match.review_title or "Fact-Check ClaimReview",
        text_excerpt=f"Rating: '{match.rating_text or 'Not specified'}' | Reviewed claim: {(match.claim_text or '')[:200]}",
        url=match.review_url,
        publication_date=match.review_publication_date,
        retrieved_at=match.retrieved_at,
        retrieval_direction=retrieval_direction,
        stance=stance,
        is_relevant=is_relevant,
        rejection_reason=rejection_reason,
        relevance_score=round(0.5 * subj_align + 0.5 * pred_align, 4),
        subject_entity_alignment=subj_align,
        predicate_alignment=pred_align,
        temporal_relevance=temp_rel,
        temporal_status=temp_status,
        geographic_relevance=geo_rel,
        geographic_status=geo_status,
        source_reliability_tier=tier_name,
        provenance_weight=prov_weight,
        evidence_specificity=specificity,
        independent_group_key=f"fc:{pub_key}",
        contradiction_strength=contradiction_strength,
        source_freshness=fresh_label,
        overall_quality_score=overall_q,
        alignment_notes=match.stale_reason or f"Third-party ClaimReview rating '{match.rating_text}' (Tier 3 unless independently corroborated).",
        evidence_tier=fc_tier,
        is_official_primary=False,
        is_secondary_encyclopedic=False,
        meets_single_source_criteria=False,
        is_stale=bool(match.is_stale),
    )


_NEWS_DENY_RE = re.compile(r"\b(denies?|denied|refutes?|false|hoax|debunked|fake|no evidence|rumou?r|retracted|cancelled|canceled)\b", re.IGNORECASE)
_NEWS_AFFIRM_RE = re.compile(r"\b(confirms?|confirmed|verified|signed|enacted|approved|launched|wins?|won|completed)\b", re.IGNORECASE)


def evaluate_gdelt_article_quality(claim: str, article: Any, *, retrieval_direction: str = "neutral") -> EvidenceQualityAssessment:
    """
    Evaluates a GDELT DOC 2.0 article headline item strictly as coverage discovery metadata
    (never proof of truth, with syndicated copies collapsed).
    """
    claim_toks = normalize_content_tokens(claim, stem=True)
    title_toks = normalize_content_tokens(article.title or "", stem=True)
    c_ents = {w.lower() for e in extract_subject_entities(claim) for w in e.split() if len(w) >= 3}
    hay = (article.title or "").lower()

    if c_ents:
        subj_align = round(sum(1 for e in c_ents if e in hay) / max(1, len(c_ents)), 2)
    else:
        subj_align = round(len(claim_toks.intersection(title_toks)) / max(1, len(claim_toks)), 2)

    pred_align = round(len(claim_toks.intersection(title_toks)) / max(1, len(claim_toks)), 2)
    is_relevant = subj_align >= 0.45 and pred_align >= 0.20
    rejection_reason = None if is_relevant else "headline_off_subject_or_low_overlap"

    geo_rel, geo_status = _assess_geographic_relevance(claim, article.title or "")
    tier_name, gd_tier, prov_weight = SOURCE_RELIABILITY_TIERS["gdelt"]
    specificity = _compute_specificity(article.title or "", "gdelt")
    fresh_label, fresh_score = _freshness_label("gdelt", article.published_at)

    stance = "neutral"
    c_strength = 0.0
    if is_relevant:
        has_den = bool(_NEWS_DENY_RE.search(article.title or ""))
        has_aff = bool(_NEWS_AFFIRM_RE.search(article.title or ""))
        if has_den and not has_aff:
            stance = "contradicting"
            c_strength = 0.25  # Headline framing alone cannot refute strongly
        elif has_aff and not has_den:
            stance = "supporting"

    # Cap overall GDELT metadata quality below Tier 1/2 evidence thresholds
    overall_q = round(
        min(
            0.45,
            0.25 * subj_align + 0.20 * pred_align + 0.15 * prov_weight + 0.15 * specificity + 0.15 * fresh_score + 0.10 * geo_rel,
        ),
        2,
    )
    if not is_relevant:
        overall_q = round(min(0.20, overall_q), 2)

    title_sig = re.sub(r"\W+", "", (article.title or "").lower())[:70]
    synd_note = (
        f"Syndicated copies collapsed ({article.syndicated_count} copies treated as 1 independent report)."
        if getattr(article, "syndicated_count", 1) > 1
        else "GDELT coverage headline metadata (Tier 3 only, not factual proof)."
    )

    return EvidenceQualityAssessment(
        source_type="gdelt",
        source_name=article.domain or "GDELT Coverage",
        title_or_page=article.title,
        text_excerpt=f"[{article.domain}] {article.title}",
        url=article.url,
        publication_date=article.published_at,
        retrieved_at=article.retrieved_at,
        retrieval_direction=retrieval_direction,
        stance=stance,
        is_relevant=is_relevant,
        rejection_reason=rejection_reason,
        relevance_score=round(0.5 * subj_align + 0.5 * pred_align, 4),
        subject_entity_alignment=subj_align,
        predicate_alignment=pred_align,
        temporal_relevance=0.80,
        temporal_status=f"gdelt_window:{article.search_window}",
        geographic_relevance=geo_rel,
        geographic_status=geo_status,
        source_reliability_tier=tier_name,
        provenance_weight=prov_weight,
        evidence_specificity=specificity,
        independent_group_key=f"gdelt:{title_sig}",
        contradiction_strength=c_strength,
        source_freshness=fresh_label,
        overall_quality_score=overall_q,
        alignment_notes=synd_note,
        evidence_tier=gd_tier,
        is_official_primary=False,
        is_secondary_encyclopedic=False,
        meets_single_source_criteria=False,
        is_stale=False,
    )
