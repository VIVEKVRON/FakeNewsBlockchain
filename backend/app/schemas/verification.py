"""
backend/app/schemas/verification.py
Pydantic schemas for text verification requests, responses, and evidence structures.
"""

from enum import Enum
from typing import List, Dict, Optional, Any
from datetime import datetime, timezone
import uuid
from pydantic import BaseModel, Field, field_validator


class VerdictEnum(str, Enum):
    GENUINE = "GENUINE"
    FAKE = "FAKE"
    MISLEADING = "MISLEADING"
    PARTIALLY_TRUE = "PARTIALLY_TRUE"
    UNVERIFIED = "UNVERIFIED"
    OUTDATED = "OUTDATED"
    # Legacy aliases retained strictly for reading pre-audit SQLite & Sepolia canonical records
    LIKELY_GENUINE = "LIKELY_GENUINE"
    LIKELY_FAKE = "LIKELY_FAKE"


class NLIProbabilitiesSchema(BaseModel):
    supports: float = Field(..., description="Probability that evidence entails the claim")
    refutes: float = Field(..., description="Probability that evidence contradicts the claim")
    not_enough_info: float = Field(..., description="Probability of insufficient information")


class EvidenceSentenceSchema(BaseModel):
    rank: int = Field(..., description="Retrieval rank (1 = highest relevance)")
    page: str = Field(..., description="Wikipedia page title source")
    sentence_id: int = Field(..., description="Sentence index within the Wikipedia page")
    doc_id: str = Field(..., description="Unique document sentence ID")
    text: str = Field(..., description="Evidence sentence text")
    retrieval_similarity: float = Field(..., description="Cosine similarity score (0.0 to 1.0)")
    nli_label: str = Field(..., description="Calibrated NLI classification: SUPPORTS, REFUTES, or NOT ENOUGH INFO")
    nli_confidence: float = Field(..., description="Uncalibrated DeBERTa softmax score for top raw logit")
    nli_probabilities: NLIProbabilitiesSchema
    source_type: str = Field(default="fever_local", description="Source channel: fever_local or wikipedia_live")
    source_url: Optional[str] = Field(default=None, description="Direct URL to source Wikipedia article")
    publication_date: Optional[str] = Field(default="2017-06 (FEVER Wikipedia Corpus)", description="Source snapshot or revision timestamp")
    evidence_role: str = Field(default="contextual", description="Role after alignment: supporting, contradicting, or contextual")
    alignment_notes: Optional[str] = Field(default=None, description="Explanation of entity, predicate, and temporal alignment")
    retrieval_direction: str = Field(default="neutral", description="Prediction-independent search direction: support_oriented, contradiction_oriented, or neutral")


class ModelSignalSchema(BaseModel):
    model_name: str
    dataset_origin: str
    applicable_input_type: str
    applicable: bool
    prediction: Optional[str] = None
    confidence: Optional[float] = None
    probabilities: Dict[str, float] = Field(default_factory=dict)
    raw_logits: Dict[str, float] = Field(default_factory=dict)
    preliminary_verdict_tag: Optional[str] = None
    disclaimer: str = ""


class InitialMLSignalsSchema(BaseModel):
    liar_signal: ModelSignalSchema
    isot_signal: ModelSignalSchema
    preliminary_verdict: str
    note: str = Field(
        default="LIAR BERT and ISOT BERT are recorded separately as exploratory linguistic signals with no combined confidence score and never restrict retrieval."
    )


class DebertaNLISummarySchema(BaseModel):
    model_name: str
    evaluation_stage: str = "post_retrieval_claim_evidence_pair"
    pairs_evaluated: int = 0
    raw_label_counts: Dict[str, int] = Field(default_factory=dict)
    calibrated_label_counts: Dict[str, int] = Field(default_factory=dict)
    max_raw_probability: float = 0.0
    disclaimer: str = (
        "Evaluates retrieved (claim, evidence) pairs strictly after independent evidence collection; not a text-only initial prediction."
    )


class RetrievalAttemptSchema(BaseModel):
    provider: str
    direction: str
    query: str
    outcome: str
    available: bool
    from_cache: bool = False
    items_retrieved: int = 0
    relevant_items: int = 0
    reason: Optional[str] = None
    claim_text: Optional[str] = None
    claim_id: Optional[str] = None


class AuditSourceItemSchema(BaseModel):
    source_type: str
    source_name: str
    title_or_page: str
    text_excerpt: str
    url: Optional[str] = None
    publication_date: Optional[str] = None
    retrieved_at: str
    retrieval_direction: str
    stance: str
    is_relevant: bool
    rejection_reason: Optional[str] = None
    relevance_score: float
    subject_entity_alignment: float
    predicate_alignment: float
    temporal_relevance: float
    temporal_status: str
    geographic_relevance: float
    geographic_status: str
    source_reliability_tier: str
    evidence_tier: str = "TIER_3_SECONDARY_OR_METADATA"
    meets_single_source_criteria: bool = False
    provenance_weight: float
    evidence_specificity: float
    independent_group_key: str
    contradiction_strength: float
    source_freshness: str
    overall_quality_score: float
    alignment_notes: str
    ml_nli_label: str = "NOT ENOUGH INFO"
    ml_nli_confidence: float = 0.0
    ml_nli_probabilities: Dict[str, float] = Field(default_factory=dict)


class ProviderStatusItemSchema(BaseModel):
    provider: str
    status: str
    available: bool
    items_retrieved: int
    relevant_items: int
    error_or_reason: Optional[str] = None


class EvidenceQualitySummarySchema(BaseModel):
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
    methodology_note: str


class EvidenceAuditTrailSchema(BaseModel):
    initial_ml_signals: InitialMLSignalsSchema
    nli_evaluation: DebertaNLISummarySchema
    directions_executed: List[str] = Field(default_factory=list)
    queries_by_direction: Dict[str, str] = Field(default_factory=dict)
    retrieval_attempts: List[RetrievalAttemptSchema] = Field(default_factory=list)
    gdelt_claim_selections: List[Dict[str, Any]] = Field(default_factory=list)
    supporting_evidence: List[AuditSourceItemSchema] = Field(default_factory=list)
    contradicting_evidence: List[AuditSourceItemSchema] = Field(default_factory=list)
    neutral_evidence: List[AuditSourceItemSchema] = Field(default_factory=list)
    rejected_irrelevant_evidence: List[AuditSourceItemSchema] = Field(default_factory=list)
    conflicts_detected: bool = False
    conflict_details: List[str] = Field(default_factory=list)
    provider_statuses: List[ProviderStatusItemSchema] = Field(default_factory=list)
    unavailable_providers: List[str] = Field(default_factory=list)
    evidence_quality_summary: EvidenceQualitySummarySchema
    second_pass_decision: str
    verdict_changed_from_initial: bool
    verdict_change_reason: Optional[str] = None
    second_pass_reasoning: str
    final_verdict: str
    final_confidence: float
    total_retrieval_attempts: int = 0
    omitted_retrieval_attempts: int = 0


class SubClaimVerdictSchema(BaseModel):
    claim: str
    verdict: VerdictEnum
    confidence_score: float
    explanation: str
    uncertainty_explanation: Optional[str] = None
    evidence: List[EvidenceSentenceSchema] = Field(default_factory=list)
    evidence_audit_trail: Optional[EvidenceAuditTrailSchema] = None


class FactCheckMatchSchema(BaseModel):
    claim_text: Optional[str] = None
    review_title: Optional[str] = None
    publisher_name: Optional[str] = None
    publisher_site: Optional[str] = None
    reviewer_name: Optional[str] = None
    rating_text: Optional[str] = None
    review_url: Optional[str] = None
    review_publication_date: Optional[str] = None
    claim_appearance_date: Optional[str] = None
    original_claim_author: Optional[str] = None
    language_code: Optional[str] = None
    retrieved_at: str
    is_stale: bool = False
    stale_reason: Optional[str] = None
    is_conflicting: bool = False


class NewsEvidenceSchema(BaseModel):
    title: str
    url: str
    domain: str
    published_at: Optional[str] = None
    language: Optional[str] = None
    source_country: Optional[str] = None
    search_query: str
    search_window: str = "1month"
    retrieved_at: str
    syndicated_count: int = 1


class GdeltUsageStatusSchema(BaseModel):
    enabled: bool
    allowance_limit: int
    requests_used: int
    requests_remaining: int
    warning_threshold: int
    warning_active: bool
    limit_reached: bool
    cache_hits: int
    failed_requests: int
    last_request_at: Optional[str] = None
    last_source: Optional[str] = None
    last_status: Optional[str] = None
    tracker_available: bool
    accounting_rule: str
    google_fact_check_available: Optional[bool] = None


class ExternalSourceStatusSchema(BaseModel):
    google_fact_check_status: str = "not_queried"
    google_fact_check_available: bool = False
    google_fact_check_error: Optional[str] = None
    gdelt_status: str = "not_queried"
    gdelt_error: Optional[str] = None
    has_conflicting_fact_checks: bool = False
    has_stale_fact_checks: bool = False
    gdelt_conflicting_coverage: bool = False
    duplicates_collapsed: int = 0
    gdelt_usage: Optional[GdeltUsageStatusSchema] = None
    supplementary_notes: List[str] = Field(default_factory=list)


class TextVerificationRequest(BaseModel):
    claim: str = Field(
        ...,
        min_length=3,
        max_length=1000,
        description="News statement or factual claim to verify"
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of evidence sentences to retrieve (1 to 20)"
    )

    @field_validator("claim")
    @classmethod
    def clean_claim_text(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Claim cannot be empty or purely whitespace.")
        return cleaned


class TextVerificationResponse(BaseModel):
    verification_id: str = Field(default_factory=lambda: f"verif-{uuid.uuid4().hex[:12]}")
    claim: str
    verdict: VerdictEnum
    confidence_score: float = Field(..., description="Synthesised heuristic alignment score (0.0 to 1.0)")
    explanation: str
    uncertainty_explanation: str = Field(default="", description="Explanation of uncertainty, abstention logic, and corpus scope")
    conflicting_evidence_detected: bool = False
    strongest_evidence_page: Optional[str] = None
    evidence: List[EvidenceSentenceSchema] = Field(default_factory=list)
    claim_verdicts: List[SubClaimVerdictSchema] = Field(default_factory=list, description="Sub-claim assessments for compound inputs")
    fact_check_matches: List[FactCheckMatchSchema] = Field(default_factory=list, description="Supplementary third-party ClaimReview matches")
    news_evidence: List[NewsEvidenceSchema] = Field(default_factory=list, description="Supplementary GDELT global news coverage metadata")
    external_source_status: Optional[ExternalSourceStatusSchema] = Field(default=None, description="Provider availability, conflicts, staleness, and shared quota state")
    evidence_audit_trail: Optional[EvidenceAuditTrailSchema] = Field(default=None, description="Prediction-independent IEVE evidence collection and second-pass audit trail")
    limitations: List[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    blockchain_hash: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Deterministic cryptographic canonical verification record and SHA-256 hash"
    )
