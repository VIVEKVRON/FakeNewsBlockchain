"""
backend/app/schemas/news.py
Pydantic schemas for live breaking news monitoring, RSS/GDELT ingestion,
canonical deduplication, and SQLite caching.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from backend.app.schemas.verification import VerdictEnum, GdeltUsageStatusSchema


class NewsArticleSchema(BaseModel):
    id: str
    canonical_url: str
    title: str
    description: Optional[str] = None
    content: Optional[str] = None
    publisher: str
    source_type: str = Field(..., description="'rss' or 'gdelt'")
    category: str = "General"
    published_at: Optional[str] = None
    ingested_at: str
    verified_verdict: Optional[VerdictEnum] = None
    verification_summary: Optional[str] = None
    is_new: bool = False


class NewsListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    articles: List[NewsArticleSchema]


class NewsSourceSchema(BaseModel):
    id: str
    name: str
    feed_url: str
    source_type: str
    category: str
    is_active: bool = True
    last_fetched_at: Optional[str] = None
    last_status: Optional[str] = None


class NewsSourcesResponse(BaseModel):
    sources: List[NewsSourceSchema]


class NewsRefreshResponse(BaseModel):
    status: str
    articles_fetched: int
    new_articles_saved: int
    duplicates_skipped: int
    sources_contacted: int
    sources_succeeded: int
    errors: List[str] = Field(default_factory=list)
    refreshed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    gdelt_usage: Optional[GdeltUsageStatusSchema] = None
