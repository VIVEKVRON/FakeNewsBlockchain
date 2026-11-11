import math
import os
import re
from functools import lru_cache
from pathlib import Path
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_TIMESPAN_PATTERN = re.compile(
    r"^\s*([1-9]\d{0,3})\s*(min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days|w|wk|wks|week|weeks|m|mo|mos|month|months)\s*$",
    re.IGNORECASE,
)

_TIMESPAN_MAX_BY_UNIT = {
    "min": 1440,
    "h": 168,
    "d": 365,
    "w": 52,
    "m": 12,
}


def validate_gdelt_timespan(raw_timespan: str) -> str:
    """
    Validates and normalizes GDELT DOC 2.0 `timespan` values (e.g., `24h`, `3days`, `1week`, `1month`).
    Rejects zero, negative, malformed, oversized, or injection strings before any network call.
    """
    if not isinstance(raw_timespan, str) or not raw_timespan.strip():
        raise ValueError("GDELT timespan must be a non-empty string such as '1week' or '1month'.")
    m = _TIMESPAN_PATTERN.match(raw_timespan.strip())
    if not m:
        raise ValueError(
            f"Invalid GDELT timespan '{raw_timespan}'. Accepted formats: <N><min|h|d|days|w|week|m|month> (e.g., '24h', '3days', '1week', '1month')."
        )
    qty = int(m.group(1))
    unit_raw = m.group(2).lower()
    if unit_raw.startswith("min"):
        max_qty = _TIMESPAN_MAX_BY_UNIT["min"]
    elif unit_raw.startswith("h"):
        max_qty = _TIMESPAN_MAX_BY_UNIT["h"]
    elif unit_raw.startswith("d"):
        max_qty = _TIMESPAN_MAX_BY_UNIT["d"]
    elif unit_raw.startswith("w"):
        max_qty = _TIMESPAN_MAX_BY_UNIT["w"]
    else:
        max_qty = _TIMESPAN_MAX_BY_UNIT["m"]
    if qty > max_qty:
        raise ValueError(f"GDELT timespan '{raw_timespan}' exceeds safe upper bound ({max_qty} {unit_raw}).")
    return f"{qty}{unit_raw}"


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables and .env file.
    Default paths point directly to the audited assets in the Requirements/ folder.
    """
    # Base paths
    PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent
    
    # Server configuration
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    SECRET_KEY: str = "dev-secret-key-fakenews-blockchain-2026"
    
    # Resource & CPU Limits for 16 GB RAM constraint
    TORCH_NUM_THREADS: int = 4
    
    # Machine Learning Models (relative to project root)
    MODEL_FEVER_PATH: str = "Requirements/fever_verifier_v1"
    MODEL_ISOT_PATH: str = "Requirements/bert_isot_temporal_v1"
    MODEL_LIAR_PATH: str = "Requirements/bert_liar_v1/final_model"
    EMBEDDING_MODEL_NAME: str = "sentence-transformers/all-MiniLM-L6-v2"
    
    # Retrieval Knowledge Base (FAISS + Corpus)
    RETRIEVAL_INDEX_PATH: str = "Requirements/wiki_fever.index"
    RETRIEVAL_ROW_MAPPING_PATH: str = "Requirements/row_mapping.jsonl"
    RETRIEVAL_SENTENCES_PATH: str = "Requirements/sentences.jsonl"
    MAX_EVIDENCE_RETRIEVAL_K: int = 5
    
    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///data/database/fakenews.db"
    
    # Multimodal & Uploads
    UPLOAD_DIR: str = "data/uploads"
    MAX_UPLOAD_SIZE_MB: int = 10
    
    # Blockchain (Sepolia & Local Hardhat)
    BLOCKCHAIN_ENABLED: bool = True
    SEPOLIA_RPC_URL: str = ""
    SEPOLIA_PRIVATE_KEY: str = ""
    SEPOLIA_CHAIN_ID: int = 11155111
    CONTRACT_ADDRESS: str = ""
    
    # External News APIs, Public Evidence Fallback & Hard-Capped GDELT Quota (Zero-cost)
    NEWS_API_KEY: str = ""
    GOOGLE_FACT_CHECK_API_KEY: str = ""
    GOOGLE_FACT_CHECK_TIMEOUT_SEC: float = 8.0
    GDELT_ENABLED: bool = True
    GDELT_REQUEST_LIMIT: int = 200
    GDELT_WARNING_THRESHOLD: int = 20
    GDELT_CONNECT_TIMEOUT_SEC: float = 8.0
    GDELT_TIMEOUT_SEC: float = 12.0
    GDELT_MAX_RECORDS: int = 10
    GDELT_MAX_RETRIES: int = 0
    GDELT_DEFAULT_TIMESPAN: str = "1month"
    EXTERNAL_CACHE_TTL_HOURS: int = 24
    WIKIPEDIA_FALLBACK_ENABLED: bool = True
    WIKIPEDIA_TIMEOUT_SEC: float = 8.0

    # Public Verification URL (for certificates, QR codes & external network auditing)
    PUBLIC_VERIFICATION_BASE_URL: str = ""

    @field_validator("GDELT_CONNECT_TIMEOUT_SEC", "GDELT_TIMEOUT_SEC")
    @classmethod
    def validate_gdelt_timeout_values(cls, v: float) -> float:
        if not math.isfinite(v) or v <= 0.0 or v > 60.0:
            raise ValueError("GDELT timeout values must be finite numbers in (0.0, 60.0] seconds.")
        return float(v)

    @field_validator("GDELT_MAX_RETRIES")
    @classmethod
    def validate_gdelt_retries(cls, v: int) -> int:
        if v < 0 or v > 2:
            raise ValueError("GDELT_MAX_RETRIES must be between 0 and 2.")
        return int(v)

    @field_validator("GDELT_DEFAULT_TIMESPAN")
    @classmethod
    def validate_default_timespan_setting(cls, v: str) -> str:
        return validate_gdelt_timespan(v)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    def get_absolute_path(self, relative_or_absolute: str) -> Path:
        """Resolve path relative to project root if not already absolute."""
        p = Path(relative_or_absolute)
        return p if p.is_absolute() else (self.PROJECT_ROOT / p).resolve()


@lru_cache()
def get_settings() -> Settings:
    return Settings()
