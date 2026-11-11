"""
ml/inference/article_classifier.py
Statistical article-pattern classifier using BERT fine-tuned on the ISOT fake news dataset.
Operates on CPU via ModelManager and provides supplementary classification signals.
"""

from dataclasses import dataclass, asdict, field
from typing import Dict, Any, Optional
import torch
import torch.nn.functional as F

from backend.app.utils.logger import logger
from ml.inference.model_loader import get_ml_inference_semaphore, get_model_manager


@dataclass
class ArticleClassificationResult:
    prediction: str              # "FAKE" or "REAL"
    confidence: float            # Softmax confidence score
    probabilities: Dict[str, float]
    model_name: str
    dataset_origin: str
    distribution_shift_warning: str
    raw_logits: Dict[str, float] = field(default_factory=dict)
    applicable_input_type: str = "full_article"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ArticleClassifier:
    """
    Evaluates news article text for stylistic and lexical patterns characteristic of
    the ISOT benchmark dataset.
    """
    WARNING_MESSAGE = (
        "ISOT dataset warning: This model was evaluated with high test accuracy on the ISOT "
        "benchmark (~99.9%), but exhibits known publisher, subject, and temporal distribution shifts. "
        "Its output represents stylistic similarity to known training distributions, not factual truth verification."
    )

    def __init__(self):
        self.model_manager = get_model_manager()

    def classify(self, text: str, title: Optional[str] = None) -> ArticleClassificationResult:
        full_text = f"{title}. {text}" if title else text
        clean_text = full_text.strip()
        if not clean_text:
            return ArticleClassificationResult(
                prediction="UNKNOWN",
                confidence=0.0,
                probabilities={"fake": 0.5, "real": 0.5},
                model_name="google-bert/bert-base-uncased",
                dataset_origin="ISOT",
                distribution_shift_warning=self.WARNING_MESSAGE,
                raw_logits={},
                applicable_input_type="full_article",
            )

        with get_ml_inference_semaphore():
            model, tokenizer = self.model_manager.get_bert_isot()

            # Tokenize up to 512 tokens
            inputs = tokenizer(
                clean_text,
                return_tensors="pt",
                truncation=True,
                max_length=512,
                padding=True
            )

            with torch.inference_mode():
                outputs = model(**inputs)
                logits = outputs.logits
                raw_logit_vals = logits[0].tolist()
                probs = F.softmax(logits, dim=-1)[0].tolist()

        id2label = {int(k): v for k, v in model.config.id2label.items()}
        pred_id = int(torch.argmax(logits, dim=-1)[0])
        pred_label = id2label.get(pred_id, "FAKE")

        prob_dict = {
            "fake": round(float(probs[0]), 4),
            "real": round(float(probs[1]), 4)
        }
        logit_dict = {
            "fake": round(float(raw_logit_vals[0]), 4),
            "real": round(float(raw_logit_vals[1]), 4),
        }

        return ArticleClassificationResult(
            prediction=pred_label,
            confidence=round(float(probs[pred_id]), 4),
            probabilities=prob_dict,
            model_name="google-bert/bert-base-uncased",
            dataset_origin="ISOT",
            distribution_shift_warning=self.WARNING_MESSAGE,
            raw_logits=logit_dict,
            applicable_input_type="full_article",
        )


def get_article_classifier() -> ArticleClassifier:
    return ArticleClassifier()
