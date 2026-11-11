"""
backend/tests/test_environment.py
Unit tests for Day 1 Milestone 1 environment, dependencies, and ModelManager scaffolding.
"""

import sys
import pytest
from pathlib import Path

from backend.app.config import get_settings
from ml.inference.model_loader import get_model_manager


def test_python_version():
    """Verify that Python runtime is 3.12."""
    assert sys.version_info.major == 3
    assert sys.version_info.minor == 12


def test_cpu_pytorch():
    """Verify CPU PyTorch and thread control."""
    import torch
    assert not torch.cuda.is_available(), "PyTorch should be CPU-only as specified"
    assert torch.__version__ is not None


def test_heavy_ml_packages_installed():
    """Verify transformers, sentence_transformers, and faiss are properly installed."""
    import transformers
    import sentence_transformers
    import faiss

    assert transformers.__version__ is not None
    assert sentence_transformers.__version__ is not None
    
    # Test FAISS Index creation
    index = faiss.IndexFlatIP(384)
    assert index.d == 384
    assert index.ntotal == 0


def test_settings_asset_paths_exist():
    """Verify all 6 core research assets exist at configured paths."""
    settings = get_settings()

    fever_path = settings.get_absolute_path(settings.MODEL_FEVER_PATH)
    isot_path = settings.get_absolute_path(settings.MODEL_ISOT_PATH)
    liar_path = settings.get_absolute_path(settings.MODEL_LIAR_PATH)
    faiss_path = settings.get_absolute_path(settings.RETRIEVAL_INDEX_PATH)
    row_map_path = settings.get_absolute_path(settings.RETRIEVAL_ROW_MAPPING_PATH)
    sent_path = settings.get_absolute_path(settings.RETRIEVAL_SENTENCES_PATH)

    assert fever_path.is_dir(), f"Missing FEVER dir at {fever_path}"
    assert isot_path.is_dir(), f"Missing ISOT dir at {isot_path}"
    assert liar_path.is_dir(), f"Missing LIAR dir at {liar_path}"
    assert faiss_path.is_file(), f"Missing FAISS index at {faiss_path}"
    assert row_map_path.is_file(), f"Missing row mapping at {row_map_path}"
    assert sent_path.is_file(), f"Missing sentences corpus at {sent_path}"


def test_model_manager_scaffolding():
    """Verify ModelManager singleton initialization and thread limit enforcement."""
    model_mgr = get_model_manager()
    status = model_mgr.status()

    assert status["device"] == "cpu"
    assert status["torch_threads"] == 4
    # Verify status report dictionary contains all model keys with boolean states
    assert isinstance(status["models_loaded"], dict)
    for model_key in ["fever_verifier", "bert_isot", "bert_liar", "sentence_transformer"]:
        assert model_key in status["models_loaded"]
        assert isinstance(status["models_loaded"][model_key], bool)
