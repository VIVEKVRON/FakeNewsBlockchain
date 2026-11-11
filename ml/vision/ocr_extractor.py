"""
ml/vision/ocr_extractor.py
PaddleOCR-powered text extraction engine.
Runs CPU inference locally to detect and transcribe text blocks from uploaded images.
"""

import io
import threading
from typing import List, Dict, Any, Optional
import numpy as np
import cv2
from PIL import Image

from backend.app.utils.logger import logger
from backend.app.schemas.image import OCRResult, OCRTextBlock


class OCRExtractor:
    """
    Singleton wrapper for PaddleOCR running on CPU.
    """
    _instance: Optional["OCRExtractor"] = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(OCRExtractor, cls).__new__(cls)
                cls._instance._ocr = None
                cls._instance._init_lock = threading.Lock()
            return cls._instance

    def _get_ocr_engine(self):
        """Lazy loads PaddleOCR on first request."""
        if self._ocr is None:
            with self._init_lock:
                if self._ocr is None:
                    # PyTorch must be imported before paddle on Windows
                    import torch  # noqa: F401
                    import paddlex.inference.models.runners.paddle_static.runner as runner_mod

                    # Block MKLDNN/oneDNN for OCR models to prevent Windows PIR DoubleAttribute crash
                    for m in ["PP-OCRv6_medium_det", "PP-OCRv6_medium_rec", "PP-OCRv4_mobile_det", "PP-OCRv4_mobile_rec"]:
                        if m not in runner_mod.MKLDNN_BLOCKLIST:
                            runner_mod.MKLDNN_BLOCKLIST.append(m)

                    from paddleocr import PaddleOCR
                    logger.info("Initializing PaddleOCR engine on CPU...")
                    self._ocr = PaddleOCR(
                        use_doc_orientation_classify=False,
                        use_doc_unwarping=False,
                        use_textline_orientation=False,
                        lang="en"
                    )
                    logger.info("PaddleOCR engine initialized successfully.")
        return self._ocr

    def extract(self, image_bytes: bytes) -> OCRResult:
        """
        Extracts all textual lines from raw image bytes.
        """
        try:
            pil_img = Image.open(io.BytesIO(image_bytes))
            if pil_img.mode != "RGB":
                pil_img = pil_img.convert("RGB")
            
            # Limit maximum resolution to 2048 to prevent memory spikes on CPU
            w, h = pil_img.size
            if max(w, h) > 2048:
                scale = 2048.0 / max(w, h)
                pil_img = pil_img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)

            img_np = np.array(pil_img, dtype=np.uint8)
        except Exception as e:
            logger.error(f"Image decode error in OCR: {e}")
            raise ValueError(f"Could not decode image for OCR: {e}")

        engine = self._get_ocr_engine()

        try:
            predictions = list(engine.predict(img_np))
        except Exception as e:
            logger.error(f"PaddleOCR prediction failed: {e}")
            raise RuntimeError(f"OCR inference failed: {e}")

        text_blocks: List[OCRTextBlock] = []
        confidences: List[float] = []

        for pred in predictions:
            if not isinstance(pred, dict):
                continue
            rec_texts = pred.get("rec_texts", [])
            rec_scores = pred.get("rec_scores", [])
            rec_polys = pred.get("rec_polys", [])

            for idx, text in enumerate(rec_texts):
                clean_text = str(text).strip()
                if not clean_text:
                    continue
                score = float(rec_scores[idx]) if idx < len(rec_scores) else 0.0
                
                # Format polygon coordinates
                box_coords = []
                if idx < len(rec_polys):
                    poly = rec_polys[idx]
                    if hasattr(poly, "tolist"):
                        box_coords = poly.tolist()
                    elif isinstance(poly, (list, tuple)):
                        box_coords = [list(pt) for pt in poly]

                text_blocks.append(
                    OCRTextBlock(
                        text=clean_text,
                        confidence=round(score, 4),
                        box=box_coords
                    )
                )
                confidences.append(score)

        has_text = len(text_blocks) > 0
        full_text = " ".join(block.text for block in text_blocks)
        word_count = len(full_text.split()) if has_text else 0
        avg_conf = round(float(np.mean(confidences)), 4) if confidences else 0.0

        return OCRResult(
            has_text=has_text,
            full_text=full_text,
            word_count=word_count,
            average_confidence=avg_conf,
            text_blocks=text_blocks,
        )


def get_ocr_extractor() -> OCRExtractor:
    return OCRExtractor()
