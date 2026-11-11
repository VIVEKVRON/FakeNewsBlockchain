"""
backend/app/schemas/image.py
Pydantic schemas for multimodal image analysis: OCR extraction, ELA tampering indicators,
metadata, and epistemological limitations.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import uuid
from pydantic import BaseModel, Field


class ImageMetadata(BaseModel):
    filename: str
    content_type: str
    format: str
    width: int
    height: int
    aspect_ratio: float
    file_size_bytes: int


class OCRTextBlock(BaseModel):
    text: str
    confidence: float
    box: List[List[int]] = Field(default_factory=list, description="4-point polygon coordinates [[x,y],...]")


class OCRResult(BaseModel):
    has_text: bool
    full_text: str
    word_count: int
    average_confidence: float
    text_blocks: List[OCRTextBlock] = Field(default_factory=list)


class ELAResult(BaseModel):
    mean_error: float
    max_error: int
    std_error: float
    variance_score: float
    quality_tested: int = 90
    potential_compression_anomalies: bool
    anomaly_regions_detected: int = 0
    ela_image_base64: Optional[str] = Field(None, description="Base64 JPEG thumbnail of enhanced ELA error map")


class ImageAnalysisResponse(BaseModel):
    analysis_id: str = Field(default_factory=lambda: f"img-{uuid.uuid4().hex[:12]}")
    verification_id: Optional[str] = None
    record_hash: Optional[str] = None
    verdict: str = Field(default="UNVERIFIED", description="Factual truth verdict: strictly UNVERIFIED for standalone visual forensics")
    factual_verification_status: str = Field(default="UNVERIFIED", description="Standalone OCR and ELA do not establish empirical truth")
    metadata: ImageMetadata
    ocr: OCRResult
    ela: ELAResult
    observations: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
