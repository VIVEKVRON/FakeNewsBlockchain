"""
scripts/demo_image_analysis.py
Demonstration script testing POST /api/v1/analyze/image with synthetic JPG, PNG, WEBP,
and malformed images against the running local server.
"""

import sys
import io
import json
from pathlib import Path
import numpy as np
import cv2
from PIL import Image
import urllib.request
import urllib.error

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def make_image_bytes(format: str, text: str = "") -> bytes:
    img = np.full((140, 420, 3), 255, dtype=np.uint8)
    if text:
        cv2.putText(img, text, (15, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2)
    pil_img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    buf = io.BytesIO()
    pil_img.save(buf, format=format)
    return buf.getvalue()


def post_multipart(url: str, filename: str, file_bytes: bytes, content_type: str):
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    data = []
    data.append(f"--{boundary}".encode())
    data.append(f'Content-Disposition: form-data; name="file"; filename="{filename}"'.encode())
    data.append(f"Content-Type: {content_type}".encode())
    data.append(b"")
    data.append(file_bytes)
    data.append(f"--{boundary}--".encode())
    data.append(b"")
    body = b"\r\n".join(data)

    req = urllib.request.Request(url, data=body)
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def main():
    print("=" * 80)
    print("FAKENEWSBLOCKCHAIN - MULTIMODAL IMAGE ANALYSIS DEMO")
    print("Testing /api/v1/analyze/image via Frontend Proxy (http://127.0.0.1:5173)")
    print("=" * 80)

    test_cases = [
        {
            "category": "1. JPG WITH READABLE TEXT",
            "filename": "breaking_news.jpg",
            "format": "JPEG",
            "text": "19 Kids and Counting TLC Series",
            "mime": "image/jpeg",
        },
        {
            "category": "2. PNG WITHOUT TEXT (BLANK GRAPHIC)",
            "filename": "chart_graphic.png",
            "format": "PNG",
            "text": "",
            "mime": "image/png",
        },
        {
            "category": "3. WEBP IMAGE WITH FORENSIC COMPRESSION",
            "filename": "social_post.webp",
            "format": "WEBP",
            "text": "Breaking News Alert",
            "mime": "image/webp",
        },
        {
            "category": "4. CORRUPTED / MALFORMED FILE",
            "filename": "corrupted.jpg",
            "format": "RAW",
            "text": "CORRUPT_BYTES",
            "mime": "image/jpeg",
            "raw_bytes": b"NON_IMAGE_CORRUPTED_BYTES_1234567890",
        },
    ]

    for tc in test_cases:
        print(f"\n>>> Running: {tc['category']}")
        print(f"File: {tc['filename']} ({tc['mime']})")
        
        file_bytes = tc.get("raw_bytes") or make_image_bytes(tc["format"], tc.get("text", ""))
        status_code, res = post_multipart(
            "http://127.0.0.1:5173/api/v1/analyze/image",
            tc["filename"],
            file_bytes,
            tc["mime"]
        )

        print(f"HTTP Status: {status_code}")
        if status_code == 200:
            meta = res["metadata"]
            ocr = res["ocr"]
            ela = res["ela"]
            print(f"  [Metadata] Resolution: {meta['width']}x{meta['height']} | Format: {meta['format']} | Size: {meta['file_size_bytes']} bytes")
            print(f"  [OCR] Has Text: {ocr['has_text']} | Word Count: {ocr['word_count']} | Avg Conf: {ocr['average_confidence']:.2f}")
            print(f"  [OCR Transcribed]: \"{ocr['full_text']}\"")
            print(f"  [ELA Metrics] Mean Error: {ela['mean_error']} | Max Error: {ela['max_error']} | Std Error: {ela['std_error']} | Anomalies: {ela['potential_compression_anomalies']}")
            print(f"  [ELA Visual Map]: Base64 image length: {len(ela.get('ela_image_base64') or '')} chars")
            print(f"  [Observations]: {res['observations']}")
        else:
            print(f"  [Rejected Correctly]: {res}")
        print("-" * 80)


if __name__ == "__main__":
    main()
