"""
backend/tests/test_image.py
Unit and integration tests for multimodal image analysis:
  - JPG, PNG, WEBP uploads
  - Text-containing and text-free images
  - Error Level Analysis (ELA) metrics & base64 visualization map
  - Malformed, empty, and oversized file rejections
  - Epistemological disclaimer verifications
"""

import io
import pytest
import numpy as np
import cv2
from PIL import Image
from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def _create_test_image(format: str = "JPEG", text: str = "") -> bytes:
    """Helper to generate in-memory synthetic test images."""
    img = np.full((120, 360, 3), 255, dtype=np.uint8)
    if text:
        cv2.putText(img, text, (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2)
    
    pil_img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    buf = io.BytesIO()
    pil_img.save(buf, format=format)
    return buf.getvalue()


def test_image_analysis_jpg_with_text():
    """Tests JPG upload with readable text."""
    img_bytes = _create_test_image(format="JPEG", text="Official Breaking News")
    
    response = client.post(
        "/api/v1/analyze/image",
        files={"file": ("news_sample.jpg", img_bytes, "image/jpeg")}
    )
    assert response.status_code == 200
    data = response.json()

    # Metadata
    assert data["metadata"]["filename"] == "news_sample.jpg"
    assert data["metadata"]["format"] == "JPEG"
    assert data["metadata"]["width"] == 360
    assert data["metadata"]["height"] == 120

    # OCR
    assert data["ocr"]["has_text"] is True
    assert data["ocr"]["word_count"] >= 1
    assert any("news" in block["text"].lower() or "official" in block["text"].lower() for block in data["ocr"]["text_blocks"])
    assert data["ocr"]["average_confidence"] > 0.0

    # ELA
    assert data["ela"]["mean_error"] >= 0.0
    assert data["ela"]["max_error"] >= 0
    assert data["ela"]["ela_image_base64"].startswith("data:image/jpeg;base64,")

    # Disclaimers & Epistemological Semantics
    assert data["verdict"] == "UNVERIFIED"
    assert data["factual_verification_status"] == "UNVERIFIED"
    assert len(data["limitations"]) >= 3
    assert any("not definitive proof of image forgery" in lim.lower() for lim in data["limitations"])


def test_image_analysis_png_without_text():
    """Tests PNG upload without text."""
    img_bytes = _create_test_image(format="PNG", text="")
    
    response = client.post(
        "/api/v1/analyze/image",
        files={"file": ("blank_graphic.png", img_bytes, "image/png")}
    )
    assert response.status_code == 200
    data = response.json()

    assert data["metadata"]["format"] == "PNG"
    assert data["ocr"]["has_text"] is False
    assert data["ocr"]["word_count"] == 0
    assert data["ocr"]["full_text"] == ""
    assert data["ela"]["mean_error"] >= 0.0


def test_image_analysis_webp():
    """Tests WEBP upload."""
    img_bytes = _create_test_image(format="WEBP", text="Webp Test")
    
    response = client.post(
        "/api/v1/analyze/image",
        files={"file": ("sample.webp", img_bytes, "image/webp")}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["metadata"]["format"] == "WEBP"
    assert data["ela"]["ela_image_base64"] is not None


def test_image_malformed_file():
    """Tests rejection of corrupted/malformed image bytes."""
    corrupted_bytes = b"CORRUPTED_NON_IMAGE_HEADER_12345" * 10
    
    response = client.post(
        "/api/v1/analyze/image",
        files={"file": ("corrupt.jpg", corrupted_bytes, "image/jpeg")}
    )
    assert response.status_code == 400
    assert "Malformed or corrupt image file" in response.json()["detail"]


def test_image_oversized_file():
    """Tests rejection of files exceeding 10 MB."""
    oversized_bytes = b"0" * (11 * 1024 * 1024)  # 11 MB
    
    response = client.post(
        "/api/v1/analyze/image",
        files={"file": ("huge_photo.jpg", oversized_bytes, "image/jpeg")}
    )
    assert response.status_code == 413
    assert "exceeds maximum allowable size of 10 MB" in response.json()["detail"]


def test_image_empty_file():
    """Tests rejection of 0-byte upload."""
    response = client.post(
        "/api/v1/analyze/image",
        files={"file": ("empty.jpg", b"", "image/jpeg")}
    )
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


def test_image_unsupported_format():
    """Tests rejection of disallowed extensions."""
    response = client.post(
        "/api/v1/analyze/image",
        files={"file": ("document.pdf", b"%PDF-1.4...", "application/pdf")}
    )
    assert response.status_code == 400
    assert "Unsupported file extension" in response.json()["detail"]
