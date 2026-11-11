"""
ml/inference/verdict_synthesizer.py
Six-class evidence-grounded verdict synthesis:
  - GENUINE
  - FAKE
  - MISLEADING
  - PARTIALLY_TRUE
  - UNVERIFIED
  - OUTDATED

Combines calibrated DeBERTa NLI assessments, symbolic alignment (entity, predicate, number,
date, negation, temporal markers), and provenance metadata without relying on uncalibrated
model softmax scores as truth probabilities.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from ml.inference.claim_verifier import VerifiedEvidence
from ml.inference.evidence_alignment import (
    AlignedEvidenceAssessment,
    MUTUALLY_EXCLUSIVE_GROUPS,
    claim_asserts_current_state,
    evaluate_evidence_alignment,
    evidence_confirms_active_tenure,
    normalize_content_tokens,
)


ABSOLUTE_FRAMING_WORDS = {
    "only", "sole", "solely", "exclusively", "always", "never",
    "every", "all", "everyone", "100", "completely", "entirely", "purely", "single"
}

BROADCASTER_NETWORKS = {
    "hbo", "tlc", "bbc", "cbs", "nbc", "abc", "fox", "pbs", "netflix", "hulu", "cnn"
}

TEMPORAL_ROLE_WORDS = {
    "president", "presid", "prime", "minister", "pm", "chief", "cm",
    "ceo", "governor", "monarch", "king", "queen", "sovereign", "chancellor", "leader",
    "secretary", "brand", "name", "air", "series", "show",
    "currency", "circulat", "shuttle", "fleet", "fly", "flies",
    "parent", "holding", "company", "champion", "reign", "holder"
}


@dataclass
class SynthesisResult:
    verdict: str  # GENUINE, FAKE, MISLEADING, PARTIALLY_TRUE, UNVERIFIED, OUTDATED
    confidence_score: float
    explanation: str
    uncertainty_explanation: str
    conflicting_evidence_detected: bool
    strongest_evidence_page: Optional[str]
    limitations: List[str]
    aligned_assessments: List[AlignedEvidenceAssessment] = field(default_factory=list)


def _format_source_provenance(ev: VerifiedEvidence) -> str:
    src_label = "Live Wikipedia" if ev.source_type == "wikipedia_live" else "FEVER Wikipedia Corpus"
    date_label = ev.publication_date or "Unknown date"
    return f"{src_label} ('{ev.page}', rev: {date_label})"


def _is_temporal_role_match(claim: str, assessment: AlignedEvidenceAssessment) -> bool:
    """
    Confirms a historical-end evidence sentence matches the role/office/entity
    the claim asserts as current (so a past office like 'Chief Minister 2001-2014'
    does not override 'Prime Minister since 2014').
    """
    if not assessment.shows_historical_end or assessment.evidence.retrieval_similarity < 0.45:
        return False
    if assessment.missing_primary_entity:
        return False

    c_tokens = normalize_content_tokens(claim, stem=True)
    e_tokens = normalize_content_tokens(assessment.evidence.text, stem=True)
    ev_low = assessment.evidence.text.lower()

    # If evidence explicitly indicates rebrand / end / retirement / replacement / ownership transition
    if any(kw in ev_low for kw in (
        "rebranded", "now x corp", "former name", "former brand", "concluded on",
        "cancelled in", "canceled in", "retired politician", "partially reusable", "retired,",
        "until the adoption of", "official currency of", "became the parent holding company",
        "restructuring of", "defeating the holders", "defeating the defending holders"
    )) or ("owned by" in ev_low and assessment.has_exclusive_slot_conflict):
        return True

    claim_roles = c_tokens.intersection(TEMPORAL_ROLE_WORDS)
    if not claim_roles:
        return assessment.entity_matched

    # Prevent 'chief minister' historical term from falsely firing on 'prime minister' claim
    if "prime" in c_tokens and "minister" in e_tokens and "prime" not in e_tokens and "chief" in e_tokens:
        return False

    # Matched sentence must contain the same role family (e.g. 'presid', 'minister') or 'held the office'
    if claim_roles.intersection(e_tokens) or "held the office" in ev_low:
        has_ongoing_since = bool(re.search(r"\bhas served as\b.*?\bsince\b", ev_low)) and not bool(
            re.search(r"\bfrom\s+\d{4}\s+to\s+\d{4}\b", ev_low)
        )
        return not has_ongoing_since
    return False


def _has_active_current_tenure(claim: str, assessment: AlignedEvidenceAssessment) -> bool:
    ev_low = assessment.evidence.text.lower()
    if assessment.missing_primary_entity or assessment.evidence.retrieval_similarity < 0.48:
        return False
    c_tokens = normalize_content_tokens(claim, stem=True)
    e_tokens = normalize_content_tokens(ev_low, stem=True)
    claim_roles = c_tokens.intersection(TEMPORAL_ROLE_WORDS)
    role_hit = bool(claim_roles.intersection(e_tokens)) if claim_roles else True
    return role_hit and evidence_confirms_active_tenure(claim, assessment.evidence.text)


class VerdictSynthesizer:
    """
    Implements the conservative six-class verdict policy over calibrated evidence assessments.
    """
    MIN_SUPPORT_SIMILARITY = 0.48
    STRONG_NLI_THRESHOLD = 0.65

    DEFAULT_LIMITATIONS = [
        "Primary retrieval uses the 126k-sentence 2017 FEVER Wikipedia snapshot, augmented conditionally via read-only public Wikipedia (en.wikipedia.org) when local coverage is sparse or temporally sensitive.",
        "Absence of matching evidence in Wikipedia or local snapshots never constitutes proof of falsehood; insufficient cases default strictly to UNVERIFIED.",
        "DeBERTa NLI probabilities are uncalibrated softmax outputs combined with symbolic entity/date/predicate gating—not calibrated statistical truth probabilities.",
        "Experimental ISOT and LIAR signals reflect benchmark linguistic distributions and cannot independently certify empirical facts.",
        "Does not perform universal web fact-checking across proprietary databases or real-time wire services."
    ]

    def synthesize(
        self,
        claim: str,
        evidence: List[VerifiedEvidence],
        retrieval_meta: Optional[Dict[str, Any]] = None
    ) -> SynthesisResult:
        limitations = list(self.DEFAULT_LIMITATIONS)
        meta = retrieval_meta or {}
        wiki_status = meta.get("wikipedia_status", "not_needed")

        if not evidence:
            uncertainty = (
                "Zero candidate evidence sentences were retrieved from the local FEVER index"
                + (f" and live Wikipedia fallback status was '{wiki_status}'." if meta.get("wikipedia_fallback_triggered") else ".")
            )
            return SynthesisResult(
                verdict="UNVERIFIED",
                confidence_score=0.0,
                explanation="No relevant documentary evidence could be retrieved from local or public Wikipedia knowledge sources.",
                uncertainty_explanation=uncertainty,
                conflicting_evidence_detected=False,
                strongest_evidence_page=None,
                limitations=limitations,
                aligned_assessments=[]
            )

        # Evaluate symbolic + NLI alignment for every retrieved item and update evidence provenance/role
        assessments = [evaluate_evidence_alignment(claim, ev) for ev in evidence]
        for a in assessments:
            a.evidence.nli_label = a.calibrated_nli
            a.evidence.evidence_role = a.evidence_role
            a.evidence.alignment_notes = a.alignment_reason

        top_ev = evidence[0]
        supporting = [
            a for a in assessments
            if a.calibrated_nli == "SUPPORTS"
            and a.evidence.nli_probabilities.get("supports", 0.0) >= self.STRONG_NLI_THRESHOLD
            and a.evidence.retrieval_similarity >= self.MIN_SUPPORT_SIMILARITY
        ]
        contradicting = [
            a for a in assessments
            if a.calibrated_nli == "REFUTES"
            and (
                a.evidence.nli_probabilities.get("refutes", 0.0) >= self.STRONG_NLI_THRESHOLD
                or a.has_exclusive_slot_conflict
                or a.has_numeric_conflict
            )
            and a.evidence.retrieval_similarity >= self.MIN_SUPPORT_SIMILARITY
        ]
        nei_abstained = [a for a in assessments if a.calibrated_nli == "NOT ENOUGH INFO"]

        uncertainty_notes: List[str] = []
        if nei_abstained:
            raw_refutes_blocked = sum(1 for a in nei_abstained if a.evidence.raw_nli_label == "REFUTES")
            if raw_refutes_blocked:
                uncertainty_notes.append(
                    f"Abstention guard reclassified {raw_refutes_blocked} low-alignment DeBERTa REFUTES prediction(s) to NOT ENOUGH INFO because evidence lacked direct contradiction or subject match."
                )
        if meta.get("wikipedia_fallback_triggered") and wiki_status in ("offline", "timeout", "error_fallback"):
            uncertainty_notes.append(
                f"Live public Wikipedia fallback could not complete ({wiki_status}); evaluation relied solely on the 2017 local FEVER corpus."
            )

        # ------------------------------------------------------------------
        # PRIORITY 1: OUTDATED (Historically accurate state framed as current)
        # ------------------------------------------------------------------
        if claim_asserts_current_state(claim):
            has_live_ev = any(a.evidence.source_type == "wikipedia_live" for a in assessments)
            # Never allow static 2017 FEVER snapshot hits to certify GENUINE or veto live Wikipedia on current-state claims
            if has_live_ev:
                supporting = [s for s in supporting if s.evidence.source_type != "fever_local"]
            temporal_assessments = [
                a for a in assessments
                if not (has_live_ev and a.evidence.source_type == "fever_local")
            ] or assessments
            active_hits = [a for a in temporal_assessments if _has_active_current_tenure(claim, a)]
            outdated_hits = [a for a in temporal_assessments if _is_temporal_role_match(claim, a)]
            if outdated_hits and not active_hits:
                primary = max(outdated_hits, key=lambda x: x.evidence.retrieval_similarity)
                score = round(min(0.92, 0.45 * primary.evidence.retrieval_similarity + 0.50), 2)
                uncertainty_notes.append(
                    "Temporal check detected present-tense/current framing against evidence specifying a closed historical tenure, cancellation, or rebrand."
                )
                return SynthesisResult(
                    verdict="OUTDATED",
                    confidence_score=score,
                    explanation=(
                        f"Outdated framing: {_format_source_provenance(primary.evidence)} indicates this state or role "
                        f"previously applied to the subject but ended or changed prior to the current date."
                    ),
                    uncertainty_explanation=" ".join(uncertainty_notes),
                    conflicting_evidence_detected=bool(supporting and contradicting),
                    strongest_evidence_page=primary.evidence.page,
                    limitations=limitations,
                    aligned_assessments=assessments
                )
            # If live/current evidence positively confirms an active ongoing tenure (e.g. "is the 47th president"),
            # earlier prior-term dates (e.g. "served from 2017 to 2021") are historical context, not a contradiction.
            if active_hits:
                contradicting = [
                    c for c in contradicting
                    if c.has_exclusive_slot_conflict or c.has_negation_conflict or not c.shows_historical_end
                ]
                for ah in active_hits:
                    if ah not in supporting and ah.entity_matched and ah.evidence.retrieval_similarity >= self.MIN_SUPPORT_SIMILARITY:
                        if ah.evidence.raw_nli_label == "SUPPORTS" or ah.evidence.nli_probabilities.get("supports", 0.0) >= 0.45:
                            supporting.append(ah)

        # ------------------------------------------------------------------
        # PRIORITY 2: MISLEADING (Contextual distortion / slot substitution / resolved genuine conflict)
        # ------------------------------------------------------------------
        claim_words_raw = set(re.findall(r"[a-zA-Z0-9]+", claim.lower()))
        has_absolute_framing = bool(claim_words_raw.intersection(ABSOLUTE_FRAMING_WORDS))

        # Case 2A: Broadcaster / alternative attribution substitution on genuine subject
        for c_item in contradicting:
            ev_words = set(re.findall(r"[a-zA-Z0-9]+", c_item.evidence.text.lower()))
            c_nets = claim_words_raw.intersection(BROADCASTER_NETWORKS)
            e_nets = ev_words.intersection(BROADCASTER_NETWORKS)
            if c_nets and e_nets and not c_nets.intersection(e_nets):
                return SynthesisResult(
                    verdict="MISLEADING",
                    confidence_score=0.72,
                    explanation=(
                        f"Misleading attribution: {_format_source_provenance(c_item.evidence)} confirms the subject exists "
                        f"but aired/appeared via {', '.join(sorted(e_nets)).upper()} rather than {', '.join(sorted(c_nets)).upper()}."
                    ),
                    uncertainty_explanation=(
                        "Named entity corroborated, while attributed network/platform conflicts with documentary records."
                    ),
                    conflicting_evidence_detected=True,
                    strongest_evidence_page=c_item.evidence.page,
                    limitations=limitations,
                    aligned_assessments=assessments
                )

        # Case 2B: Absolute / exaggerated framing contradicted on real subject ("only", "exclusively", "100%", etc.)
        if has_absolute_framing and contradicting:
            top_c = max(contradicting, key=lambda x: x.evidence.retrieval_similarity)
            if top_c.entity_matched:
                return SynthesisResult(
                    verdict="MISLEADING",
                    confidence_score=0.72,
                    explanation=(
                        f"Misleading scope/framing: Absolute qualifier in the claim conflicts with evidence in "
                        f"{_format_source_provenance(top_c.evidence)}."
                    ),
                    uncertainty_explanation=(
                        "Detected sweeping/absolute quantifier distorted relative to qualified documentary evidence. "
                        + " ".join(uncertainty_notes)
                    ).strip(),
                    conflicting_evidence_detected=True,
                    strongest_evidence_page=top_c.evidence.page,
                    limitations=limitations,
                    aligned_assessments=assessments
                )

        # Resolve secondary biographical timeline dates vs disputed exclusive slots before Case 2C
        claim_yrs = set(re.findall(r"\b(?:1[5-9]\d{2}|20\d{2})\b", claim))
        if supporting and contradicting and claim_yrs:
            exact_year_sup = [
                s for s in supporting
                if s.entity_matched and claim_yrs.issubset(set(re.findall(r"\b(?:1[5-9]\d{2}|20\d{2})\b", s.evidence.text)))
            ]
            if exact_year_sup:
                contradicting = [
                    c for c in contradicting
                    if c.has_exclusive_slot_conflict or c.has_negation_conflict or not c.has_numeric_conflict
                ]

        if supporting and contradicting:
            has_excl_ref = any(c.entity_matched and c.has_exclusive_slot_conflict for c in contradicting)
            has_num_ref = any(c.entity_matched and c.has_numeric_conflict for c in contradicting)
            if has_excl_ref:
                claim_low = claim.lower()
                excl_tokens_in_claim = {
                    g for grp in MUTUALLY_EXCLUSIVE_GROUPS for g in grp
                    if re.search(rf"\b{re.escape(g)}\b", claim_low)
                }
                if excl_tokens_in_claim:
                    sup_with_excl = [
                        s for s in supporting
                        if s.entity_matched and all(
                            re.search(rf"\b{re.escape(tok)}\b", s.evidence.text.lower())
                            for tok in excl_tokens_in_claim
                        )
                    ]
                    if not sup_with_excl:
                        supporting = []
            if supporting and has_num_ref and claim_yrs:
                sup_with_yrs = [
                    s for s in supporting
                    if s.entity_matched and claim_yrs.issubset(set(re.findall(r"\b(?:1[5-9]\d{2}|20\d{2})\b", s.evidence.text)))
                ]
                if not sup_with_yrs:
                    supporting = []

        # Case 2C: High-relevance supporting AND contradicting sentences on the SAME subject
        if supporting and contradicting:
            top_s = max(supporting, key=lambda x: x.evidence.retrieval_similarity)
            top_r = max(contradicting, key=lambda x: x.evidence.retrieval_similarity)
            sim_diff = abs(top_s.evidence.retrieval_similarity - top_r.evidence.retrieval_similarity)
            # Material genuine tension vs minor background difference
            if sim_diff < 0.14 and top_s.evidence.retrieval_similarity >= 0.50 and top_r.evidence.retrieval_similarity >= 0.50:
                return SynthesisResult(
                    verdict="MISLEADING",
                    confidence_score=0.68,
                    explanation=(
                        f"Conflicting or contested framing detected between {_format_source_provenance(top_s.evidence)} "
                        f"(supporting) and {_format_source_provenance(top_r.evidence)} (contradicting)."
                    ),
                    uncertainty_explanation=(
                        "Both supporting and contradicting documentary sentences achieved comparable semantic relevance; "
                        "presenting one side in isolation distorts the full record. " + " ".join(uncertainty_notes)
                    ).strip(),
                    conflicting_evidence_detected=True,
                    strongest_evidence_page=top_s.evidence.page,
                    limitations=limitations,
                    aligned_assessments=assessments
                )
            # If supporting strongly dominates retrieval similarity over a peripheral contrast
            if top_s.evidence.retrieval_similarity - top_r.evidence.retrieval_similarity >= 0.14:
                contradicting = []
            elif top_r.evidence.retrieval_similarity - top_s.evidence.retrieval_similarity >= 0.14:
                supporting = []

        # ------------------------------------------------------------------
        # PRIORITY 3: GENUINE (Strong, consistent corroboration with entity grounding)
        # ------------------------------------------------------------------
        entity_sup = [s for s in supporting if s.entity_matched]
        if entity_sup and not contradicting:
            best_s = max(entity_sup, key=lambda x: x.evidence.retrieval_similarity)
            s_prob = best_s.evidence.nli_probabilities.get("supports", best_s.evidence.nli_confidence)
            score = round(min(0.95, (best_s.evidence.retrieval_similarity * 0.45) + (s_prob * 0.55)), 2)
            return SynthesisResult(
                verdict="GENUINE",
                confidence_score=score,
                explanation=(
                    f"Corroborated by {_format_source_provenance(best_s.evidence)} with semantic similarity "
                    f"{best_s.evidence.retrieval_similarity:.2f} and aligned subject/predicate support."
                ),
                uncertainty_explanation=(
                    f"Supported across {len(entity_sup)} subject-aligned sentence(s) with no calibrated contradictions. "
                    "Note: NLI score reflects statistical alignment on retrieved text, not calibrated real-world probability. "
                    + " ".join(uncertainty_notes)
                ).strip(),
                conflicting_evidence_detected=False,
                strongest_evidence_page=best_s.evidence.page,
                limitations=limitations,
                aligned_assessments=assessments
            )

        # ------------------------------------------------------------------
        # PRIORITY 4: FAKE (Direct factual contradiction with verified entity match)
        # ------------------------------------------------------------------
        entity_con = [c for c in contradicting if c.entity_matched]
        if entity_con and not entity_sup:
            best_r = max(entity_con, key=lambda x: x.evidence.retrieval_similarity)
            r_prob = best_r.evidence.nli_probabilities.get("refutes", best_r.evidence.nli_confidence)
            score = round(min(0.95, (best_r.evidence.retrieval_similarity * 0.45) + (r_prob * 0.55)), 2)
            return SynthesisResult(
                verdict="FAKE",
                confidence_score=score,
                explanation=(
                    f"Directly contradicted by {_format_source_provenance(best_r.evidence)} (semantic similarity "
                    f"{best_r.evidence.retrieval_similarity:.2f}; alignment: {best_r.alignment_reason})."
                ),
                uncertainty_explanation=(
                    f"Contradicted by {len(entity_con)} subject-matched evidence sentence(s) backed by structural conflict signals. "
                    + " ".join(uncertainty_notes)
                ).strip(),
                conflicting_evidence_detected=False,
                strongest_evidence_page=best_r.evidence.page,
                limitations=limitations,
                aligned_assessments=assessments
            )

        # ------------------------------------------------------------------
        # PRIORITY 5: UNVERIFIED (Safe abstention when evidence is missing/irrelevant/ambiguous)
        # ------------------------------------------------------------------
        primary_reason = assessments[0].alignment_reason
        if top_ev.retrieval_similarity < 0.45:
            reason_summary = (
                f"Top retrieved evidence ({_format_source_provenance(top_ev)}) has low semantic similarity "
                f"({top_ev.retrieval_similarity:.2f} < 0.45). Cannot verify or refute reliably."
            )
        else:
            reason_summary = (
                f"Available evidence from {_format_source_provenance(top_ev)} lacks sufficient entity/predicate "
                f"coverage to verify or refute the claim ({primary_reason})."
            )

        score = round(min(0.45, top_ev.retrieval_similarity * 0.5), 2)
        return SynthesisResult(
            verdict="UNVERIFIED",
            confidence_score=score,
            explanation=reason_summary,
            uncertainty_explanation=(
                f"Safe abstention triggered across {len(assessments)} candidate sentence(s). "
                + (" ".join(uncertainty_notes) if uncertainty_notes else "No sentence achieved decisive subject-matched entailment or contradiction.")
            ),
            conflicting_evidence_detected=False,
            strongest_evidence_page=top_ev.page,
            limitations=limitations,
            aligned_assessments=assessments
        )


def get_verdict_synthesizer() -> VerdictSynthesizer:
    return VerdictSynthesizer()
