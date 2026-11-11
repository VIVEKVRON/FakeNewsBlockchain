"""
backend/app/api/routes/news.py
FastAPI router for live breaking news monitoring, source queries,
feed refresh, and one-click article verification dispatch.
"""

from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status
from backend.app.schemas.news import (
    NewsListResponse,
    NewsSourcesResponse,
    NewsRefreshResponse,
)
from backend.app.schemas.verification import GdeltUsageStatusSchema
from backend.app.schemas.article import ArticleVerificationResponse
from backend.app.services.news_service import NewsService, get_news_service

router = APIRouter(prefix="/news", tags=["Live News Monitoring"])


@router.get(
    "",
    response_model=NewsListResponse,
    summary="List Cached News Articles",
    description="Retrieve paginated breaking news articles from local SQLite cache with keyword, publisher, and category filters.",
)
def list_news(
    keyword: Optional[str] = Query(None, description="Search keyword in title or description"),
    publisher: Optional[str] = Query(None, description="Filter by publisher name"),
    category: Optional[str] = Query(None, description="Filter by category (e.g. World, Science)"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    news_service: NewsService = Depends(get_news_service),
) -> NewsListResponse:
    return news_service.get_articles(
        keyword=keyword,
        publisher=publisher,
        category=category,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/sources",
    response_model=NewsSourcesResponse,
    summary="List Monitored News Sources",
    description="Retrieve active RSS feeds and GDELT 2.0 endpoints configured for news monitoring.",
)
def list_sources(
    news_service: NewsService = Depends(get_news_service),
) -> NewsSourcesResponse:
    return news_service.get_sources()


@router.post(
    "/refresh",
    response_model=NewsRefreshResponse,
    summary="Refresh News Feeds",
    description="Fetch latest articles from all active RSS feeds and GDELT 2.0, deduplicate against SQLite cache, and record ingestion timestamp.",
)
def refresh_news(
    news_service: NewsService = Depends(get_news_service),
) -> NewsRefreshResponse:
    return news_service.refresh_feeds()


@router.get(
    "/gdelt-usage",
    response_model=GdeltUsageStatusSchema,
    summary="Get Shared External API Usage & GDELT Quota Status",
    description="Returns persistent shared GDELT request counter (used/remaining/limit/cache hits/warnings) and Google Fact Check API configuration availability without exposing secrets.",
)
def get_gdelt_usage(
    news_service: NewsService = Depends(get_news_service),
) -> GdeltUsageStatusSchema:
    return news_service.get_gdelt_usage()


@router.post(
    "/{article_id}/verify",
    response_model=ArticleVerificationResponse,
    summary="Verify Cached News Article",
    description="Extract full content from a cached news article, run the factual verification pipeline, and store verified verdict.",
)
def verify_news_article(
    article_id: str,
    news_service: NewsService = Depends(get_news_service),
) -> ArticleVerificationResponse:
    try:
        return news_service.verify_cached_article(article_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Verification failed: {str(e)}"
        )
