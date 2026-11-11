"""
ml/vision/ela_analyzer.py
Local, CPU-optimized Error Level Analysis (ELA) using OpenCV and Pillow.
Measures compression artifact discrepancies across an image without cloud APIs.
Explicitly treats results as compression variance indicators, NOT proof of manipulation.
"""

import io
import base64
from dataclasses import dataclass
from typing import Optional, Tuple, Dict, Any, List
import numpy as np
import cv2
from PIL import Image

from backend.app.utils.logger import logger


@dataclass
class ELAMetrics:
    mean_error: float
    max_error: int
    std_error: float
    variance_score: float
    quality_tested: int
    potential_compression_anomalies: bool
    anomaly_regions_detected: int
    ela_image_base64: Optional[str]


class ELAAnalyzer:
    """
    Performs digital image Error Level Analysis by resaving the image at a known
    compression quality (default 90) and analyzing pixel-level delta variance.
    """
    DEFAULT_QUALITY = 90
    SCALE_FACTOR = 15.0       # Standard forensic contrast enhancement multiplier
    BLOCK_SIZE = 32           # Grid size for local anomaly inspection
    ANOMALY_Z_THRESH = 3.0    # Standard deviations above median to flag localized error spike

    def analyze(self, image_bytes: bytes, quality: int = DEFAULT_QUALITY) -> ELAMetrics:
        # Load via Pillow to handle format conversion cleanly
        try:
            pil_image = Image.open(io.BytesIO(image_bytes))
            # Convert to RGB (handles RGBA, Palette, Grayscale)
            if pil_image.mode != "RGB":
                pil_image = pil_image.convert("RGB")
        except Exception as e:
            logger.error(f"Failed to open image in ELA: {e}")
            raise ValueError(f"Invalid image format for ELA: {e}")

        # Limit max dimensions to 1920 to keep CPU inference fast and memory capped
        width, height = pil_image.size
        max_dim = max(width, height)
        if max_dim > 1920:
            scale = 1920.0 / max_dim
            new_w, new_h = int(width * scale), int(height * scale)
            pil_image = pil_image.resize((new_w, new_h), Image.Resampling.LANCZOS)

        orig_arr = np.array(pil_image, dtype=np.uint8)

        # Resave in-memory as JPEG at reference quality
        buf = io.BytesIO()
        pil_image.save(buf, format="JPEG", quality=quality)
        buf.seek(0)
        compressed_pil = Image.open(buf)
        comp_arr = np.array(compressed_pil, dtype=np.uint8)

        # Compute absolute difference
        diff = cv2.absdiff(orig_arr, comp_arr)

        # Statistical metrics
        mean_err = float(np.mean(diff))
        max_err = int(np.max(diff))
        std_err = float(np.std(diff))
        variance_score = round(float(np.var(diff)), 2)

        # Grid-based compression variance anomaly detection
        h, w, _ = diff.shape
        grid_errors: List[float] = []

        for y in range(0, h, self.BLOCK_SIZE):
            for x in range(0, w, self.BLOCK_SIZE):
                block = diff[y : min(y + self.BLOCK_SIZE, h), x : min(x + self.BLOCK_SIZE, w)]
                if block.size > 0:
                    grid_errors.append(float(np.mean(block)))

        anomaly_count = 0
        if len(grid_errors) > 4:
            median_block = float(np.median(grid_errors))
            std_block = float(np.std(grid_errors))
            if std_block > 0.5:
                # Count blocks with error significantly exceeding surrounding areas
                anomaly_count = sum(1 for err in grid_errors if (err - median_block) > (self.ANOMALY_Z_THRESH * std_block))

        potential_anomalies = anomaly_count >= 3

        # Generate enhanced ELA visual map
        ela_vis = np.clip(diff.astype(np.float32) * self.SCALE_FACTOR, 0, 255).astype(np.uint8)

        # Resize visual map thumbnail for response payload (max 800px on long edge)
        vh, vw, _ = ela_vis.shape
        if max(vh, vw) > 800:
            thumb_scale = 800.0 / max(vh, vw)
            ela_vis = cv2.resize(ela_vis, (int(vw * thumb_scale), int(vh * thumb_scale)), interpolation=cv2.INTER_AREA)

        # Convert to BGR for OpenCV encoding
        ela_vis_bgr = cv2.cvtColor(ela_vis, cv2.COLOR_RGB2BGR)
        _, encoded = cv2.imencode(".jpg", ela_vis_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        ela_b64 = f"data:image/jpeg;base64,{base64.b64encode(encoded).decode('utf-8')}"

        return ELAMetrics(
            mean_error=round(mean_err, 2),
            max_error=max_err,
            std_error=round(std_err, 2),
            variance_score=variance_score,
            quality_tested=quality,
            potential_compression_anomalies=potential_anomalies,
            anomaly_regions_detected=anomaly_count,
            ela_image_base64=ela_b64,
        )


_ela_instance: Optional[ELAAnalyzer] = None

def get_ela_analyzer() -> ELAAnalyzer:
    global _ela_instance
    if _ela_instance is None:
        _ela_instance = ELAAnalyzer()
    return _ela_instance
