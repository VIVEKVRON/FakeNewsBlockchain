"""
ml/inference/claim_extractor.py
Rule-based and heuristic factual claim extraction and ranking from article text.
Extracts salient, verifiable factual propositions rather than subjective commentary.
"""

import re
from dataclasses import dataclass
from typing import List, Optional, Set


@dataclass
class ExtractedCandidateClaim:
    text: str
    relevance_score: float
    sentence_index: int


class ClaimExtractor:
    """
    Extracts and ranks factual claims from full article bodies.
    Prioritizes sentences containing verifiable entities, dates, numbers, and declarative verbs.
    """
    FACTUAL_VERBS = {
        "announced", "confirmed", "stated", "reported", "founded", "cancelled",
        "released", "discovered", "developed", "signed", "launched", "created",
        "died", "born", "awarded", "sentenced", "elected", "passed", "is", "was",
        "features", "starred", "began", "concluded"
    }

    DISCARD_PATTERNS = [
        r"^read more",
        r"^click here",
        r"^subscribe to",
        r"^advertisement",
        r"^photo by",
        r"^source:",
        r"\?$"  # Exclude rhetorical and direct questions
    ]

    def extract_claims(
        self,
        text: str,
        title: Optional[str] = None,
        max_claims: int = 3
    ) -> List[ExtractedCandidateClaim]:
        if not text or not text.strip():
            return []

        # Sentence tokenization using punctuation lookahead
        raw_sentences = [
            s.strip()
            for s in re.split(r"(?<=[.!?])\s+", text)
            if s.strip()
        ]

        title_words = set(re.findall(r"\w+", title.lower())) if title else set()

        candidates = []
        for idx, sentence in enumerate(raw_sentences):
            # Length filter: must be substantive but not a run-on paragraph
            words = re.findall(r"\w+", sentence)
            if len(words) < 6 or len(words) > 50:
                continue

            # Check discard filters
            if any(re.search(pat, sentence, re.IGNORECASE) for pat in self.DISCARD_PATTERNS):
                continue

            # Calculate factual saliency score
            score = 0.0

            # 1. Lead paragraph boost (first 3 sentences)
            if idx < 3:
                score += 1.5 - (idx * 0.3)

            # 2. Number / date presence (years, counts, stats)
            has_numbers = bool(re.search(r"\b\d{1,4}\b", sentence))
            if has_numbers:
                score += 1.2

            # 3. Factual verb presence
            lower_sentence = sentence.lower()
            matched_verbs = sum(1 for v in self.FACTUAL_VERBS if f" {v} " in lower_sentence)
            score += min(2.0, matched_verbs * 0.8)

            # 4. Named entity / Proper noun density (capitalized words not at start)
            non_start_words = sentence.split()[1:]
            capitalized_words = sum(1 for w in non_start_words if w and w[0].isupper() and w.isalpha())
            score += min(2.0, capitalized_words * 0.5)

            # 5. Title relevance overlap
            if title_words:
                sentence_words = set(re.findall(r"\w+", lower_sentence))
                overlap = len(title_words.intersection(sentence_words))
                score += min(2.5, overlap * 0.6)

            candidates.append(
                ExtractedCandidateClaim(
                    text=sentence,
                    relevance_score=round(score, 2),
                    sentence_index=idx
                )
            )

        # Sort by relevance score descending
        candidates.sort(key=lambda c: c.relevance_score, reverse=True)

        # Select top non-redundant claims
        selected = []
        seen_texts: Set[str] = set()

        for c in candidates:
            # Simple substring redundancy filter
            if not any(c.text in s.text or s.text in c.text for s in selected):
                selected.append(c)
                seen_texts.add(c.text)
                if len(selected) >= max(1, min(max_claims, 5)):
                    break

        return selected


def get_claim_extractor() -> ClaimExtractor:
    return ClaimExtractor()
