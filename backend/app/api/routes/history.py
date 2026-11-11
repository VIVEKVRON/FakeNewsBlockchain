"""
backend/app/api/routes/history.py
API endpoints for searching, filtering, and retrieving persistent verification records.
"""

from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from backend.app.database.repository import (
    list_verification_records,
    get_verification_record
)

router = APIRouter(prefix="/history", tags=["Verification History"])


class HistoryListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    records: List[Dict[str, Any]]


@router.get(
    "",
    response_model=HistoryListResponse,
    summary="List verification history with search, filtering, and pagination",
    description="Query persistent verification records from SQLite by content type, verdict, blockchain status, or keyword search."
)
async def get_history(
    content_type: Optional[str] = Query(default=None, description="Filter by 'text', 'article', 'image', or 'all'"),
    verdict: Optional[str] = Query(
        default=None,
        description="Filter by verdict (GENUINE, FAKE, MISLEADING, PARTIALLY_TRUE, UNVERIFIED, OUTDATED; legacy aliases LIKELY_GENUINE, LIKELY_FAKE supported)"
    ),
    blockchain_status: Optional[str] = Query(default=None, description="Filter by status (unanchored, confirmed, failed)"),
    search: Optional[str] = Query(default=None, description="Search term in claim, title, verification ID, or tx hash"),
    limit: int = Query(default=20, ge=1, le=100, description="Items per page"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    sort_by: str = Query(default="created_at", description="Sort column (created_at, confidence_score, block_number)"),
    order: str = Query(default="desc", description="Sort direction ('desc' or 'asc')")
) -> HistoryListResponse:
    records, total = list_verification_records(
        content_type=content_type,
        verdict=verdict,
        blockchain_status=blockchain_status,
        search=search,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        order=order
    )
    return HistoryListResponse(
        total=total,
        limit=limit,
        offset=offset,
        records=records
    )


@router.get(
    "/{verification_id}",
    summary="Get single verification record by unique identifier",
    description="Retrieves complete verification data including evidence, canonical record hash, and blockchain receipt."
)
async def get_record_detail(verification_id: str) -> Dict[str, Any]:
    record = get_verification_record(verification_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Verification record '{verification_id}' not found."
        )
    return record
