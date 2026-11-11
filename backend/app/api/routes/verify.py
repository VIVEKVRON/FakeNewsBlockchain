"""
backend/app/api/routes/verify.py
API endpoints for text, claim, and full-article verification.
"""

from fastapi import APIRouter, HTTPException, status
from starlette.concurrency import run_in_threadpool
from backend.app.schemas.verification import (
    TextVerificationRequest,
    TextVerificationResponse
)
from backend.app.schemas.article import (
    ArticleVerificationRequest,
    ArticleVerificationResponse
)
from backend.app.services.verification_service import get_verification_service
from backend.app.utils.logger import logger

router = APIRouter(prefix="/verify", tags=["Verification"])


def _run_verify_text(request: TextVerificationRequest) -> TextVerificationResponse:
    service = get_verification_service()
    return service.verify_text_claim(request)


def _run_verify_article(request: ArticleVerificationRequest) -> ArticleVerificationResponse:
    service = get_verification_service()
    return service.verify_article(request)


@router.post(
    "/text",
    response_model=TextVerificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify an individual claim using FAISS RAG and DeBERTa FEVER",
    description="Retrieves evidence from the FEVER Wikipedia index and predicts entailment (SUPPORTS, REFUTES, NOT ENOUGH INFO) to synthesize a conservative 4-tier truth verdict."
)
async def verify_text(request: TextVerificationRequest) -> TextVerificationResponse:
    try:
        return await run_in_threadpool(_run_verify_text, request)
    except Exception as e:
        logger.error(f"Error during text verification: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Verification engine encountered an internal error: {str(e)}"
        )


@router.post(
    "/article",
    response_model=ArticleVerificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify a complete news article using ISOT, claim extraction, and FEVER RAG",
    description="Evaluates article text with ISOT statistical classifier, extracts salient factual claims, verifies each via the FEVER RAG pipeline, and generates a holistic truth assessment."
)
async def verify_article(request: ArticleVerificationRequest) -> ArticleVerificationResponse:
    try:
        return await run_in_threadpool(_run_verify_article, request)
    except Exception as e:
        logger.error(f"Error during article verification: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Article verification engine encountered an internal error: {str(e)}"
        )
