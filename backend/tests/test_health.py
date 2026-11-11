"""
backend/tests/test_health.py
Unit tests for the FastAPI health and diagnostic endpoints.
"""

from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["project"] == "FakeNewsBlockchain"
    assert data["status"] == "running"


def test_health_endpoint():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["version"] == "1.0.0"
    assert data["runtime"]["device"] == "cpu"
    assert data["runtime"]["torch_threads"] == 4
    
    # Check that all 4 primary assets report verified on disk
    paths = data["asset_paths_verified"]
    assert paths["fever_verifier"] is True
    assert paths["bert_isot"] is True
    assert paths["bert_liar"] is True
    assert paths["faiss_index"] is True
