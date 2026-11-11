"""
ml/inference/model_loader.py
Centralized ModelManager singleton providing lazy-loaded, CPU-optimized inference.
Strictly respects 16 GB RAM constraints by limiting threads and loading on-demand.
"""

import threading
from typing import Dict, Any, Optional, Tuple
from pathlib import Path

from backend.app.config import get_settings
from backend.app.utils.logger import logger

# Lazy imports for heavy ML packages to allow fast module import
torch = None
AutoTokenizer = None
AutoModelForSequenceClassification = None
SentenceTransformer = None
_TORCH_INIT_LOCK = threading.Lock()
# Cap concurrent PyTorch/DeBERTa CPU inference executions to protect the 16 GB RAM budget
# and prevent OpenMP thread oversubscription without ever holding locks during network I/O.
_ML_INFERENCE_SEMAPHORE = threading.BoundedSemaphore(value=1)


def get_ml_inference_semaphore() -> threading.BoundedSemaphore:
    """Returns shared bounded semaphore gating simultaneous CPU ML forward passes."""
    return _ML_INFERENCE_SEMAPHORE


def _ensure_torch_configured():
    """Initializes PyTorch with CPU thread limits (thread-safe)."""
    global torch
    if torch is None:
        with _TORCH_INIT_LOCK:
            if torch is None:
                import torch as _torch
                torch = _torch
                settings = get_settings()
                # Cap CPU threads to prevent thread starvation and high memory spikes
                torch.set_num_threads(settings.TORCH_NUM_THREADS)
                try:
                    torch.set_num_interop_threads(1)
                except RuntimeError:
                    pass  # Already initialized in current process
                logger.info(f"PyTorch initialized on CPU (threads={settings.TORCH_NUM_THREADS}, interop=1)")


class ModelManager:
    """
    Singleton class managing the lifecycle and memory of all AI models.
    Models are loaded lazily upon first request, kept in RAM, and run in eval mode.
    """
    _instance: Optional["ModelManager"] = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(ModelManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        
        self.settings = get_settings()
        self._device = "cpu"
        
        # Internal model containers
        self._fever_model = None
        self._fever_tokenizer = None
        
        self._isot_model = None
        self._isot_tokenizer = None
        
        self._liar_model = None
        self._liar_tokenizer = None
        
        self._embedding_model = None
        
        # Locks for individual model loading
        self._fever_lock = threading.Lock()
        self._isot_lock = threading.Lock()
        self._liar_lock = threading.Lock()
        self._embedding_lock = threading.Lock()
        
        self._initialized = True
        logger.info("ModelManager singleton initialized (lazy loading ready).")

    @property
    def device(self) -> str:
        return self._device

    def get_fever_verifier(self) -> Tuple[Any, Any]:
        """
        Retrieves (model, tokenizer) for the DeBERTa FEVER verifier.
        Labels: 0 -> SUPPORTS, 1 -> REFUTES, 2 -> NOT ENOUGH INFO
        """
        if self._fever_model is None:
            with self._fever_lock:
                if self._fever_model is None:
                    _ensure_torch_configured()
                    global AutoTokenizer, AutoModelForSequenceClassification
                    if AutoTokenizer is None:
                        from transformers import AutoTokenizer, AutoModelForSequenceClassification

                    path = str(self.settings.get_absolute_path(self.settings.MODEL_FEVER_PATH))
                    logger.info(f"Loading DeBERTa FEVER Verifier from: {path}")
                    
                    tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True)
                    model = AutoModelForSequenceClassification.from_pretrained(
                        path,
                        local_files_only=True,
                        torch_dtype=torch.float32
                    )
                    model.eval()
                    for param in model.parameters():
                        param.requires_grad = False
                    
                    self._fever_tokenizer = tokenizer
                    self._fever_model = model
                    logger.info("DeBERTa FEVER Verifier successfully loaded on CPU.")
                    
        return self._fever_model, self._fever_tokenizer

    def get_bert_isot(self) -> Tuple[Any, Any]:
        """
        Retrieves (model, tokenizer) for the BERT ISOT article classifier.
        Labels: 0 -> FAKE, 1 -> REAL
        """
        if self._isot_model is None:
            with self._isot_lock:
                if self._isot_model is None:
                    _ensure_torch_configured()
                    global AutoTokenizer, AutoModelForSequenceClassification
                    if AutoTokenizer is None:
                        from transformers import AutoTokenizer, AutoModelForSequenceClassification

                    path = str(self.settings.get_absolute_path(self.settings.MODEL_ISOT_PATH))
                    logger.info(f"Loading BERT ISOT Classifier from: {path}")
                    
                    tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True)
                    model = AutoModelForSequenceClassification.from_pretrained(
                        path,
                        local_files_only=True,
                        torch_dtype=torch.float32
                    )
                    model.eval()
                    for param in model.parameters():
                        param.requires_grad = False
                    
                    self._isot_tokenizer = tokenizer
                    self._isot_model = model
                    logger.info("BERT ISOT Classifier successfully loaded on CPU.")
                    
        return self._isot_model, self._isot_tokenizer

    def get_bert_liar(self) -> Tuple[Any, Any]:
        """
        Retrieves (model, tokenizer) for the BERT LIAR claim classifier.
        Labels: 0 -> pants-fire, 1 -> false, 2 -> barely-true, 3 -> half-true, 4 -> mostly-true, 5 -> true
        """
        if self._liar_model is None:
            with self._liar_lock:
                if self._liar_model is None:
                    _ensure_torch_configured()
                    global AutoTokenizer, AutoModelForSequenceClassification
                    if AutoTokenizer is None:
                        from transformers import AutoTokenizer, AutoModelForSequenceClassification

                    path = str(self.settings.get_absolute_path(self.settings.MODEL_LIAR_PATH))
                    logger.info(f"Loading BERT LIAR Classifier from: {path}")
                    
                    tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True)
                    model = AutoModelForSequenceClassification.from_pretrained(
                        path,
                        local_files_only=True,
                        torch_dtype=torch.float32
                    )
                    model.eval()
                    for param in model.parameters():
                        param.requires_grad = False
                    
                    self._liar_tokenizer = tokenizer
                    self._liar_model = model
                    logger.info("BERT LIAR Classifier successfully loaded on CPU.")
                    
        return self._liar_model, self._liar_tokenizer

    def get_embedding_model(self) -> Any:
        """
        Retrieves the SentenceTransformer embedding model for RAG queries.
        Produces 384-dimensional normalized vectors.
        """
        if self._embedding_model is None:
            with self._embedding_lock:
                if self._embedding_model is None:
                    _ensure_torch_configured()
                    global SentenceTransformer
                    if SentenceTransformer is None:
                        from sentence_transformers import SentenceTransformer

                    model_name = self.settings.EMBEDDING_MODEL_NAME
                    logger.info(f"Loading SentenceTransformer: {model_name} on CPU")
                    try:
                        model = SentenceTransformer(model_name, device="cpu", local_files_only=True)
                    except Exception:
                        logger.info(f"Local cache miss for {model_name}; attempting Hub load.")
                        model = SentenceTransformer(model_name, device="cpu")
                    self._embedding_model = model
                    logger.info("SentenceTransformer successfully loaded.")
                    
        return self._embedding_model

    def status(self) -> Dict[str, Any]:
        """Returns the current runtime and memory status of models."""
        _ensure_torch_configured()
        threads = torch.get_num_threads() if torch else None
        
        return {
            "device": self._device,
            "torch_threads": threads,
            "models_loaded": {
                "fever_verifier": self._fever_model is not None,
                "bert_isot": self._isot_model is not None,
                "bert_liar": self._liar_model is not None,
                "sentence_transformer": self._embedding_model is not None
            }
        }


# Global singleton helper
def get_model_manager() -> ModelManager:
    return ModelManager()
