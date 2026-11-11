"""
ml/inference/claim_classifier.py
Experimental 6-way claim classification using BERT fine-tuned on the LIAR dataset.
Provides supplementary linguistic signals for claims.
"""

from dataclasses import dataclass, asdict, field
from typing import Dict, Any
import torch
import torch.nn.functional as F

from backend.app.utils.logger import logger
from ml.inference.model_loader import get_ml_inference_semaphore, get_model_manager


@dataclass
class ClaimClassificationResult:
    prediction: str              # pants-fire, false, barely-true, half-true, mostly-true, true
    confidence: float            # Softmax probability for top label
    probabilities: Dict[str, float]
    model_name: str
    dataset_origin: str
    disclaimer: str
    raw_logits: Dict[str, float] = field(default_factory=dict)
    applicable_input_type: str = "short_claim"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ClaimClassifier:
    """
    Evaluates claims across the 6 LIAR benchmark truthfulness grades.
    """
    DISCLAIMER_MESSAGE = (
        "LIAR dataset note: The LIAR baseline model achieves ~26.84% multi-class accuracy. "
        "Its softmax distribution provides an exploratory linguistic pattern signal and must "
        "not be interpreted as the literal probability that a statement is true."
    )

    def __init__(self):
        self.model_manager = get_model_manager()

    def classify(self, claim: str) -> ClaimClassificationResult:
        clean_claim = claim.strip()
        if not clean_claim:
            return ClaimClassificationResult(
                prediction="unverified",
                confidence=0.0,
                probabilities={},
                model_name="bert-base-uncased",
                dataset_origin="LIAR",
                disclaimer=self.DISCLAIMER_MESSAGE,
                raw_logits={},
                applicable_input_type="short_claim",
            )

        with get_ml_inference_semaphore():
            model, tokenizer = self.model_manager.get_bert_liar()

            inputs = tokenizer(
                clean_claim,
                return_tensors="pt",
                truncation=True,
                max_length=128,
                padding=True
            )

            with torch.inference_mode():
                outputs = model(**inputs)
                logits = outputs.logits
                raw_logit_vals = logits[0].tolist()
                probs = F.softmax(logits, dim=-1)[0].tolist()

        id2label = {int(k): v for k, v in model.config.id2label.items()}
        pred_id = int(torch.argmax(logits, dim=-1)[0])
        pred_label = id2label.get(pred_id, "half-true")

        prob_dict = {
            id2label[i]: round(float(p), 4)
            for i, p in enumerate(probs)
        }
        logit_dict = {
            id2label[i]: round(float(lv), 4)
            for i, lv in enumerate(raw_logit_vals)
        }

        return ClaimClassificationResult(
            prediction=pred_label,
            confidence=round(float(probs[pred_id]), 4),
            probabilities=prob_dict,
            model_name="bert-base-uncased",
            dataset_origin="LIAR",
            disclaimer=self.DISCLAIMER_MESSAGE,
            raw_logits=logit_dict,
            applicable_input_type="short_claim",
        )


def get_claim_classifier() -> ClaimClassifier:
    return ClaimClassifier()
