"""
ml/inference/claim_verifier.py
Natural Language Inference (NLI) claim verification engine using the DeBERTa-v3 FEVER model.
Performs batched CPU inference over claim-evidence pairs.
"""

from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional
import torch
import torch.nn.functional as F

from backend.app.utils.logger import logger
from ml.inference.model_loader import get_ml_inference_semaphore, get_model_manager
from ml.rag.retriever import EvidenceSentence


@dataclass
class VerifiedEvidence:
    rank: int
    page: str
    sentence_id: int
    doc_id: str
    text: str
    retrieval_similarity: float
    nli_label: str
    nli_confidence: float
    nli_probabilities: Dict[str, float]
    source_type: str = "fever_local"
    source_url: Optional[str] = None
    publication_date: str = "2017-06 (FEVER Wikipedia Corpus)"
    raw_nli_label: str = "NOT ENOUGH INFO"
    evidence_role: str = "contextual"  # supporting, contradicting, contextual
    alignment_notes: str = ""
    retrieval_direction: str = "neutral"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ClaimVerifier:
    """
    Evaluates entailment between an input claim and retrieved evidence sentences.
    Labels:
      0: SUPPORTS
      1: REFUTES
      2: NOT ENOUGH INFO
    """
    def __init__(self):
        self.model_manager = get_model_manager()

    def verify(self, claim: str, evidence_list: List[EvidenceSentence]) -> List[VerifiedEvidence]:
        """
        Runs batched DeBERTa inference on (claim, evidence_sentence) pairs.
        """
        if not evidence_list:
            return []

        clean_claim = claim.strip()
        with get_ml_inference_semaphore():
            model, tokenizer = self.model_manager.get_fever_verifier()

            # Build pairs
            claims = [clean_claim] * len(evidence_list)
            evidences = [ev.text for ev in evidence_list]

            # Batched tokenization (CPU friendly max_length 256)
            inputs = tokenizer(
                claims,
                evidences,
                padding=True,
                truncation=True,
                max_length=256,
                return_tensors="pt"
            )

            with torch.inference_mode():
                outputs = model(**inputs)
                logits = outputs.logits
                probs = F.softmax(logits, dim=-1)

        # Normalize label mapping to integer keys
        id2label = {int(k): v for k, v in model.config.id2label.items()}

        verified_results = []
        for i, ev in enumerate(evidence_list):
            row_probs = probs[i].tolist()
            pred_id = int(torch.argmax(logits[i], dim=-1))
            label = id2label.get(pred_id, "NOT ENOUGH INFO")
            conf = float(row_probs[pred_id])

            prob_dict = {
                "supports": round(float(row_probs[0]), 4),
                "refutes": round(float(row_probs[1]), 4),
                "not_enough_info": round(float(row_probs[2]), 4)
            }

            verified_results.append(
                VerifiedEvidence(
                    rank=ev.rank,
                    page=ev.page,
                    sentence_id=ev.sentence_id,
                    doc_id=ev.doc_id,
                    text=ev.text,
                    retrieval_similarity=ev.similarity_score,
                    nli_label=label,
                    nli_confidence=round(conf, 4),
                    nli_probabilities=prob_dict,
                    source_type=getattr(ev, "source_type", "fever_local"),
                    source_url=getattr(ev, "source_url", None),
                    publication_date=getattr(ev, "publication_date", "2017-06 (FEVER Wikipedia Corpus)"),
                    raw_nli_label=label,
                    retrieval_direction=getattr(ev, "retrieval_direction", "neutral"),
                )
            )

        return verified_results


def get_claim_verifier() -> ClaimVerifier:
    return ClaimVerifier()
