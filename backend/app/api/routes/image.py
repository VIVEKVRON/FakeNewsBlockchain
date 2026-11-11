"""
backend/app/api/routes/image.py
API endpoints for multimodal image analysis: ELA tampering indicators,
PaddleOCR text extraction, and metadata verification.
"""

from fastapi import APIRouter, UploadFile, File, Depends, status
from backend.app.schemas.image import ImageAnalysisResponse
from backend.app.services.image_service import ImageService, get_image_service

router = APIRouter(prefix="/analyze", tags=["Image Analysis"])


@router.post(
    "/image",
    response_model=ImageAnalysisResponse,
    status_code=status.HTTP_200_OK,
    summary="Analyze Image via OCR & Error Level Analysis (ELA)",
    description=(
        "Upload an image (JPG, PNG, WEBP, up to 10 MB) to extract embedded text via PaddleOCR "
        "and compute compression artifact discrepancies using Error Level Analysis (ELA). "
        "Results are objective indicators, NOT proof of image authenticity or AI generation."
    ),
)
async def analyze_image(
    file: UploadFile = File(..., description="Image file to analyze (JPG, PNG, or WEBP, max 10 MB)"),
    image_service: ImageService = Depends(get_image_service),
) -> ImageAnalysisResponse:
    return await image_service.analyze_image(file)
