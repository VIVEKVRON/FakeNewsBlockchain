"""
ml/rag/retriever.py
Evidence retrieval engine using FAISS IndexFlatIP and sentence-transformers/all-MiniLM-L6-v2.
Maintains high performance on 16 GB RAM through in-memory byte offset indexing.
"""

import json
import os
import re
import threading
import urllib.parse
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import faiss
import numpy as np

from backend.app.config import get_settings
from backend.app.utils.logger import logger
from ml.inference.model_loader import get_ml_inference_semaphore, get_model_manager


FEVER_SNAPSHOT_DATE = "2017-06 (FEVER Wikipedia Corpus)"


def clean_wikipedia_text(text: str) -> str:
    """Normalizes FEVER Penn-Treebank bracket tokens and spaced punctuation for clean inference/display."""
    if not text:
        return ""
    cleaned = (
        text.replace("-LRB-", "(")
        .replace("-RRB-", ")")
        .replace("-LSB-", "[")
        .replace("-RSB-", "]")
        .replace("-LCB-", "{")
        .replace("-RCB-", "}")
        .replace("`` ", "\"")
        .replace(" ''", "\"")
    )
    cleaned = re.sub(r"\s+([,.;:?!%)])", r"\1", cleaned)
    cleaned = re.sub(r"([(])\s+", r"\1", cleaned)
    cleaned = re.sub(r"\s+'s\b", "'s", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


@dataclass
class EvidenceSentence:
    rank: int
    row_id: int
    doc_id: str
    page: str
    sentence_id: int
    text: str
    similarity_score: float
    source_type: str = "fever_local"
    source_url: Optional[str] = None
    publication_date: str = FEVER_SNAPSHOT_DATE
    retrieval_direction: str = "neutral"

    def to_dict(self):
        return asdict(self)


class FAISSRetriever:
    """
    Singleton retriever for querying 126,000 FEVER Wikipedia sentences
    using the pre-built 384-dimensional FAISS IndexFlatIP index.
    """
    _instance: Optional["FAISSRetriever"] = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(FAISSRetriever, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        self.settings = get_settings()
        self.model_manager = get_model_manager()
        
        # Paths
        self.index_path = str(self.settings.get_absolute_path(self.settings.RETRIEVAL_INDEX_PATH))
        self.sentences_path = str(self.settings.get_absolute_path(self.settings.RETRIEVAL_SENTENCES_PATH))
        
        # Load FAISS index
        logger.info(f"Loading FAISS index from: {self.index_path}")
        self.index = faiss.read_index(self.index_path)
        logger.info(f"FAISS index loaded. Total vectors: {self.index.ntotal:,}, Dimension: {self.index.d}")

        # Build in-memory line byte offsets for fast random access (< 1MB RAM footprint)
        self._offsets = []
        self._build_offset_index()
        
        self._initialized = True
        logger.info("FAISSRetriever initialized and ready for queries.")

    def _build_offset_index(self):
        """Builds a fast byte-offset lookup for sentences.jsonl without reading full text into RAM."""
        logger.info(f"Building byte-offset index for {self.sentences_path}...")
        pos = 0
        offsets = []
        with open(self.sentences_path, "rb") as f:
            for line in f:
                offsets.append(pos)
                pos += len(line)
        self._offsets = offsets
        logger.info(f"Offset index ready with {len(self._offsets):,} entries.")

    def get_sentence_by_row(self, row_idx: int) -> dict:
        """Seek and parse a single sentence JSON line using its byte offset."""
        if row_idx < 0 or row_idx >= len(self._offsets):
            raise IndexError(f"Row index {row_idx} out of bounds (0..{len(self._offsets)-1})")
        
        with open(self.sentences_path, "r", encoding="utf-8") as f:
            f.seek(self._offsets[row_idx])
            line = f.readline()
            return json.loads(line)

    def retrieve(self, query: str, top_k: int = 5) -> List[EvidenceSentence]:
        """
        Embed query using all-MiniLM-L6-v2 and retrieve top_k nearest sentences.
        Inner Product on unit-normalized vectors equals Cosine Similarity.
        """
        clean_query = query.strip()
        if not clean_query:
            return []

        # Bound top_k safely between 1 and 20
        k = max(1, min(top_k, 20))

        # Get embedding model from singleton & run CPU embedding/FAISS search under inference cap
        with get_ml_inference_semaphore():
            embedder = self.model_manager.get_embedding_model()

            # Encode with unit normalization
            query_vector = embedder.encode(
                [clean_query],
                convert_to_numpy=True,
                normalize_embeddings=True
            )

            # Search FAISS index
            distances, indices = self.index.search(query_vector, k)

        results = []
        for rank, (row_id, dist) in enumerate(zip(indices[0], distances[0]), 1):
            if row_id < 0:
                continue
            
            raw_record = self.get_sentence_by_row(int(row_id))

            raw_page = raw_record.get("page", "")
            page_title = clean_wikipedia_text(raw_page.replace("_", " "))
            cleaned_text = clean_wikipedia_text(raw_record.get("text", ""))
            source_url = f"https://en.wikipedia.org/wiki/{urllib.parse.quote(raw_page)}" if raw_page else None

            evidence = EvidenceSentence(
                rank=rank,
                row_id=int(row_id),
                doc_id=raw_record.get("doc_id", ""),
                page=page_title,
                sentence_id=raw_record.get("sentence_id", 0),
                text=cleaned_text,
                similarity_score=round(float(dist), 4),
                source_type="fever_local",
                source_url=source_url,
                publication_date=FEVER_SNAPSHOT_DATE
            )
            results.append(evidence)

        return results

    @staticmethod
    def _needs_wikipedia_fallback(query: str, local_results: List[EvidenceSentence]) -> Tuple[bool, str]:
        """
        Determines whether public MediaWiki fallback should augment local 2017 FEVER FAISS results.
        """
        if not local_results:
            return True, "no_local_results"

        top_sim = local_results[0].similarity_score
        if top_sim < 0.62:
            return True, f"low_local_similarity({top_sim:.2f})"

        q_lower = query.lower()
        temporal_or_post2017 = re.search(
            r"\b(current|currently|incumbent|today|now|presently|rebranded|sitting|reigning|"
            r"remains|unrenamed|parent|ceo|cm|pm|chief minister|prime minister|president|"
            r"chancellor|king|queen|monarch|secretary[\s-]+general|champion|20(?:1[8-9]|2[0-9]|3[0-9]))\b",
            q_lower
        )
        if temporal_or_post2017:
            return True, "temporal_or_office_claim"

        # Check if proper-noun entities from claim appear in retrieved local evidence
        words = re.findall(r"[A-Za-z0-9]+", query)
        proper_tokens = {
            w.lower() for i, w in enumerate(words)
            if len(w) >= 4 and w[0].isupper() and (i > 0 or w.lower() not in {
                "this", "that", "there", "these", "all", "only", "over", "pure",
                "healthy", "three", "two", "four", "five", "amateur", "confidential", "leaked"
            })
        }
        if proper_tokens:
            combined_local = " ".join(f"{ev.page} {ev.text}" for ev in local_results).lower()
            missing_entities = [t for t in proper_tokens if t not in combined_local]
            if missing_entities:
                return True, f"missing_entities({','.join(missing_entities[:3])})"

        # Check subject-noun & sweeping-quantifier coverage on local FEVER pages (e.g. "All penguin species... Antarctic" -> Antarctica != penguin)
        generic_subject_stop = {
            "all", "only", "every", "some", "many", "most", "pure", "healthy", "the", "this",
            "that", "these", "those", "with", "from", "into", "inside", "during", "across",
            "species", "human", "beings", "people", "percent", "degrees"
        }
        lc_words = [w.lower() for w in re.findall(r"[A-Za-z]+", query)]
        head_topic_nouns = [w for w in lc_words[:5] if len(w) >= 5 and w not in generic_subject_stop]
        if head_topic_nouns:
            stem_head = head_topic_nouns[0].rstrip("s")
            local_pages_joined = " ".join(ev.page.lower() for ev in local_results)
            if stem_head not in local_pages_joined and top_sim < 0.78:
                return True, f"subject_page_absent({stem_head})"

        if re.search(r"\b(all|only|sole|exclusively|always|never|100|boils|cure|cures|awarded|ceremony)\b", q_lower) and top_sim < 0.85:
            return True, "sweeping_or_quantitative_claim"

        return False, "local_sufficient"

    def retrieve_hybrid(self, query: str, top_k: int = 5) -> Tuple[List[EvidenceSentence], Dict[str, Any]]:
        """
        Primary retrieval entrypoint implementing Option B:
          1. Queries local 126k FEVER FAISS index.
          2. Conditionally augments with free public Wikipedia MediaWiki API when local coverage is weak,
             entity-missing, or temporally sensitive/post-2017.
          3. Returns merged top_k EvidenceSentence items + provenance metadata.
        """
        k = max(1, min(top_k, 20))
        # Retrieve a wider candidate pool internally so unrelated top keyword matches don't crowd out the true subject page
        pool_k = max(k, 10)
        local_pool = self.retrieve(query, top_k=pool_k)

        # Boost local sentences whose page or text matches proper entities in query before trimming to top_k
        q_words = re.findall(r"[A-Za-z0-9]+", query)
        proper_tokens = {
            w.lower() for i, w in enumerate(q_words)
            if len(w) >= 4 and w[0].isupper() and w.lower() not in {"however", "although", "meanwhile", "this", "that"}
        }
        if proper_tokens and local_pool:
            def _entity_boost(ev: EvidenceSentence) -> float:
                combined = f"{ev.page} {ev.text}".lower()
                hits = sum(1 for t in proper_tokens if t in combined)
                return ev.similarity_score + (0.06 * hits)
            local_pool.sort(key=_entity_boost, reverse=True)

        local_results = local_pool[:k]
        for idx, item in enumerate(local_results, 1):
            item.rank = idx

        should_fallback, trigger_reason = self._needs_wikipedia_fallback(query, local_results)

        meta: Dict[str, Any] = {
            "wikipedia_fallback_triggered": False,
            "trigger_reason": trigger_reason,
            "wikipedia_status": "not_needed",
            "local_count": len(local_results),
            "live_count": 0,
        }

        if not should_fallback or not getattr(self.settings, "WIKIPEDIA_FALLBACK_ENABLED", True):
            if not getattr(self.settings, "WIKIPEDIA_FALLBACK_ENABLED", True):
                meta["wikipedia_status"] = "disabled"
            return local_results, meta

        try:
            from ml.rag.wikipedia_fallback import get_wikipedia_fallback
            wiki_client = get_wikipedia_fallback()
            if hasattr(wiki_client, "retrieve_with_status"):
                wiki_res = wiki_client.retrieve_with_status(query, top_k=max(k, 5))
                wiki_hits = wiki_res.hits
                wiki_status = wiki_res.status
            else:
                wiki_hits = wiki_client.retrieve(query, top_k=max(k, 5))
                wiki_status = getattr(wiki_client, "last_status", "ok" if wiki_hits else "no_results")
            meta["wikipedia_fallback_triggered"] = True
            meta["wikipedia_status"] = wiki_status
            meta["live_count"] = len(wiki_hits)

            if not wiki_hits:
                return local_results, meta

            merged: List[EvidenceSentence] = list(local_results)
            seen_texts = {re.sub(r"\W+", "", ev.text.lower())[:90] for ev in local_results}

            for hit in wiki_hits:
                norm_key = re.sub(r"\W+", "", hit.text.lower())[:90]
                if norm_key in seen_texts:
                    continue
                seen_texts.add(norm_key)
                merged.append(
                    EvidenceSentence(
                        rank=0,
                        row_id=-1,
                        doc_id=hit.doc_id,
                        page=hit.page,
                        sentence_id=hit.sentence_id,
                        text=hit.text,
                        similarity_score=hit.similarity_score,
                        source_type="wikipedia_live",
                        source_url=hit.source_url,
                        publication_date=hit.publication_date,
                    )
                )

            # Prioritize fresher live Wikipedia on temporal/office claims and preserve top relevant live hits
            is_temporal = trigger_reason == "temporal_or_office_claim"
            merged.sort(
                key=lambda x: (
                    x.similarity_score + (0.04 if (is_temporal and x.source_type == "wikipedia_live") else (0.015 if x.source_type == "wikipedia_live" else 0.0))
                ),
                reverse=True
            )
            limit_k = max(k, 5)
            top_merged = merged[:max(k, 6)]
            # Ensure up to 2 high-scoring live hits aren't crowded out of final results
            final_hits = list(top_merged[:limit_k])
            live_extras = [m for m in merged if m.source_type == "wikipedia_live" and m not in final_hits and m.similarity_score >= 0.45]
            if live_extras and sum(1 for h in final_hits if h.source_type == "wikipedia_live") < 2:
                # Replace lowest-scoring local tail slots if live Wikipedia provides relevant fresher/venue context
                live_margin = 0.12 if trigger_reason in ("sweeping_or_quantitative_claim", "temporal_or_office_claim") else 0.05
                for extra in live_extras[:2]:
                    local_tail = [h for h in final_hits if h.source_type == "fever_local"]
                    if local_tail and extra.similarity_score + live_margin >= local_tail[-1].similarity_score:
                        final_hits.remove(local_tail[-1])
                        final_hits.append(extra)
                final_hits.sort(
                    key=lambda x: x.similarity_score + (0.04 if (is_temporal and x.source_type == "wikipedia_live") else 0.0),
                    reverse=True,
                )

            for idx, item in enumerate(final_hits, 1):
                item.rank = idx

            return final_hits, meta
        except Exception as exc:
            logger.warning(f"Wikipedia hybrid fallback error ({exc}); returning local FEVER results only.")
            meta["wikipedia_fallback_triggered"] = True
            meta["wikipedia_status"] = "error_fallback"
            return local_results, meta

    def retrieve_independent(
        self,
        claim: str,
        directional_queries: Dict[str, str],
        top_k: int = 5,
    ) -> Tuple[List[EvidenceSentence], Dict[str, Any]]:
        """
        Prediction-independent bidirectional retrieval for IEVE.
        Runs support-oriented, contradiction-oriented, and neutral queries on local FEVER FAISS
        and conditionally augments with directional Wikipedia queries without ever taking
        any initial ML prediction as a filter.
        """
        k = max(1, min(top_k, 20))
        pool_k = max(k, 8)
        dir_label_map = {
            "support": "support_oriented",
            "contradict": "contradiction_oriented",
            "neutral": "neutral",
        }
        ordered_dirs: List[Tuple[str, str]] = []
        seen_q_texts = set()
        for key in ("support", "contradict", "neutral"):
            q_val = (directional_queries.get(key) or "").strip()
            if q_val and q_val.lower() not in seen_q_texts:
                seen_q_texts.add(q_val.lower())
                ordered_dirs.append((dir_label_map[key], q_val))
        if not ordered_dirs and claim.strip():
            ordered_dirs.append(("neutral", claim.strip()))

        merged_local: Dict[Tuple[str, int, str], EvidenceSentence] = {}
        if ordered_dirs:
            texts = [q for _, q in ordered_dirs]
            with get_ml_inference_semaphore():
                embedder = self.model_manager.get_embedding_model()
                q_vecs = embedder.encode(
                    texts,
                    convert_to_numpy=True,
                    normalize_embeddings=True,
                )
                distances_all, indices_all = self.index.search(q_vecs, pool_k)

            for dir_idx, (dir_tag, _) in enumerate(ordered_dirs):
                for row_id, dist in zip(indices_all[dir_idx], distances_all[dir_idx]):
                    if row_id < 0:
                        continue
                    raw_record = self.get_sentence_by_row(int(row_id))
                    raw_page = raw_record.get("page", "")
                    page_title = clean_wikipedia_text(raw_page.replace("_", " "))
                    cleaned_text = clean_wikipedia_text(raw_record.get("text", ""))
                    if not cleaned_text:
                        continue
                    doc_id = raw_record.get("doc_id", "")
                    sent_id = int(raw_record.get("sentence_id", 0))
                    dedup_key = (page_title.lower(), sent_id, cleaned_text[:80].lower())
                    sim = round(float(dist), 4)
                    if dedup_key not in merged_local or sim > merged_local[dedup_key].similarity_score:
                        source_url = f"https://en.wikipedia.org/wiki/{urllib.parse.quote(raw_page)}" if raw_page else None
                        merged_local[dedup_key] = EvidenceSentence(
                            rank=0,
                            row_id=int(row_id),
                            doc_id=doc_id,
                            page=page_title,
                            sentence_id=sent_id,
                            text=cleaned_text,
                            similarity_score=sim,
                            source_type="fever_local",
                            source_url=source_url,
                            publication_date=FEVER_SNAPSHOT_DATE,
                            retrieval_direction=dir_tag,
                        )

        local_pool = list(merged_local.values())
        q_words = re.findall(r"[A-Za-z0-9]+", claim)
        proper_tokens = {
            w.lower() for i, w in enumerate(q_words)
            if len(w) >= 4 and w[0].isupper() and w.lower() not in {"however", "although", "meanwhile", "this", "that"}
        }
        if proper_tokens and local_pool:
            local_pool.sort(
                key=lambda ev: ev.similarity_score + (0.06 * sum(1 for t in proper_tokens if t in f"{ev.page} {ev.text}".lower())),
                reverse=True,
            )
        else:
            local_pool.sort(key=lambda ev: ev.similarity_score, reverse=True)

        # Keep balanced representation so contradiction-oriented local hits are preserved even when support dominates similarity
        local_cap = max(k + 3, 8)
        local_results = list(local_pool[:local_cap])
        contra_extras = [ev for ev in local_pool[local_cap:] if ev.retrieval_direction == "contradiction_oriented"][:2]
        local_results.extend(contra_extras)
        for idx, item in enumerate(local_results, 1):
            item.rank = idx

        should_fallback, trigger_reason = self._needs_wikipedia_fallback(claim, local_results)
        local_attempts: List[Dict[str, Any]] = []
        for dir_tag, q_str in ordered_dirs:
            cnt = sum(1 for ev in merged_local.values() if ev.retrieval_direction == dir_tag)
            local_attempts.append(
                {
                    "provider": "fever_local",
                    "direction": dir_tag,
                    "query": q_str,
                    "outcome": "success_with_results" if cnt > 0 else "no_results",
                    "available": True,
                    "from_cache": False,
                    "items_retrieved": cnt,
                    "reason": "local_faiss_126k_search",
                }
            )

        meta: Dict[str, Any] = {
            "wikipedia_fallback_triggered": False,
            "trigger_reason": trigger_reason,
            "wikipedia_status": "not_needed",
            "local_count": len(local_results),
            "live_count": 0,
            "directions_executed": ["support", "contradict", "neutral"],
            "local_attempts": local_attempts,
        }

        if not should_fallback or not getattr(self.settings, "WIKIPEDIA_FALLBACK_ENABLED", True):
            if not getattr(self.settings, "WIKIPEDIA_FALLBACK_ENABLED", True):
                meta["wikipedia_status"] = "disabled"
            local_attempts.append(
                {
                    "provider": "wikipedia_live",
                    "direction": "support_oriented",
                    "query": claim.strip(),
                    "outcome": "skipped_by_policy",
                    "available": meta["wikipedia_status"] != "disabled",
                    "from_cache": False,
                    "items_retrieved": 0,
                    "reason": "wikipedia_disabled" if meta["wikipedia_status"] == "disabled" else f"not_triggered ({trigger_reason})",
                }
            )
            return local_results[:max(k, 8)], meta

        def _map_wiki_outcome(w_status: str, hits_cnt: int, from_cache: bool = False) -> Tuple[str, bool]:
            if w_status in ("cache_hit", "ok_cached") or (from_cache and w_status in ("ok", "ok_cached", "cache_hit")):
                return "cache_hit", True
            if w_status == "timeout":
                return "timeout", False
            if w_status in ("offline", "error_fallback", "blocked_domain"):
                return "network_error", False
            if w_status in ("disabled", "not_needed"):
                return "skipped_by_policy", w_status != "disabled"
            if hits_cnt > 0:
                return "success_with_results", True
            return "no_results", True

        def _call_wiki(q_text: str, k_limit: int) -> Tuple[List[Any], str, bool, str]:
            if hasattr(wiki_client, "retrieve_with_status"):
                w_res = wiki_client.retrieve_with_status(q_text, top_k=k_limit)
                reason_bits = [
                    f"{o.get('query', '')}:{o.get('status', '')}"
                    for o in getattr(w_res, "query_outcomes", [])
                    if o.get("status")
                ]
                reason_str = w_res.status if not reason_bits else f"{w_res.status} ({'; '.join(reason_bits)})"
                return list(w_res.hits), str(w_res.status), bool(w_res.from_cache), reason_str
            hits_raw = list(wiki_client.retrieve(q_text, top_k=k_limit))
            st = str(getattr(wiki_client, "last_status", "ok" if hits_raw else "no_results"))
            return hits_raw, st, st in ("cache_hit", "ok_cached"), st

        try:
            from ml.rag.wikipedia_fallback import get_wikipedia_fallback
            wiki_client = get_wikipedia_fallback()
            # Retrieve both primary claim context and contradiction-oriented context via cached MediaWiki client
            wiki_hits_sup, status_sup, sup_cached, sup_reason = _call_wiki(claim, max(k, 5))
            sup_out, sup_avail = _map_wiki_outcome(status_sup, len(wiki_hits_sup), from_cache=sup_cached)
            local_attempts.append(
                {
                    "provider": "wikipedia_live",
                    "direction": "support_oriented",
                    "query": claim.strip(),
                    "outcome": sup_out,
                    "available": sup_avail,
                    "from_cache": sup_cached or sup_out == "cache_hit",
                    "items_retrieved": len(wiki_hits_sup),
                    "reason": sup_reason,
                }
            )
            contra_q = (directional_queries.get("contradict") or "").strip()
            wiki_hits_con = []
            status_con = status_sup
            con_cached = False
            if contra_q and contra_q.lower() != claim.strip().lower():
                wiki_hits_con, status_con, con_cached, con_reason = _call_wiki(contra_q, 3)
                con_out, con_avail = _map_wiki_outcome(status_con, len(wiki_hits_con), from_cache=con_cached)
                local_attempts.append(
                    {
                        "provider": "wikipedia_live",
                        "direction": "contradiction_oriented",
                        "query": contra_q,
                        "outcome": con_out,
                        "available": con_avail,
                        "from_cache": con_cached or con_out == "cache_hit",
                        "items_retrieved": len(wiki_hits_con),
                        "reason": con_reason,
                    }
                )
            meta["wikipedia_fallback_triggered"] = True
            meta["wikipedia_status"] = status_sup if status_sup != "no_results" or not con_cached else status_con
            meta["wikipedia_from_cache"] = bool(sup_cached or con_cached)
            meta["live_count"] = len(wiki_hits_sup) + len(wiki_hits_con)

            merged_all: List[EvidenceSentence] = list(local_results)
            seen_texts = {re.sub(r"\W+", "", ev.text.lower())[:90] for ev in local_results}

            for dir_label, hits_group in (("support_oriented", wiki_hits_sup), ("contradiction_oriented", wiki_hits_con)):
                for hit in hits_group:
                    norm_key = re.sub(r"\W+", "", hit.text.lower())[:90]
                    if norm_key in seen_texts:
                        continue
                    seen_texts.add(norm_key)
                    merged_all.append(
                        EvidenceSentence(
                            rank=0,
                            row_id=-1,
                            doc_id=hit.doc_id,
                            page=hit.page,
                            sentence_id=hit.sentence_id,
                            text=hit.text,
                            similarity_score=hit.similarity_score,
                            source_type="wikipedia_live",
                            source_url=hit.source_url,
                            publication_date=hit.publication_date,
                            retrieval_direction=dir_label,
                        )
                    )

            is_temporal = trigger_reason == "temporal_or_office_claim"
            merged_all.sort(
                key=lambda x: (
                    x.similarity_score + (0.04 if (is_temporal and x.source_type == "wikipedia_live") else (0.015 if x.source_type == "wikipedia_live" else 0.0))
                ),
                reverse=True,
            )
            max_keep = max(k + 4, 9)
            final_hits = list(merged_all[:max_keep])
            # Preserve at least 2 contradiction-oriented hits & 2 live hits when present so second pass never misses them
            for bucket in (
                [m for m in merged_all if m.retrieval_direction == "contradiction_oriented" and m not in final_hits][:2],
                [m for m in merged_all if m.source_type == "wikipedia_live" and m not in final_hits and m.similarity_score >= 0.45][:2],
            ):
                final_hits.extend(bucket)

            for idx, item in enumerate(final_hits, 1):
                item.rank = idx
            return final_hits, meta
        except Exception as exc:
            logger.warning(f"Independent Wikipedia fallback error ({exc}); returning local FEVER results only.")
            meta["wikipedia_fallback_triggered"] = True
            meta["wikipedia_status"] = "error_fallback"
            local_attempts.append(
                {
                    "provider": "wikipedia_live",
                    "direction": "support_oriented",
                    "query": claim.strip(),
                    "outcome": "network_error",
                    "available": False,
                    "from_cache": False,
                    "items_retrieved": 0,
                    "reason": f"error_fallback: {exc}",
                }
            )
            return local_results[:max(k, 8)], meta


def get_retriever() -> FAISSRetriever:
    return FAISSRetriever()
