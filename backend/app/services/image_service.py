"""
backend/app/services/image_service.py
Service for multimodal image analysis: input validation, ELA execution,
PaddleOCR extraction, and objective observation generation.
"""

import io
import uuid
import json
import hashlib
from datetime import datetime, timezone
from typing import List, Tuple, Optional, Dict, Any
from fastapi import UploadFile, HTTPException, status
from PIL import Image

from backend.app.utils.logger import logger
from backend.app.schemas.image import (
    ImageMetadata,
    OCRResult,
    ELAResult,
    ImageAnalysisResponse,
)
from backend.app.database.repository import save_verification_record
from ml.vision.ela_analyzer import get_ela_analyzer
from ml.vision.ocr_extractor import get_ocr_extractor

# Safe limits to protect 16 GB RAM and CPU
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
MIN_DIMENSION = 32
MAX_DIMENSION = 4096
Image.MAX_IMAGE_PIXELS = 25_000_000  # Decompression bomb safeguard


class ImageService:
    def __init__(self):
        self.ela_analyzer = get_ela_analyzer()
        self.ocr_extractor = get_ocr_extractor()

    async def validate_and_read_image(self, file: UploadFile) -> Tuple[bytes, ImageMetadata]:
        filename = file.filename or "uploaded_image"
        
        # 1. Extension check
        ext = ""
        if "." in filename:
            ext = "." + filename.rsplit(".", 1)[-1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file extension '{ext}'. Allowed extensions: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
            )

        # 2. Content-Type check (allow missing or octet-stream if extension is valid)
        if file.content_type and file.content_type not in ALLOWED_MIME_TYPES and file.content_type != "application/octet-stream":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported MIME type '{file.content_type}'. Allowed: image/jpeg, image/png, image/webp"
            )

        # 3. Read bytes & Size limit
        content = await file.read()
        file_size = len(content)

        if file_size == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty (0 bytes)."
            )

        if file_size > MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"Image file exceeds maximum allowable size of 10 MB (size: {file_size / (1024*1024):.2f} MB)."
            )

        # 4. Integrity and Decompression Bomb verification via Pillow
        try:
            image_stream = io.BytesIO(content)
            with Image.open(image_stream) as img:
                img.verify()
            
            # Reopen to read dimensions safely
            image_stream.seek(0)
            with Image.open(image_stream) as img:
                width, height = img.size
                img_format = (img.format or "JPEG").upper()
        except Image.DecompressionBombError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Image exceeds maximum pixel limits (possible decompression bomb)."
            )
        except Exception as e:
            logger.warning(f"Malformed image rejection: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Malformed or corrupt image file: {str(e)}"
            )

        # 5. Dimension bounds
        if width < MIN_DIMENSION or height < MIN_DIMENSION:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Image dimensions ({width}x{height}) are smaller than minimum allowed ({MIN_DIMENSION}x{MIN_DIMENSION})."
            )

        if width > MAX_DIMENSION or height > MAX_DIMENSION:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Image dimensions ({width}x{height}) exceed maximum allowed ({MAX_DIMENSION}x{MAX_DIMENSION})."
            )

        metadata = ImageMetadata(
            filename=filename,
            content_type=file.content_type or f"image/{img_format.lower()}",
            format=img_format,
            width=width,
            height=height,
            aspect_ratio=round(width / max(1, height), 2),
            file_size_bytes=file_size,
        )

        return content, metadata

    async def analyze_image(self, file: UploadFile) -> ImageAnalysisResponse:
        logger.info(f"Received image analysis request: '{file.filename}'")
        image_bytes, metadata = await self.validate_and_read_image(file)

        # 1. Run Error Level Analysis (ELA)
        ela_metrics = self.ela_analyzer.analyze(image_bytes)

        # 2. Run PaddleOCR text extraction
        ocr_result = self.ocr_extractor.extract(image_bytes)

        # 3. Generate objective, neutral observations
        observations: List[str] = []

        if ocr_result.has_text:
            observations.append(
                f"OCR detected {ocr_result.word_count} words across {len(ocr_result.text_blocks)} text segments "
                f"with an average recognition confidence of {(ocr_result.average_confidence * 100):.1f}%."
            )
        else:
            observations.append("No textual elements or readable typography were detected in the image.")

        if ela_metrics.potential_compression_anomalies:
            observations.append(
                f"Error Level Analysis identified {ela_metrics.anomaly_regions_detected} localized region(s) "
                f"exhibiting statistically elevated compression variance (variance score: {ela_metrics.variance_score}). "
                "This may indicate composited elements, multiple resaves, or high-contrast edges."
            )
        else:
            observations.append(
                f"Error Level Analysis shows uniform compression distribution across the frame "
                f"(mean error: {ela_metrics.mean_error:.2f}, std: {ela_metrics.std_error:.2f})."
            )

        # 4. Mandatory epistemological boundaries
        limitations = [
            "Error Level Analysis (ELA) measures compression artifact discrepancies, NOT definitive proof of image forgery or manipulation.",
            "Re-saving, resizing, or social-media re-encoding generates compression differences on authentic images.",
            "Optical Character Recognition (OCR) extracts text glyphs; recognition confidence reflects character detection quality, NOT factual truth.",
            "Standalone image analysis does not cross-reference external knowledge bases; factual veracity of extracted text remains UNVERIFIED.",
            "This system does not perform synthetic/AI-generated image detection."
        ]

        ela_schema = ELAResult(
            mean_error=ela_metrics.mean_error,
            max_error=ela_metrics.max_error,
            std_error=ela_metrics.std_error,
            variance_score=ela_metrics.variance_score,
            quality_tested=ela_metrics.quality_tested,
            potential_compression_anomalies=ela_metrics.potential_compression_anomalies,
            anomaly_regions_detected=ela_metrics.anomaly_regions_detected,
            ela_image_base64=ela_metrics.ela_image_base64,
        )

        # 5. Cryptographic Canonical Record & Persistent SQLite History
        analysis_id = f"img-{uuid.uuid4().hex[:12]}"
        verification_id = f"verif-{analysis_id}"
        image_content_hash = hashlib.sha256(image_bytes).hexdigest()
        
        # Epistemological Semantics:
        # Standalone image forensics (OCR extraction + ELA artifact checks) does NOT establish
        # empirical truth or evidence-backed falsity. Factual veracity is strictly UNVERIFIED.
        verdict = "UNVERIFIED"
        confidence_score = 0.0  # Factual truth is unverified without external knowledge grounding

        title = f"Image Analysis: {metadata.filename}"
        content_preview = (
            f"OCR: \"{ocr_result.full_text[:150]}...\""
            if ocr_result.has_text
            else f"Visual Forensics: {metadata.format} ({metadata.width}x{metadata.height}, {metadata.file_size_bytes} bytes)"
        )
        original_content = (
            f"Image File: {metadata.filename}\n"
            f"Format: {metadata.format}, Dimensions: {metadata.width}x{metadata.height}, Size: {metadata.file_size_bytes} bytes\n"
            f"OCR Extracted Text:\n{ocr_result.full_text}\n\n"
            f"ELA Forensics: variance={ela_metrics.variance_score}, anomalies={ela_metrics.potential_compression_anomalies}"
        )

        canonical_dict = {
            "confidence_score": confidence_score,
            "evidence_hashes": [
                hashlib.sha256(f"OCR:{ocr_result.full_text}".encode("utf-8")).hexdigest(),
                hashlib.sha256(f"ELA:var={ela_metrics.variance_score}:anom={ela_metrics.potential_compression_anomalies}".encode("utf-8")).hexdigest(),
            ],
            "original_content_hash": image_content_hash,
            "primary_verdict": verdict,
            "schema_version": "1.0",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "verification_id": verification_id,
        }
        canonical_serialized = json.dumps(canonical_dict, sort_keys=True, separators=(",", ":"))
        record_hash = hashlib.sha256(canonical_serialized.encode("utf-8")).hexdigest()

        evidence_data = [
            {
                "type": "OCR Text Extraction",
                "description": "Character detection confidence (NOT factual truth)",
                "text": ocr_result.full_text,
                "ocr_recognition_confidence": round(ocr_result.average_confidence, 4),
                "word_count": ocr_result.word_count,
                "factual_truth_certified": False,
            },
            {
                "type": "Error Level Analysis",
                "description": "Compression artifact discrepancy indicator (NOT proof of manipulation)",
                "variance_score": ela_metrics.variance_score,
                "potential_compression_anomalies": ela_metrics.potential_compression_anomalies,
                "mean_error": ela_metrics.mean_error,
                "manipulation_certified": False,
            }
        ]

        try:
            save_verification_record(
                verification_id=verification_id,
                content_type="image",
                title=title,
                content_preview=content_preview,
                original_content=original_content,
                verdict=verdict,
                confidence_score=confidence_score,
                explanation="Standalone multimodal image analysis completed (OCR + ELA). Factual truth is UNVERIFIED without external knowledge grounding.",
                evidence_data=evidence_data,
                canonical_record_dict=canonical_dict,
                record_hash=record_hash,
                blockchain_anchored=False,
                blockchain_status="unanchored",
            )
            logger.info(f"Persisted image analysis verification record: {verification_id} (hash: {record_hash[:16]}...)")
        except Exception as e:
            logger.error(f"Failed to persist image verification to SQLite: {e}")

        return ImageAnalysisResponse(
            analysis_id=analysis_id,
            verification_id=verification_id,
            record_hash=record_hash,
            verdict=verdict,
            factual_verification_status="UNVERIFIED",
            metadata=metadata,
            ocr=ocr_result,
            ela=ela_schema,
            observations=observations,
            limitations=limitations,
        )


_image_service: Optional[ImageService] = None

def get_image_service() -> ImageService:
    global _image_service
    if _image_service is None:
        _image_service = ImageService()
    return _image_service
