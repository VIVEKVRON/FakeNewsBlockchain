from contextlib import asynccontextmanager
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.config import get_settings
from backend.app.utils.logger import logger
from ml.inference.model_loader import get_model_manager
from backend.app.api.routes import verify, image, news, blockchain, history, certificates


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    settings = get_settings()
    logger.info(f"Starting FakeNewsBlockchain Backend in [{settings.ENVIRONMENT}] mode.")
    logger.info(f"Project root: {settings.PROJECT_ROOT}")
    
    # Initialize ModelManager singleton
    model_mgr = get_model_manager()
    logger.info(f"ModelManager status: {model_mgr.status()}")

    # Initialize SQLite database schema and seed Sepolia record
    from backend.app.database.connection import init_db
    from backend.app.database.repository import seed_confirmed_sepolia_record_if_empty
    from backend.app.services.external_apis.gdelt_usage_tracker import GdeltUsageTracker
    init_db()
    seed_confirmed_sepolia_record_if_empty()
    GdeltUsageTracker().ensure_schema()
    
    yield
    
    logger.info("Shutting down FakeNewsBlockchain Backend.")


settings = get_settings()

app = FastAPI(
    title="FakeNewsBlockchain API",
    description="Real-Time Multimodal Fake News Detection & Fact Verification API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Cross-Origin Resource Sharing (CORS) for React Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Register API Routers
app.include_router(verify.router, prefix="/api/v1")
app.include_router(image.router, prefix="/api/v1")
app.include_router(news.router, prefix="/api/v1")
app.include_router(blockchain.router, prefix="/api/v1")
app.include_router(history.router, prefix="/api/v1")
app.include_router(certificates.router, prefix="/api/v1")


@app.get("/", tags=["Root"])
async def root():
    return {
        "project": "FakeNewsBlockchain",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "health": "/api/v1/health"
    }


@app.get("/api/v1/health", tags=["System"])
async def health():
    """System health check and runtime model diagnostics."""
    model_mgr = get_model_manager()
    status_info = model_mgr.status()
    
    # Verify that asset paths exist on disk
    fever_exists = settings.get_absolute_path(settings.MODEL_FEVER_PATH).exists()
    isot_exists = settings.get_absolute_path(settings.MODEL_ISOT_PATH).exists()
    liar_exists = settings.get_absolute_path(settings.MODEL_LIAR_PATH).exists()
    index_exists = settings.get_absolute_path(settings.RETRIEVAL_INDEX_PATH).exists()

    return {
        "status": "healthy",
        "version": "1.0.0",
        "environment": settings.ENVIRONMENT,
        "runtime": {
            "device": status_info["device"],
            "torch_threads": status_info["torch_threads"],
            "models_loaded": status_info["models_loaded"]
        },
        "asset_paths_verified": {
            "fever_verifier": fever_exists,
            "bert_isot": isot_exists,
            "bert_liar": liar_exists,
            "faiss_index": index_exists
        }
    }
