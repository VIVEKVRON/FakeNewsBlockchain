"""
backend/app/services/news_service.py
Service for live breaking news monitoring, public RSS/GDELT ingestion,
Trafilatura full-text extraction, SSRF protection, SQLite caching, and deduplication.
"""

import os
import io
import json
import sqlite3
import hashlib
import socket
import ipaddress
import urllib.parse
from datetime import datetime, timezone
from typing import List, Optional, Tuple, Dict, Any
import feedparser
import trafilatura

from backend.app.config import get_settings
from backend.app.utils.logger import logger
from backend.app.schemas.news import (
    NewsArticleSchema,
    NewsListResponse,
    NewsSourceSchema,
    NewsSourcesResponse,
    NewsRefreshResponse,
)
from backend.app.schemas.article import (
    ArticleVerificationRequest,
    ArticleVerificationResponse,
)
from backend.app.schemas.verification import VerdictEnum, GdeltUsageStatusSchema
from backend.app.services.verification_service import get_verification_service
from backend.app.services.external_apis.evidence_cache import ExternalEvidenceCache
from backend.app.services.external_apis.gdelt_usage_tracker import GdeltUsageTracker
from backend.app.services.external_apis.gdelt_client import GdeltClient
from backend.app.services.external_apis.quota_db import validate_external_http_url, resolve_news_cache_db_path


def is_safe_url(url: str) -> bool:
    """
    Validates URL to protect against Server-Side Request Forgery (SSRF).
    Blocks private networks, localhost, link-local, loopback, and non-http schemes.
    """
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        hostname = parsed.hostname
        if not hostname:
            return False

        # Disallow raw localhost strings
        if hostname.lower() in ("localhost", "127.0.0.1", "::1"):
            return False

        # Resolve IP addresses
        addr_info = socket.getaddrinfo(hostname, None)
        for _, _, _, _, sockaddr in addr_info:
            ip_str = sockaddr[0]
            ip = ipaddress.ip_address(ip_str)
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_reserved
                or ip.is_link_local
                or ip.is_multicast
            ):
                return False
        return True
    except Exception:
        return False


def normalize_canonical_url(raw_url: str) -> str:
    """
    Normalizes a news URL by stripping tracking parameters (UTM, Facebook, etc.).
    """
    try:
        parsed = urllib.parse.urlparse(raw_url)
        qs = urllib.parse.parse_qsl(parsed.query)
        tracking_params = {
            "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
            "at_medium", "at_campaign", "fbclid", "gclid", "ref", "source"
        }
        filtered_qs = [(k, v) for k, v in qs if k.lower() not in tracking_params]
        new_query = urllib.parse.urlencode(filtered_qs)
        canonical = urllib.parse.urlunparse((
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path.rstrip("/"),
            parsed.params,
            new_query,
            ""  # Strip fragment
        ))
        return canonical
    except Exception:
        return raw_url.strip()


class NewsService:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = resolve_news_cache_db_path(db_path)
        self._ensure_db_initialized()
        self.gdelt_tracker = GdeltUsageTracker(db_path=self.db_path)
        self.gdelt_cache = ExternalEvidenceCache(db_path=self.db_path)
        self.gdelt_client = GdeltClient(tracker=self.gdelt_tracker, cache=self.gdelt_cache)
        self.verification_service = get_verification_service()

    def get_gdelt_usage(self) -> GdeltUsageStatusSchema:
        settings = get_settings()
        status_obj = self.gdelt_tracker.get_status()
        google_avail = bool(settings.GOOGLE_FACT_CHECK_API_KEY and settings.GOOGLE_FACT_CHECK_API_KEY.strip())
        return GdeltUsageStatusSchema(
            **status_obj.to_dict(),
            google_fact_check_available=google_avail,
        )

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_db_initialized(self):
        """Initializes SQLite tables for articles and sources if not existing."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS news_articles (
                    id TEXT PRIMARY KEY,
                    canonical_url TEXT UNIQUE NOT NULL,
                    url_hash TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    content TEXT,
                    publisher TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    category TEXT DEFAULT 'General',
                    published_at TEXT,
                    ingested_at TEXT NOT NULL,
                    verified_verdict TEXT DEFAULT NULL,
                    verification_data TEXT DEFAULT NULL
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_articles_canonical ON news_articles(canonical_url);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_articles_published ON news_articles(published_at DESC);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_articles_publisher ON news_articles(publisher);")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS news_sources (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    feed_url TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    category TEXT NOT NULL,
                    is_active INTEGER DEFAULT 1,
                    last_fetched_at TEXT,
                    last_status TEXT
                );
            """)

            # Populate default reputable feeds if empty
            cursor = conn.execute("SELECT COUNT(*) FROM news_sources;")
            count = cursor.fetchone()[0]
            if count == 0:
                default_sources = [
                    ("src-bbc-world", "BBC News World", "https://feeds.bbci.co.uk/news/world/rss.xml", "rss", "World", 1),
                    ("src-npr-news", "NPR Top Stories", "https://feeds.npr.org/1001/rss.xml", "rss", "Top Stories", 1),
                    ("src-nyt-world", "New York Times World", "https://rss.nytimes.com/services/xml/rss/nyt/World.xml", "rss", "International", 1),
                    ("src-phys-sci", "Phys.org Science", "https://phys.org/rss-feed/", "rss", "Science", 1),
                    ("src-gdelt-global", "GDELT 2.0 Global Events", "https://api.gdeltproject.org/api/v2/doc/doc?query=sourcelang:eng&mode=ArtList&maxrecords=25&format=json", "gdelt", "Global", 1),
                ]
                conn.executemany("""
                    INSERT INTO news_sources (id, name, feed_url, source_type, category, is_active)
                    VALUES (?, ?, ?, ?, ?, ?);
                """, default_sources)
            conn.commit()

    def get_sources(self) -> NewsSourcesResponse:
        """Returns all configured news sources."""
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM news_sources ORDER BY name ASC;").fetchall()
            sources = [
                NewsSourceSchema(
                    id=row["id"],
                    name=row["name"],
                    feed_url=row["feed_url"],
                    source_type=row["source_type"],
                    category=row["category"],
                    is_active=bool(row["is_active"]),
                    last_fetched_at=row["last_fetched_at"],
                    last_status=row["last_status"],
                )
                for row in rows
            ]
            return NewsSourcesResponse(sources=sources)

    def extract_full_text_safe(self, url: str) -> Optional[str]:
        """
        Uses Trafilatura to extract public article text safely with SSRF checks and timeouts.
        Does NOT bypass paywalls or auth.
        """
        if not is_safe_url(url):
            logger.warning(f"SSRF safety check blocked URL: {url}")
            return None

        try:
            downloaded = trafilatura.fetch_url(url)
            if not downloaded:
                return None
            extracted = trafilatura.extract(
                downloaded,
                include_comments=False,
                include_tables=False,
                no_fallback=False
            )
            return extracted.strip() if extracted else None
        except Exception as e:
            logger.warning(f"Trafilatura extraction skipped for {url}: {e}")
            return None

    def refresh_feeds(self) -> NewsRefreshResponse:
        """
        Ingests articles from all active RSS feeds and GDELT 2.0.
        Performs SSRF validation, canonical URL normalization, and deduplication.
        """
        sources = self.get_sources().sources
        active_sources = [s for s in sources if s.is_active]

        total_fetched = 0
        new_saved = 0
        duplicates = 0
        sources_succeeded = 0
        errors: List[str] = []

        now_iso = datetime.now(timezone.utc).isoformat()

        for source in active_sources:
            try:
                if source.source_type == "rss":
                    f_count, s_count, d_count = self._ingest_rss_source(source, now_iso)
                elif source.source_type == "gdelt":
                    f_count, s_count, d_count = self._ingest_gdelt_source(source, now_iso)
                else:
                    continue

                total_fetched += f_count
                new_saved += s_count
                duplicates += d_count
                sources_succeeded += 1

                self._update_source_status(source.id, now_iso, f"OK ({s_count} new, {d_count} dupes)")
            except Exception as e:
                err_msg = f"Source '{source.name}' error: {str(e)}"
                logger.warning(err_msg)
                errors.append(err_msg)
                self._update_source_status(source.id, now_iso, f"Error: {str(e)[:100]}")

        # If zero articles in DB (e.g. offline/isolated environment), seed initial offline benchmark articles
        with self._get_connection() as conn:
            db_count = conn.execute("SELECT COUNT(*) FROM news_articles;").fetchone()[0]
            if db_count == 0:
                self._seed_sample_articles(now_iso)
                new_saved += 4

        return NewsRefreshResponse(
            status="success" if sources_succeeded > 0 else "partial",
            articles_fetched=total_fetched,
            new_articles_saved=new_saved,
            duplicates_skipped=duplicates,
            sources_contacted=len(active_sources),
            sources_succeeded=sources_succeeded,
            errors=errors,
            refreshed_at=now_iso,
            gdelt_usage=self.get_gdelt_usage(),
        )

    def _ingest_rss_source(self, source: NewsSourceSchema, timestamp: str) -> Tuple[int, int, int]:
        feed = feedparser.parse(source.feed_url)
        entries = getattr(feed, "entries", [])
        fetched = len(entries)
        saved = 0
        dupes = 0

        with self._get_connection() as conn:
            for entry in entries:
                raw_url = getattr(entry, "link", None)
                title = getattr(entry, "title", None)
                if not raw_url or not title:
                    continue

                canonical_url = normalize_canonical_url(raw_url)
                description = getattr(entry, "summary", "") or getattr(entry, "description", "")
                published_at = getattr(entry, "published", "") or timestamp

                url_hash = hashlib.sha256(canonical_url.encode()).hexdigest()
                content_hash = hashlib.sha256((title + description).encode()).hexdigest()
                article_id = f"art-news-{url_hash[:12]}"

                # Check existence
                cursor = conn.execute("SELECT id FROM news_articles WHERE canonical_url = ?;", (canonical_url,))
                if cursor.fetchone():
                    dupes += 1
                    continue

                conn.execute("""
                    INSERT INTO news_articles (
                        id, canonical_url, url_hash, content_hash, title, description, content,
                        publisher, source_type, category, published_at, ingested_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, (
                    article_id, canonical_url, url_hash, content_hash, title.strip(),
                    description.strip() if description else None, None,
                    source.name, "rss", source.category, published_at, timestamp
                ))
                saved += 1
            conn.commit()

        return fetched, saved, dupes

    def _ingest_gdelt_source(self, source: NewsSourceSchema, timestamp: str) -> Tuple[int, int, int]:
        gd_res = self.gdelt_client.fetch_feed_articles(
            feed_url=source.feed_url,
            source_label="news_refresh",
        )
        if gd_res.status not in ("ok", "ok_cached", "no_results"):
            raise RuntimeError(gd_res.error_detail or f"GDELT skipped ({gd_res.status})")

        fetched = gd_res.raw_count or len(gd_res.articles)
        saved = 0
        db_dupes = 0

        with self._get_connection() as conn:
            for item in gd_res.articles:
                if not item.url or not item.title or not validate_external_http_url(item.url):
                    continue

                canonical_url = normalize_canonical_url(item.url)
                domain = item.domain or "GDELT Source"
                seendate = item.published_at or timestamp

                url_hash = hashlib.sha256(canonical_url.encode()).hexdigest()
                content_hash = hashlib.sha256(item.title.encode()).hexdigest()
                article_id = f"art-news-{url_hash[:12]}"

                cursor = conn.execute("SELECT id FROM news_articles WHERE canonical_url = ?;", (canonical_url,))
                if cursor.fetchone():
                    db_dupes += 1
                    continue

                conn.execute("""
                    INSERT INTO news_articles (
                        id, canonical_url, url_hash, content_hash, title, description, content,
                        publisher, source_type, category, published_at, ingested_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, (
                    article_id, canonical_url, url_hash, content_hash, item.title.strip(),
                    None, None, domain, "gdelt", source.category, seendate, timestamp
                ))
                saved += 1
            conn.commit()

        return fetched, saved, gd_res.duplicates_collapsed + db_dupes

    def _update_source_status(self, source_id: str, timestamp: str, status_msg: str):
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE news_sources
                SET last_fetched_at = ?, last_status = ?
                WHERE id = ?;
            """, (timestamp, status_msg, source_id))
            conn.commit()

    def _seed_sample_articles(self, timestamp: str):
        """Seeds offline sample articles if no external network is available."""
        samples = [
            (
                "art-news-sample01",
                "https://www.bbc.co.uk/news/world-sample-01",
                "TLC Reality Series 19 Kids and Counting Documents Family Life",
                "19 Kids and Counting is an American reality television show featuring the Duggar family. The series originally documented their day-to-day household activities.",
                "BBC News World",
                "rss",
                "Entertainment"
            ),
            (
                "art-news-sample02",
                "https://www.npr.org/sections/sample-02",
                "Broadcaster Network Historical Syndication and Television Programs",
                "19 Kids and Counting aired on HBO. The show attracted millions of viewers across the country during its primetime weekend broadcast slot.",
                "NPR Top Stories",
                "rss",
                "Top Stories"
            ),
            (
                "art-news-sample03",
                "https://www.nytimes.com/sample-03",
                "Television Show Cancellation Date Rumors and Executive Delays",
                "19 Kids and Counting was cancelled in 2030. Industry analysts claimed that executives delayed the official announcement.",
                "New York Times World",
                "rss",
                "Media"
            ),
            (
                "art-news-sample04",
                "https://phys.org/news/sample-04",
                "Planetary Exploration and Speculative Biology in Solar System",
                "Biologists discovered alien potatoes on Pluto in 2026. The extraterrestrial tubers supposedly survive in sub-zero atmospheric methane.",
                "Phys.org Science",
                "rss",
                "Science"
            ),
        ]
        with self._get_connection() as conn:
            for art_id, url, title, desc, pub, stype, cat in samples:
                url_hash = hashlib.sha256(url.encode()).hexdigest()
                content_hash = hashlib.sha256((title + desc).encode()).hexdigest()
                conn.execute("""
                    INSERT OR IGNORE INTO news_articles (
                        id, canonical_url, url_hash, content_hash, title, description, content,
                        publisher, source_type, category, published_at, ingested_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, (
                    art_id, url, url_hash, content_hash, title, desc, desc,
                    pub, stype, cat, timestamp, timestamp
                ))
            conn.commit()

    def get_articles(
        self,
        keyword: Optional[str] = None,
        publisher: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 20,
        offset: int = 0
    ) -> NewsListResponse:
        """Retrieves cached articles with filtering and pagination."""
        query = "SELECT * FROM news_articles WHERE 1=1"
        params: List[Any] = []

        if keyword and keyword.strip():
            kw = f"%{keyword.strip()}%"
            query += " AND (title LIKE ? OR description LIKE ? OR content LIKE ?)"
            params.extend([kw, kw, kw])

        if publisher and publisher.strip() and publisher != "ALL":
            query += " AND publisher LIKE ?"
            params.append(f"%{publisher.strip()}%")

        if category and category.strip() and category != "ALL":
            query += " AND category = ?"
            params.append(category.strip())

        # Count total
        count_query = query.replace("SELECT *", "SELECT COUNT(*)")
        with self._get_connection() as conn:
            total = conn.execute(count_query, params).fetchone()[0]

            # Paginated records
            query += " ORDER BY published_at DESC, ingested_at DESC LIMIT ? OFFSET ?;"
            params.extend([limit, offset])

            rows = conn.execute(query, params).fetchall()
            articles = []
            for row in rows:
                verdict_val = None
                if row["verified_verdict"]:
                    try:
                        verdict_val = VerdictEnum(row["verified_verdict"])
                    except ValueError:
                        pass

                articles.append(
                    NewsArticleSchema(
                        id=row["id"],
                        canonical_url=row["canonical_url"],
                        title=row["title"],
                        description=row["description"],
                        content=row["content"],
                        publisher=row["publisher"],
                        source_type=row["source_type"],
                        category=row["category"],
                        published_at=row["published_at"],
                        ingested_at=row["ingested_at"],
                        verified_verdict=verdict_val,
                        verification_summary=None,
                        is_new=False,
                    )
                )

            return NewsListResponse(
                total=total,
                limit=limit,
                offset=offset,
                articles=articles,
            )

    def verify_cached_article(self, article_id: str) -> ArticleVerificationResponse:
        """
        Retrieves a cached article, extracts body text, and passes it to the
        factual verification engine. Updates the SQLite cache with the result.
        """
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM news_articles WHERE id = ?;", (article_id,)).fetchone()
            if not row:
                raise ValueError(f"Article '{article_id}' not found in local news cache.")

        title = row["title"]
        body_text = row["content"]

        # If body content is missing or short, attempt safe Trafilatura extraction from canonical URL
        if not body_text or len(body_text.strip()) < 20:
            extracted = self.extract_full_text_safe(row["canonical_url"])
            if extracted and len(extracted) >= 20:
                body_text = extracted
                # Update SQLite with full text
                with self._get_connection() as conn:
                    conn.execute("UPDATE news_articles SET content = ? WHERE id = ?;", (body_text, article_id))
                    conn.commit()
            else:
                body_text = row["description"] or title

        # Ensure minimum length for verification service
        if len(body_text) < 20:
            body_text = f"{title}. {body_text}".strip()

        # Run Verification Service
        req = ArticleVerificationRequest(
            title=title,
            text=body_text,
            max_claims=3,
            source_url=row["canonical_url"],
        )
        res = self.verification_service.verify_article(req)

        # Update SQLite cache with verified verdict
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE news_articles
                SET verified_verdict = ?, verification_data = ?
                WHERE id = ?;
            """, (res.overall_verdict.value, res.model_dump_json(), article_id))
            conn.commit()

        return res


_news_service_instance: Optional[NewsService] = None

def get_news_service() -> NewsService:
    global _news_service_instance
    if _news_service_instance is None:
        _news_service_instance = NewsService()
    return _news_service_instance
