"""
backend/app/schemas/article.py
Pydantic schemas for full article fact verification, claim extraction, and classifier signals.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import uuid
from pydantic import BaseModel, Field, field_validator

from backend.app.schemas.verification import (
    VerdictEnum,
    EvidenceSentenceSchema,
    EvidenceAuditTrailSchema,
    FactCheckMatchSchema,
    NewsEvidenceSchema,
    ExternalSourceStatusSchema,
)


class ArticleClassifierSignal(BaseModel):
    model: str = "google-bert/bert-base-uncased (ISOT)"
    prediction: str = Field(..., description="Binary article pattern: FAKE or REAL")
    confidence: float = Field(..., description="Softmax confidence score")
    probabilities: Dict[str, float]
    distribution_shift_warning: str


class LIARClassifierSignal(BaseModel):
    model: str = "bert-base-uncased (LIAR)"
    prediction: str = Field(..., description="6-class LIAR grade (pants-fire to true)")
    confidence: float
    probabilities: Dict[str, float]
    disclaimer: str


class ExtractedClaimVerification(BaseModel):
    claim: str
    relevance_rank: int
    verdict: VerdictEnum
    confidence_score: float
    explanation: str
    uncertainty_explanation: str = ""
    evidence: List[EvidenceSentenceSchema] = Field(default_factory=list)
    liar_signal: Optional[LIARClassifierSignal] = None
    evidence_audit_trail: Optional[EvidenceAuditTrailSchema] = None


class ArticleVerificationRequest(BaseModel):
    title: Optional[str] = Field(default=None, max_length=300, description="Article title / headline")
    text: str = Field(..., min_length=20, max_length=50000, description="Full article text body")
    max_claims: int = Field(default=3, ge=1, le=5, description="Number of claims to extract and verify (1 to 5)")
    source_url: Optional[str] = Field(default=None, description="Optional article source link")

    @field_validator("text")
    @classmethod
    def clean_text_body(cls, v: str) -> str:
        cleaned = v.strip()
        if len(cleaned) < 20:
            raise ValueError("Article text body must contain at least 20 non-whitespace characters.")
        return cleaned


class ArticleVerificationResponse(BaseModel):
    article_id: str = Field(default_factory=lambda: f"art-{uuid.uuid4().hex[:12]}")
    title: Optional[str] = None
    overall_verdict: VerdictEnum
    overall_confidence: float
    summary_explanation: str
    uncertainty_explanation: str = ""
    article_classifier: ArticleClassifierSignal
    claims_analyzed: int
    extracted_claims: List[ExtractedClaimVerification] = Field(default_factory=list)
    fact_check_matches: List[FactCheckMatchSchema] = Field(default_factory=list, description="Supplementary third-party ClaimReview matches")
    news_evidence: List[NewsEvidenceSchema] = Field(default_factory=list, description="Supplementary GDELT global news coverage metadata")
    external_source_status: Optional[ExternalSourceStatusSchema] = Field(default=None, description="Provider availability, conflicts, staleness, and shared quota state")
    evidence_audit_trail: Optional[EvidenceAuditTrailSchema] = Field(default=None, description="Prediction-independent article-level IEVE second-pass audit trail")
    limitations: List[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    blockchain_hash: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Deterministic cryptographic canonical verification record and SHA-256 hash"
    )
