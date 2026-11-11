"""
Shared pytest configuration & test isolation guards.

Protects production SQLite databases (`data/news_cache.db`, `data/database/fakenews.db`)
and prevents unmocked automated tests from sending real HTTP requests to
Google Fact Check Tools or GDELT DOC 2.0 (preserving the 200-request GDELT allowance).
"""

import json
import os
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
import requests

from backend.app.config import get_settings
from backend.app.database import connection as db_connection
from backend.app.services import news_service, verification_service


def _build_synthetic_response(url: str) -> requests.Response:
    resp = requests.Response()
    resp.status_code = 200
    resp.url = url
    if "factchecktools.googleapis.com" in url:
        payload = {"claims": []}
    elif "api.gdeltproject.org" in url:
        payload = {
            "articles": [
                {
                    "title": "Global Science Cooperation Expands Research Networks",
                    "url": "https://www.reuters.com/science/global-research-networks-2026/?utm_source=gdelt",
                    "domain": "reuters.com",
                    "seendate": "20261110T090000Z",
                    "language": "English",
                    "sourcecountry": "United States",
                }
            ]
        }
    else:
        payload = {}
    resp._content = json.dumps(payload).encode("utf-8")
    resp.headers["Content-Type"] = "application/json"
    return resp


@pytest.fixture(scope="session", autouse=True)
def isolate_databases_and_external_http(tmp_path_factory):
    """
    Copies SQLite DBs into a temporary pytest session directory and guards unmocked
    `requests.Session.get` calls targeting Google Fact Check or GDELT endpoints.
    """
    settings = get_settings()
    tmp_dir = tmp_path_factory.mktemp("pytest_isolated_dbs")

    real_news_db = settings.PROJECT_ROOT / "data" / "news_cache.db"
    tmp_news_db = tmp_dir / "news_cache.db"
    if real_news_db.exists():
        shutil.copy2(real_news_db, tmp_news_db)

    real_main_db = settings.get_absolute_path("data/database/fakenews.db")
    tmp_main_db = tmp_dir / "fakenews.db"
    if real_main_db.exists():
        shutil.copy2(real_main_db, tmp_main_db)

    old_override = os.environ.get("FAKE_NEWS_TEST_NEWS_DB")
    os.environ["FAKE_NEWS_TEST_NEWS_DB"] = str(tmp_news_db)

    # Reset service singletons so they bind to isolated test DBs
    news_service._news_service_instance = None
    verification_service._service_instance = None

    original_session_get = requests.Session.get

    def guarded_session_get(self, url, *args, **kwargs):
        url_str = str(url or "")
        if "factchecktools.googleapis.com" in url_str or "api.gdeltproject.org" in url_str:
            return _build_synthetic_response(url_str)
        return original_session_get(self, url, *args, **kwargs)

    with (
        patch.object(db_connection, "DB_PATH", tmp_main_db),
        patch.object(db_connection, "get_db_path", return_value=tmp_main_db),
        patch.object(requests.Session, "get", guarded_session_get),
    ):
        db_connection.init_db()
        yield {
            "news_db": tmp_news_db,
            "main_db": tmp_main_db,
        }

    news_service._news_service_instance = None
    verification_service._service_instance = None
    if old_override is None:
        os.environ.pop("FAKE_NEWS_TEST_NEWS_DB", None)
    else:
        os.environ["FAKE_NEWS_TEST_NEWS_DB"] = old_override
