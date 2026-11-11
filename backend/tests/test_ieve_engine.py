"""
Phase 3 Automated Test Suite — Independent Evidence Verification Engine (IEVE).

Uses local mocks and temporary databases ONLY. Zero live HTTP requests or GDELT quota consumed.
Validates Decisions 1-4 & Mandatory Corrections 1-3:
  1. Initial ML Separation: LIAR BERT & ISOT BERT recorded separately with raw logits,
     applicable_input_type, and no combined score; DeBERTa FEVER NLI operates strictly
     post-retrieval on (claim, evidence) pairs.
  2. Bidirectional Retrieval: support, contradiction, and neutral formulations for local
     FEVER FAISS, Wikipedia, and Google Fact Check; 1 neutral/balanced query for GDELT.
  3. Decision 1 & 2 Option A: static textbook guard logs `skipped_static_reference_fact`
     independent of ML prediction; article verification caps GDELT at <= 2 central/material
     claims while running local/Wikipedia/Fact Check across all extracted claims.
  4. Mandatory Correction 1 (Source Provenance Tiers): official first-party records = Tier 1;
     Wikipedia/FEVER = Tier 2 (never primary-authority certification); single ClaimReviews &
     GDELT = Tier 3; primary-record-dependent claims return UNVERIFIED when Tier 1 is absent.
  5. Mandatory Correction 2 (Attempt Telemetry): explicit distinction between
     `success_with_results`, `no_results`, `cache_hit`, `timeout`, `network_error`,
     `quota_exhausted`, `skipped_by_policy`, and `unavailable_no_api_key`.
  6. Canonical hash & legacy record backward compatibility.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest
import requests
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.schemas.verification import TextVerificationResponse, VerdictEnum
from backend.app.schemas.article import ArticleClassifierSignal, ArticleVerificationResponse
from backend.app.services import verification_service
from backend.app.services.blockchain_service import create_hash_summary_from_text
from backend.app.services.external_apis.evidence_aggregator import (
    ExternalAggregationResult,
    ExternalEvidenceAggregator,
    should_query_gdelt_for_claim,
)
from backend.app.services.external_apis.evidence_cache import ExternalEvidenceCache
from backend.app.services.external_apis.gdelt_client import GdeltArticleItem, GdeltClient
from backend.app.services.external_apis.gdelt_usage_tracker import GdeltUsageTracker
from backend.app.services.external_apis.google_factcheck_client import FactCheckMatch, GoogleFactCheckClient
from ml.inference.claim_verifier import VerifiedEvidence
from ml.inference.evidence_quality import (
    TIER_1_PRIMARY_OFFICIAL,
    TIER_2_SECONDARY_ENCYCLOPEDIC,
    TIER_3_SECONDARY_OR_METADATA,
    build_directional_queries,
    evaluate_documentary_evidence,
)
from ml.inference.second_pass_synthesizer import (
    InitialMLSignals,
    ModelSignalRecord,
    SecondPassEvaluator,
    map_classifier_to_preliminary_verdict,
)
from ml.inference.verdict_synthesizer import VerdictSynthesizer
from ml.rag.retriever import EvidenceSentence

client = TestClient(app)


def _mk_verified(
    *,
    claim_text: str,
    page: str,
    text: str,
    sim: float = 0.80,
    nli_label: str = "SUPPORTS",
    raw_label: Optional[str] = None,
    sup: float = 0.90,
    ref: float = 0.05,
    nei: float = 0.05,
    source_type: str = "wikipedia_live",
    source_url: str = "https://en.wikipedia.org/wiki/Test_Page",
    pub_date: str = "2026-11-10T00:00:00Z",
    retrieval_direction: str = "neutral",
    doc_id: Optional[str] = None,
    sentence_id: int = 0,
) -> VerifiedEvidence:
    return VerifiedEvidence(
        rank=1,
        page=page,
        sentence_id=sentence_id,
        doc_id=doc_id or f"{source_type}_{page}_{sentence_id}",
        text=text,
        retrieval_similarity=sim,
        nli_label=nli_label,
        nli_confidence=max(sup, ref, nei),
        nli_probabilities={"supports": sup, "refutes": ref, "not_enough_info": nei},
        source_type=source_type,
        source_url=source_url,
        publication_date=pub_date,
        raw_nli_label=raw_label or nli_label,
        retrieval_direction=retrieval_direction,
    )


def _mock_fc_match(
    publisher: str,
    rating: str,
    claim_text: str,
    review_title: str,
    url: str = "https://example.org/factcheck",
    is_stale: bool = False,
    is_conflicting: bool = False,
) -> FactCheckMatch:
    return FactCheckMatch(
        claim_text=claim_text,
        review_title=review_title,
        publisher_name=publisher,
        publisher_site="example.org",
        reviewer_name=publisher,
        rating_text=rating,
        review_url=url,
        review_publication_date="2026-01-15",
        claim_appearance_date="2026-01-10",
        original_claim_author="Social Post",
        language_code="en",
        retrieved_at=datetime.now(timezone.utc).isoformat(),
        is_stale=is_stale,
        stale_reason="Older than recent developments" if is_stale else None,
        is_conflicting=is_conflicting,
    )


def _mock_gdelt_article(
    title: str,
    url: str = "https://reuters.com/news/example",
    domain: str = "reuters.com",
    syndicated_count: int = 1,
) -> GdeltArticleItem:
    return GdeltArticleItem(
        title=title,
        url=url,
        domain=domain,
        published_at="20261110T080000Z",
        language="English",
        source_country="United States",
        search_query="example query",
        search_window="1month",
        retrieved_at=datetime.now(timezone.utc).isoformat(),
        syndicated_count=syndicated_count,
    )


# ---------------------------------------------------------------------
# 1. Prediction-Independent Bidirectional Retrieval & GDELT Option A
# ---------------------------------------------------------------------

class TestPredictionIndependentRetrieval:
    @pytest.mark.parametrize(
        "liar_label,expected_preliminary",
        [
            ("true", "GENUINE"),
            ("false", "FAKE"),
            ("barely-true", "MISLEADING"),
            ("half-true", "MISLEADING"),
            ("pants-fire", "FAKE"),
            ("mostly-true", "GENUINE"),
            ("unverified", "UNVERIFIED"),
        ],
    )
    def test_same_claim_executes_identical_retrieval_and_separates_ml_signals(
        self, liar_label, expected_preliminary
    ):
        assert map_classifier_to_preliminary_verdict(liar_prediction=liar_label) == expected_preliminary

        svc = verification_service.get_verification_service()
        claim = "Apollo 11 landed on the Moon in 1969."
        captured_dir_queries = []

        def fake_classify(_c):
            return SimpleNamespace(
                prediction=liar_label,
                confidence=0.95,
                probabilities={liar_label: 0.95, "other": 0.05},
                raw_logits={liar_label: 2.31, "other": -1.12},
                model_name="bert-base-uncased",
                disclaimer="mock",
            )

        def spy_retrieve_independent(c, dir_q, top_k=5):
            captured_dir_queries.append(dict(dir_q))
            return [
                EvidenceSentence(
                    rank=1,
                    row_id=0,
                    doc_id="fever_local_Apollo_11_0",
                    page="Apollo 11",
                    sentence_id=0,
                    text="Apollo 11 was the American spaceflight that landed the first two humans on the Moon in July 1969.",
                    similarity_score=0.84,
                    source_type="fever_local",
                    retrieval_direction="support_oriented",
                ),
                EvidenceSentence(
                    rank=2,
                    row_id=1,
                    doc_id="fever_local_Apollo_11_1",
                    page="Apollo program",
                    sentence_id=2,
                    text="The Apollo 11 mission landed humans on the Moon on July 20, 1969.",
                    similarity_score=0.81,
                    source_type="fever_local",
                    retrieval_direction="neutral",
                ),
            ], {
                "directions_executed": ["support", "contradict", "neutral"],
                "wikipedia_status": "not_needed",
                "wikipedia_fallback_triggered": False,
            }

        def fake_collect_external(claims, **kwargs):
            return ExternalAggregationResult(google_status="no_results", gdelt_status="skipped_not_needed")

        with (
            patch.object(svc.claim_classifier, "classify", side_effect=fake_classify),
            patch.object(svc.retriever, "retrieve_independent", side_effect=spy_retrieve_independent),
            patch.object(svc.external_aggregator, "collect_independent_external_evidence", side_effect=fake_collect_external),
        ):
            _, _, audit, _ = svc._evaluate_single_claim_ieve(claim, top_k=5)

        assert len(captured_dir_queries) == 1
        assert {"support", "contradict", "neutral", "factcheck_support", "factcheck_contradict", "gdelt_neutral"}.issubset(
            set(captured_dir_queries[0].keys())
        )
        assert audit.directions_executed == ["support", "contradict", "neutral"]

        # Verify Decision 1 Modified Option A: LIAR and ISOT stored separately with raw logits; DeBERTa separated
        liar_sig = audit.initial_ml_signals.liar_signal
        isot_sig = audit.initial_ml_signals.isot_signal
        assert liar_sig.applicable is True
        assert liar_sig.applicable_input_type == "short_claim"
        assert liar_sig.raw_logits == {liar_label: 2.31, "other": -1.12}
        assert isot_sig.applicable is False
        assert isot_sig.applicable_input_type == "full_article"
        assert audit.initial_ml_signals.preliminary_verdict == expected_preliminary
        assert audit.nli_evaluation.evaluation_stage == "post_retrieval_claim_evidence_pair"
        assert audit.nli_evaluation.pairs_evaluated == 2

    @pytest.mark.parametrize(
        "verdict_tag",
        ["GENUINE", "FAKE", "MISLEADING", "PARTIALLY_TRUE", "OUTDATED", "UNVERIFIED"],
    )
    def test_all_six_verdict_inputs_execute_identical_gdelt_and_bidirectional_factcheck(self, tmp_path, verdict_tag):
        claim = "Global Summit 2026 signed climate funding agreement in Geneva."
        run_gd, reason = should_query_gdelt_for_claim(claim, phase1_verdict=verdict_tag)
        assert run_gd is True
        assert reason == "news_or_uncertain_claim"

        static_claim = "Water boils at 100 degrees Celsius."
        run_static, reason_s = should_query_gdelt_for_claim(static_claim, phase1_verdict=verdict_tag)
        assert run_static is False
        assert reason_s == "resolved_static_reference_fact"

        # Verify aggregator runs 2 Google Fact Check queries (support + contradict) and 1 neutral GDELT query
        db = str(tmp_path / f"agg_{verdict_tag}.db")
        tracker = GdeltUsageTracker(db_path=db)
        cache = ExternalEvidenceCache(db_path=db)
        fc_sess = MagicMock()
        fc_sess.get.return_value = MagicMock(status_code=200, ok=True, json=lambda: {"claims": []})
        gd_sess = MagicMock()
        gd_sess.get.return_value = MagicMock(status_code=200, ok=True, json=lambda: {"articles": []})
        settings = SimpleNamespace(
            GOOGLE_FACT_CHECK_API_KEY="test-key-safe",
            GOOGLE_FACT_CHECK_TIMEOUT_SEC=5.0,
            GDELT_ENABLED=True,
            GDELT_REQUEST_LIMIT=200,
            GDELT_WARNING_THRESHOLD=20,
            GDELT_CONNECT_TIMEOUT_SEC=8.0,
            GDELT_TIMEOUT_SEC=12.0,
            GDELT_MAX_RECORDS=10,
            GDELT_MAX_RETRIES=0,
            GDELT_DEFAULT_TIMESPAN="1month",
        )
        with (
            patch("backend.app.services.external_apis.google_factcheck_client.get_settings", return_value=settings),
            patch("backend.app.services.external_apis.gdelt_client.get_settings", return_value=settings),
            patch("backend.app.services.external_apis.gdelt_usage_tracker.get_settings", return_value=settings),
        ):
            agg = ExternalEvidenceAggregator(
                fact_check_client=GoogleFactCheckClient(cache=cache, session=fc_sess),
                gdelt_client=GdeltClient(tracker=tracker, cache=cache, session=gd_sess),
            )
            res = agg.enrich_claims([claim], phase1_verdict=verdict_tag, max_fact_check_queries=2, max_gdelt_queries=1)

        fc_dirs = [a.direction for a in res.retrieval_attempts if a.provider == "google_fact_check"]
        gd_dirs = [a.direction for a in res.retrieval_attempts if a.provider == "gdelt"]
        assert fc_dirs == ["support_oriented", "contradiction_oriented"]
        assert gd_dirs == ["neutral"]
        assert tracker.get_status().requests_used == 1

    def test_static_fact_logs_skipped_static_reference_fact_and_article_caps_gdelt_at_two(self, tmp_path):
        db = str(tmp_path / "static_art.db")
        tracker = GdeltUsageTracker(db_path=db)
        cache = ExternalEvidenceCache(db_path=db)
        fc_sess = MagicMock()
        fc_sess.get.return_value = MagicMock(status_code=200, ok=True, json=lambda: {"claims": []})
        gd_sess = MagicMock()
        gd_sess.get.return_value = MagicMock(status_code=200, ok=True, json=lambda: {"articles": []})
        settings = SimpleNamespace(
            GOOGLE_FACT_CHECK_API_KEY="test-key-safe",
            GOOGLE_FACT_CHECK_TIMEOUT_SEC=5.0,
            GDELT_ENABLED=True,
            GDELT_REQUEST_LIMIT=200,
            GDELT_WARNING_THRESHOLD=20,
            GDELT_CONNECT_TIMEOUT_SEC=8.0,
            GDELT_TIMEOUT_SEC=12.0,
            GDELT_MAX_RECORDS=10,
            GDELT_MAX_RETRIES=0,
            GDELT_DEFAULT_TIMESPAN="1month",
        )
        with (
            patch("backend.app.services.external_apis.google_factcheck_client.get_settings", return_value=settings),
            patch("backend.app.services.external_apis.gdelt_client.get_settings", return_value=settings),
            patch("backend.app.services.external_apis.gdelt_usage_tracker.get_settings", return_value=settings),
        ):
            agg = ExternalEvidenceAggregator(
                fact_check_client=GoogleFactCheckClient(cache=cache, session=fc_sess),
                gdelt_client=GdeltClient(tracker=tracker, cache=cache, session=gd_sess),
            )
            # 1. Static reference assertion -> explicitly logged as `skipped_static_reference_fact`
            static_res = agg.collect_independent_external_evidence(["Water boils at 100 degrees Celsius."])
            assert any(a.reason == "skipped_static_reference_fact" and a.outcome == "skipped_by_policy" for a in static_res.retrieval_attempts)
            assert static_res.gdelt_claim_selections[0]["reason"] == "skipped_static_reference_fact"
            assert tracker.get_status().requests_used == 0

            # 2. Article with 4 claims -> max 2 GDELT queries selected by centrality x materiality; all 4 get Fact Check
            four_claims = [
                "Geneva Climate Accord 2026 established a 40 billion dollar adaptation fund.",
                "European Energy Ministry ratified the Geneva Climate Accord in May 2026.",
                "Observers debated grid modernization targets during Geneva sessions.",
                "Delegate transport schedules shifted twice near Lake Geneva.",
            ]
            art_res = agg.collect_independent_external_evidence(
                four_claims,
                max_fact_check_queries=8,
                max_gdelt_queries=2,
                gdelt_eligible_claims=four_claims[:2],
                gdelt_skipped_claims=[(c, "skipped_article_gdelt_cap_max2") for c in four_claims[2:]],
            )
            selected_gd = [s for s in art_res.gdelt_claim_selections if s["selected"]]
            skipped_gd = [s for s in art_res.gdelt_claim_selections if not s["selected"]]
            assert len(selected_gd) == 2
            assert len(skipped_gd) == 2
            assert tracker.get_status().requests_used == 2
            # All 4 claims ran Google Fact Check attempts
            assert len([a for a in art_res.retrieval_attempts if a.provider == "google_fact_check"]) >= 4

    def test_retrieve_independent_queries_both_support_and_contradiction_on_wikipedia_and_faiss(self):
        svc = verification_service.get_verification_service()
        dir_q = build_directional_queries("Barack Obama is the current President of the United States.")
        wiki_calls = []

        def fake_wiki_retrieve(query, top_k=5):
            wiki_calls.append(query)
            return []

        from ml.rag import wikipedia_fallback
        fake_wc = SimpleNamespace(retrieve=fake_wiki_retrieve, last_status="no_results")
        with patch.object(wikipedia_fallback, "get_wikipedia_fallback", return_value=fake_wc):
            hits, meta = svc.retriever.retrieve_independent(
                "Barack Obama is the current President of the United States.",
                dir_q.to_dict(),
                top_k=4,
            )

        assert meta["directions_executed"] == ["support", "contradict", "neutral"]
        assert len(wiki_calls) == 2
        assert any("former" in q or "ended" in q or "replaced" in q for q in wiki_calls)
        assert any(a["provider"] == "fever_local" for a in meta["local_attempts"])
        assert len([a for a in meta["local_attempts"] if a["provider"] == "wikipedia_live"]) == 2


# ---------------------------------------------------------------------
# 2. Tiered Provenance, Single-Source Rules, Telemetry & Second-Pass Logic
# ---------------------------------------------------------------------

class TestTieredSufficiencyAndQualityGates:
    def _run_second_pass(
        self,
        claim: str,
        initial_verdict: str = "UNVERIFIED",
        init_conf: float = 0.85,
        doc_ev=None,
        fc_matches=None,
        news_ev=None,
        ret_meta=None,
        ext_meta=None,
    ):
        docs = doc_ev or []
        p1 = VerdictSynthesizer().synthesize(claim, docs, retrieval_meta=ret_meta or {})
        dq = build_directional_queries(claim)
        liar_sig = ModelSignalRecord(
            model_name="bert-base-uncased",
            dataset_origin="LIAR",
            applicable_input_type="short_claim",
            applicable=True,
            prediction=initial_verdict.lower(),
            confidence=init_conf,
            probabilities={initial_verdict.lower(): init_conf},
            raw_logits={initial_verdict.lower(): 1.8},
            preliminary_verdict_tag=initial_verdict,
            disclaimer="mock liar",
        )
        isot_sig = ModelSignalRecord(
            model_name="google-bert/bert-base-uncased",
            dataset_origin="ISOT",
            applicable_input_type="full_article",
            applicable=False,
            disclaimer="not applicable",
        )
        init_signals = InitialMLSignals(
            liar_signal=liar_sig,
            isot_signal=isot_sig,
            preliminary_verdict=initial_verdict,
        )
        return SecondPassEvaluator().evaluate(
            claim=claim,
            initial_signals=init_signals,
            directional_queries=dq,
            documentary_evidence=docs,
            phase1_synthesis=p1,
            fact_check_matches=fc_matches,
            news_evidence=news_ev,
            retrieval_meta=ret_meta or {},
            external_meta=ext_meta or {},
        )

    def test_wikipedia_classified_as_tier2_and_never_auto_primary_authority(self):
        claim = "Apollo 11 landed humans on the Moon in July 1969."
        wiki_hit = _mk_verified(
            claim_text=claim,
            page="Apollo 11",
            text="Apollo 11 was the American spaceflight that landed the first two humans on the Moon in July 1969.",
            source_type="wikipedia_live",
        )
        q_wiki = evaluate_documentary_evidence(claim, wiki_hit)
        assert q_wiki.evidence_tier == TIER_2_SECONDARY_ENCYCLOPEDIC
        assert q_wiki.is_official_primary is False
        assert q_wiki.is_secondary_encyclopedic is True
        assert q_wiki.meets_single_source_criteria is False

        fever_hit = _mk_verified(
            claim_text=claim,
            page="Apollo 11",
            text="Apollo 11 landed in 1969.",
            source_type="fever_local",
        )
        q_fever = evaluate_documentary_evidence(claim, fever_hit)
        assert q_fever.evidence_tier == TIER_2_SECONDARY_ENCYCLOPEDIC
        assert q_fever.is_official_primary is False
        assert q_fever.meets_single_source_criteria is False

    def test_single_weak_or_moderate_wikipedia_passage_cannot_certify_genuine(self):
        claim = "Acme Microgrid Project expanded rural solar capacity."
        moderate_wiki = _mk_verified(
            claim_text=claim,
            page="Acme Microgrid Project",
            text="The Acme Microgrid Project examined rural solar expansion options.",
            sim=0.58,
            nli_label="SUPPORTS",
            source_type="wikipedia_live",
        )
        res, audit = self._run_second_pass(
            claim=claim,
            initial_verdict="GENUINE",
            doc_ev=[moderate_wiki],
            ret_meta={"wikipedia_status": "ok"},
        )
        assert res.verdict == "UNVERIFIED"
        assert audit.evidence_quality_summary.primary_official_sources_available is False
        assert audit.evidence_quality_summary.tier1_official_primary_count == 0
        assert audit.evidence_quality_summary.tier2_encyclopedic_count == 1

    def test_primary_record_dependent_claim_returns_unverified_without_tier1_official_record(self):
        claim = "Supreme Court ruled in a confidential 2026 docket that MegaBank must liquidate holdings."
        wiki_only = _mk_verified(
            claim_text=claim,
            page="MegaBank",
            text="Supreme Court ruled on July 12, 2026 that MegaBank must liquidate holdings under docket 26-101.",
            sim=0.86,
            nli_label="SUPPORTS",
            source_type="wikipedia_live",
        )
        res, audit = self._run_second_pass(
            claim=claim,
            initial_verdict="GENUINE",
            doc_ev=[wiki_only],
            ret_meta={"wikipedia_status": "ok"},
        )
        assert res.verdict == "UNVERIFIED"
        assert audit.evidence_quality_summary.claim_requires_primary_record is True
        assert audit.evidence_quality_summary.primary_official_sources_available is False
        assert "tier 1" in audit.second_pass_reasoning.lower()

        # Genuine Tier 1 official record CAN establish a bounded official fact without needing 2 sources
        official_doc = _mk_verified(
            claim_text=claim,
            page="US Supreme Court Opinion Docket 26-101",
            text="Supreme Court ruled on July 12, 2026 in Docket 26-101 that MegaBank must liquidate specified holdings.",
            sim=0.90,
            nli_label="SUPPORTS",
            source_type="official_record",
            source_url="https://www.supremecourt.gov/opinions/26-101.pdf",
            pub_date="2026-07-12",
        )
        res_t1, audit_t1 = self._run_second_pass(
            claim=claim,
            initial_verdict="UNVERIFIED",
            doc_ev=[official_doc],
        )
        assert res_t1.verdict == "GENUINE"
        assert audit_t1.evidence_quality_summary.tier1_official_primary_count == 1
        assert audit_t1.supporting_evidence[0].evidence_tier == TIER_1_PRIMARY_OFFICIAL
        assert audit_t1.supporting_evidence[0].meets_single_source_criteria is True

    def test_tier3_support_only_and_contradict_only_never_prove_genuine_or_fake(self):
        claim = "Global Fusion Reactor achieved net energy gain in Geneva in 2026."
        # GDELT headline alone -> UNVERIFIED
        res_gd, _ = self._run_second_pass(
            claim=claim,
            initial_verdict="GENUINE",
            news_ev=[_mock_gdelt_article("Global Fusion Reactor confirms net energy gain in Geneva 2026")],
            ext_meta={"google_status": "no_results", "gdelt_status": "ok"},
        )
        assert res_gd.verdict == "UNVERIFIED"

        # Single Google Fact Check True -> UNVERIFIED
        res_fc_t, _ = self._run_second_pass(
            claim=claim,
            initial_verdict="GENUINE",
            fc_matches=[_mock_fc_match("Reviewer A", "True", claim, "Global Fusion Reactor Geneva gain")],
            ext_meta={"google_status": "ok", "gdelt_status": "no_results"},
        )
        assert res_fc_t.verdict == "UNVERIFIED"

        # Single Google Fact Check False -> UNVERIFIED
        res_fc_f, _ = self._run_second_pass(
            claim=claim,
            initial_verdict="FAKE",
            fc_matches=[_mock_fc_match("Reviewer A", "False", claim, "Global Fusion Reactor Geneva false")],
            ext_meta={"google_status": "ok", "gdelt_status": "no_results"},
        )
        assert res_fc_f.verdict == "UNVERIFIED"

    def test_conflicting_credible_sources_produce_cautious_result(self):
        claim = "Apollo 11 landed astronauts safely on the Moon in July 1969."
        doc_sup = _mk_verified(
            claim_text=claim,
            page="Apollo 11",
            text="Apollo 11 was the American spaceflight that landed the first humans on the Moon in July 1969.",
            sim=0.88,
            nli_label="SUPPORTS",
        )
        res, audit = self._run_second_pass(
            claim=claim,
            initial_verdict="GENUINE",
            doc_ev=[doc_sup],
            fc_matches=[
                _mock_fc_match("FactCheck One", "True", claim, "Apollo 11 Moon landing 1969 confirmed"),
                _mock_fc_match("FactCheck Two", "False", claim, "Apollo 11 Moon landing 1969 disputed", is_conflicting=True),
            ],
            ext_meta={"google_status": "ok", "has_conflicting_fact_checks": True, "gdelt_status": "no_results"},
        )
        assert res.verdict == "UNVERIFIED"
        assert res.conflicting_evidence_detected is True
        assert audit.conflicts_detected is True

    def test_irrelevant_entity_matches_and_outdated_2017_evidence_handled_safely(self):
        # 1. Irrelevant entities rejected cleanly
        claim_irr = "Albert Einstein was the first President of the United States."
        unrelated = _mk_verified(
            claim_text=claim_irr,
            page="Martin Van Buren",
            text="He was the first president to be born a United States citizen.",
            sim=0.72,
            nli_label="SUPPORTS",
            raw_label="SUPPORTS",
            sup=0.99,
            ref=0.01,
        )
        res_irr, audit_irr = self._run_second_pass(
            claim=claim_irr,
            initial_verdict="GENUINE",
            doc_ev=[unrelated],
            news_ev=[_mock_gdelt_article("Tennis Champion Wins Open Title in Paris")],
            ext_meta={"google_status": "no_results", "gdelt_status": "ok"},
        )
        assert res_irr.verdict == "UNVERIFIED"
        assert audit_irr.evidence_quality_summary.rejected_irrelevant_count >= 2

        # 2. Stale 2017 FEVER when live Wikipedia offline -> UNVERIFIED; live end -> OUTDATED
        claim_liz = "Queen Elizabeth II is the current reigning monarch of the United Kingdom."
        stale_2017 = _mk_verified(
            claim_text=claim_liz,
            page="Elizabeth II",
            text="Elizabeth II is the current reigning Queen of the United Kingdom and other Commonwealth realms.",
            sim=0.89,
            nli_label="SUPPORTS",
            source_type="fever_local",
            pub_date="2017-06 (FEVER Wikipedia Corpus)",
        )
        res_off, _ = self._run_second_pass(
            claim=claim_liz,
            initial_verdict="GENUINE",
            doc_ev=[stale_2017],
            ret_meta={"wikipedia_status": "timeout"},
        )
        assert res_off.verdict == "UNVERIFIED"

        live_end = _mk_verified(
            claim_text=claim_liz,
            page="Elizabeth II",
            text="Elizabeth II (21 April 1926 - 8 September 2022) was Queen of the United Kingdom from 1952 until her death in 2022.",
            sim=0.88,
            nli_label="REFUTES",
            sup=0.01,
            ref=0.99,
            source_type="wikipedia_live",
        )
        res_out, audit_out = self._run_second_pass(
            claim=claim_liz,
            initial_verdict="GENUINE",
            doc_ev=[stale_2017, live_end],
            ret_meta={"wikipedia_status": "ok"},
        )
        assert res_out.verdict == "OUTDATED"
        assert audit_out.verdict_changed_from_initial is True

    def test_failed_providers_telemetry_outcomes_and_syndication_deduplication(self):
        claim = "European Parliament voted on AI disclosure rules in Brussels."
        synd_news = _mock_gdelt_article(
            "European Parliament confirms AI disclosure rules vote approved in Brussels",
            syndicated_count=7,
        )
        res, audit = self._run_second_pass(
            claim="Novel Superconductor LK-2026 operates at ambient pressure.",
            initial_verdict="UNVERIFIED",
            ret_meta={"wikipedia_status": "timeout"},
            ext_meta={
                "google_status": "unavailable_no_api_key",
                "gdelt_status": "quota_exhausted",
                "retrieval_attempts": [
                    {"provider": "google_fact_check", "direction": "support_oriented", "query": "LK-2026", "outcome": "unavailable_no_api_key", "available": False, "items_retrieved": 0, "reason": "No API key"},
                    {"provider": "gdelt", "direction": "neutral", "query": "LK-2026", "outcome": "quota_exhausted", "available": False, "items_retrieved": 0, "reason": "Cap 200 reached"},
                ],
            },
        )
        assert res.verdict == "UNVERIFIED"
        assert set(audit.unavailable_providers) >= {"wikipedia_live", "google_fact_check", "gdelt"}
        outcomes = {a.outcome for a in audit.retrieval_attempts}
        assert {"timeout", "unavailable_no_api_key", "quota_exhausted"}.issubset(outcomes)

        _, audit_synd = self._run_second_pass(
            claim=claim,
            initial_verdict="UNVERIFIED",
            news_ev=[synd_news],
            ext_meta={"google_status": "no_results", "gdelt_status": "ok", "duplicates_collapsed": 6},
        )
        assert audit_synd.evidence_quality_summary.independent_supporting_sources == 1
        assert audit_synd.evidence_quality_summary.syndicated_duplicates_collapsed >= 6

    def test_second_pass_can_override_and_confirm_with_corroborated_tier2(self):
        # 1. Explicit numeric year refutation flips initial GENUINE (0.99) -> FAKE
        claim_false = "19 Kids and Counting was cancelled in 2030."
        con_doc = _mk_verified(
            claim_text=claim_false,
            page="19 Kids and Counting",
            text="After multiple scandals and legal proceedings, TLC cancelled 19 Kids and Counting in 2015 after ten seasons.",
            sim=0.83,
            nli_label="REFUTES",
            sup=0.01,
            ref=0.99,
            source_type="fever_local",
        )
        res_override, audit_override = self._run_second_pass(
            claim=claim_false,
            initial_verdict="GENUINE",
            init_conf=0.99,
            doc_ev=[con_doc],
        )
        assert res_override.verdict == "FAKE"
        assert audit_override.second_pass_decision == "overridden_by_evidence"

        # 2. Corroborated Tier 2 (2 distinct sentences) confirms GENUINE while reporting no Tier 1 primary source
        claim_true = "19 Kids and Counting is an American reality television show featuring the Duggar family."
        sup_doc_1 = _mk_verified(
            claim_text=claim_true,
            page="19 Kids and Counting",
            text="19 Kids and Counting is an American reality television show featuring the Duggar family on TLC.",
            sim=0.89,
            nli_label="SUPPORTS",
            sup=0.99,
            ref=0.01,
            source_type="fever_local",
            sentence_id=0,
        )
        sup_doc_2 = _mk_verified(
            claim_text=claim_true,
            page="Jim Bob Duggar",
            text="Jim Bob Duggar and his family were featured in the TLC reality series 19 Kids and Counting.",
            sim=0.79,
            nli_label="SUPPORTS",
            sup=0.96,
            ref=0.04,
            source_type="fever_local",
            sentence_id=1,
        )
        res_confirm, audit_confirm = self._run_second_pass(
            claim=claim_true,
            initial_verdict="GENUINE",
            init_conf=0.90,
            doc_ev=[sup_doc_1, sup_doc_2],
        )
        assert res_confirm.verdict == "GENUINE"
        assert audit_confirm.second_pass_decision == "confirmed_initial"
        assert audit_confirm.evidence_quality_summary.primary_official_sources_available is False
        assert audit_confirm.evidence_quality_summary.tier2_encyclopedic_count == 2


# ---------------------------------------------------------------------
# 3. End-to-End FastAPI Audit Trails, Schema & Canonical Hash Compatibility
# ---------------------------------------------------------------------

class TestIieveEndToEndAndCompatibility:
    def test_compound_claim_article_and_legacy_compatibility(self, tmp_path):
        db = str(tmp_path / "ieve_api.db")
        tracker = GdeltUsageTracker(db_path=db)
        cache = ExternalEvidenceCache(db_path=db)
        fc_sess = MagicMock()
        fc_sess.get.return_value = MagicMock(status_code=200, ok=True, json=lambda: {"claims": []})
        gd_sess = MagicMock()
        gd_sess.get.return_value = MagicMock(status_code=200, ok=True, json=lambda: {"articles": []})

        svc = verification_service.get_verification_service()
        orig_agg = svc.external_aggregator
        try:
            svc.external_aggregator = ExternalEvidenceAggregator(
                fact_check_client=GoogleFactCheckClient(cache=cache, session=fc_sess),
                gdelt_client=GdeltClient(tracker=tracker, cache=cache, session=gd_sess),
            )
            claim = "Paris is the capital of France, and Apollo 11 landed on Mars in 1969."
            resp = client.post("/api/v1/verify/text", json={"claim": claim, "top_k": 4})
            assert resp.status_code == 200
            data = resp.json()

            assert data["verdict"] == "PARTIALLY_TRUE"
            assert len(data["claim_verdicts"]) == 2
            top_audit = data["evidence_audit_trail"]
            assert top_audit is not None
            assert top_audit["final_verdict"] == "PARTIALLY_TRUE"
            assert top_audit["initial_ml_signals"]["liar_signal"]["applicable"] is True
            assert top_audit["initial_ml_signals"]["isot_signal"]["applicable"] is False
            assert top_audit["nli_evaluation"]["evaluation_stage"] == "post_retrieval_claim_evidence_pair"
            assert len(top_audit["retrieval_attempts"]) >= 1
            assert top_audit["evidence_quality_summary"]["primary_official_sources_available"] is False

            # Canonical hash backward compatibility preserved
            parsed = TextVerificationResponse(**data)
            recomputed = create_hash_summary_from_text(claim, parsed)
            assert recomputed.record_hash == data["blockchain_hash"]["record_hash"]
            assert recomputed.canonical_json == data["blockchain_hash"]["canonical_json"]

            # Article verification checks separate LIAR + ISOT models + GDELT max-2 cap selection log
            art_resp = client.post(
                "/api/v1/verify/article",
                json={
                    "title": "Duggar Reality Show Run",
                    "text": (
                        "19 Kids and Counting is an American reality television show featuring the Duggar family. "
                        "However, 19 Kids and Counting was cancelled in 2030 after decades on television."
                    ),
                    "max_claims": 2,
                },
            )
            assert art_resp.status_code == 200
            art_data = art_resp.json()
            assert art_data["overall_verdict"] == "PARTIALLY_TRUE"
            art_audit = art_data["evidence_audit_trail"]
            assert art_audit["initial_ml_signals"]["liar_signal"]["applicable"] is True
            assert art_audit["initial_ml_signals"]["isot_signal"]["applicable"] is True
            assert art_audit["nli_evaluation"]["pairs_evaluated"] >= 2
            assert len(art_audit["gdelt_claim_selections"]) <= 2

            # Legacy record schema compatibility (records without evidence_audit_trail deserialize cleanly)
            legacy_text = TextVerificationResponse(
                claim="Legacy claim",
                verdict=VerdictEnum.LIKELY_GENUINE,
                confidence_score=0.87,
                explanation="Legacy",
                evidence=[],
                limitations=[],
            )
            assert legacy_text.evidence_audit_trail is None
            legacy_art = ArticleVerificationResponse(
                overall_verdict=VerdictEnum.UNVERIFIED,
                overall_confidence=0.3,
                summary_explanation="Legacy",
                article_classifier=ArticleClassifierSignal(
                    prediction="REAL",
                    confidence=0.8,
                    probabilities={"FAKE": 0.2, "REAL": 0.8},
                    distribution_shift_warning="warn",
                ),
                claims_analyzed=0,
                extracted_claims=[],
                limitations=[],
            )
            assert legacy_art.evidence_audit_trail is None
        finally:
            svc.external_aggregator = orig_agg


# ---------------------------------------------------------------------
# 4. Phase 3 Remediation Regression Tests (isolation, fairness, concurrency, precedence, >30 telemetry)
# ---------------------------------------------------------------------

class TestPhase3IieveRemediation:
    @staticmethod
    def _make_ext_settings():
        return SimpleNamespace(
            GOOGLE_FACT_CHECK_API_KEY="test-key-secret-value",
            GOOGLE_FACT_CHECK_TIMEOUT_SEC=5.0,
            GDELT_ENABLED=True,
            GDELT_REQUEST_LIMIT=200,
            GDELT_WARNING_THRESHOLD=20,
            GDELT_CONNECT_TIMEOUT_SEC=8.0,
            GDELT_TIMEOUT_SEC=12.0,
            GDELT_MAX_RECORDS=10,
            GDELT_MAX_RETRIES=0,
            GDELT_DEFAULT_TIMESPAN="1month",
            WIKIPEDIA_FALLBACK_ENABLED=True,
            WIKIPEDIA_TIMEOUT_SEC=5.0,
            EXTERNAL_CACHE_TTL_HOURS=24,
        )

    def test_end_to_end_second_pass_overrides_initial_fake_to_genuine_and_genuine_to_misleading_or_unverified(self, tmp_path):
        db = str(tmp_path / "override_api.db")
        tracker = GdeltUsageTracker(db_path=db)
        cache = ExternalEvidenceCache(db_path=db)
        fc_sess = MagicMock()
        fc_sess.get.return_value = MagicMock(status_code=200, ok=True, json=lambda: {"claims": []})
        gd_sess = MagicMock()
        gd_sess.get.return_value = MagicMock(status_code=200, ok=True, json=lambda: {"articles": []})

        svc = verification_service.get_verification_service()
        orig_agg = svc.external_aggregator
        try:
            svc.external_aggregator = ExternalEvidenceAggregator(
                fact_check_client=GoogleFactCheckClient(cache=cache, session=fc_sess),
                gdelt_client=GdeltClient(tracker=tracker, cache=cache, session=gd_sess),
            )

            # 1. Initial LIAR = "pants-fire" (FAKE) overridden -> GENUINE on multi-source corroborated claim
            with patch.object(
                svc.claim_classifier,
                "classify",
                return_value=SimpleNamespace(
                    prediction="pants-fire",
                    confidence=0.94,
                    probabilities={"pants-fire": 0.94, "true": 0.01},
                    raw_logits={"pants-fire": 2.9, "true": -1.4},
                    model_name="bert-base-uncased",
                    disclaimer="mock liar",
                ),
            ):
                r_f2g = client.post("/api/v1/verify/text", json={"claim": "Paris is the capital of France.", "top_k": 5})
            assert r_f2g.status_code == 200
            d_f2g = r_f2g.json()
            assert d_f2g["verdict"] == "GENUINE"
            a_f2g = d_f2g["evidence_audit_trail"]
            assert a_f2g["initial_ml_signals"]["liar_signal"]["prediction"] == "pants-fire"
            assert a_f2g["initial_ml_signals"]["preliminary_verdict"] == "FAKE"
            assert a_f2g["verdict_changed_from_initial"] is True
            assert a_f2g["second_pass_decision"] == "overridden_by_evidence"

            # 2. Initial LIAR = "true" (GENUINE) overridden -> MISLEADING & abstained -> UNVERIFIED
            with patch.object(
                svc.claim_classifier,
                "classify",
                return_value=SimpleNamespace(
                    prediction="true",
                    confidence=0.96,
                    probabilities={"true": 0.96, "false": 0.01},
                    raw_logits={"true": 3.1, "false": -1.6},
                    model_name="bert-base-uncased",
                    disclaimer="mock liar",
                ),
            ):
                r_g2m = client.post("/api/v1/verify/text", json={"claim": "19 Kids and Counting aired on HBO.", "top_k": 5})
                r_g2u = client.post(
                    "/api/v1/verify/text",
                    json={"claim": "Quantum entangled alien potatoes were discovered on Pluto in 2026.", "top_k": 5},
                )
            assert r_g2m.status_code == 200
            assert r_g2m.json()["verdict"] == "MISLEADING"
            assert r_g2m.json()["evidence_audit_trail"]["verdict_changed_from_initial"] is True
            assert r_g2m.json()["evidence_audit_trail"]["second_pass_decision"] == "overridden_by_evidence"

            assert r_g2u.status_code == 200
            assert r_g2u.json()["verdict"] == "UNVERIFIED"
            assert r_g2u.json()["evidence_audit_trail"]["verdict_changed_from_initial"] is True
            assert r_g2u.json()["evidence_audit_trail"]["second_pass_decision"] == "abstained_insufficient"
        finally:
            svc.external_aggregator = orig_agg

    @pytest.mark.parametrize("isot_pred", ["FAKE", "REAL"])
    def test_article_retrieval_independence_for_isot_fake_and_real_predictions(self, tmp_path, isot_pred):
        db = str(tmp_path / f"isot_{isot_pred}.db")
        tracker = GdeltUsageTracker(db_path=db)
        cache = ExternalEvidenceCache(db_path=db)
        fc_sess = MagicMock()
        fc_sess.get.return_value = MagicMock(status_code=200, ok=True, json=lambda: {"claims": []})
        gd_sess = MagicMock()
        gd_sess.get.return_value = MagicMock(status_code=200, ok=True, json=lambda: {"articles": []})

        svc = verification_service.get_verification_service()
        orig_agg = svc.external_aggregator
        orig_ret_ind = svc.retriever.retrieve_independent
        orig_ext_fn = None
        captured_queries = []
        captured_ext_claims = []

        def spy_ret(c, dq, top_k=5):
            captured_queries.append((c, dict(dq)))
            return orig_ret_ind(c, dq, top_k=top_k)

        fake_isot = SimpleNamespace(
            prediction=isot_pred,
            confidence=0.92,
            probabilities={"FAKE": 0.92 if isot_pred == "FAKE" else 0.08, "REAL": 0.08 if isot_pred == "FAKE" else 0.92},
            raw_logits={"FAKE": 2.4 if isot_pred == "FAKE" else -2.4, "REAL": -2.4 if isot_pred == "FAKE" else 2.4},
            model_name="google-bert/bert-base-uncased",
            distribution_shift_warning="ISOT statistical style signal only (distribution shifts apply).",
        )

        try:
            agg = ExternalEvidenceAggregator(
                fact_check_client=GoogleFactCheckClient(cache=cache, session=fc_sess),
                gdelt_client=GdeltClient(tracker=tracker, cache=cache, session=gd_sess),
            )
            orig_ext_fn = agg.collect_independent_external_evidence

            def spy_ext(claims, **kwargs):
                captured_ext_claims.append((list(claims), list(kwargs.get("claim_ids") or [])))
                return orig_ext_fn(claims, **kwargs)

            agg.collect_independent_external_evidence = spy_ext
            svc.external_aggregator = agg
            with (
                patch.object(svc.article_classifier, "classify", return_value=fake_isot),
                patch.object(svc.retriever, "retrieve_independent", side_effect=spy_ret),
            ):
                resp = client.post(
                    "/api/v1/verify/article",
                    json={
                        "title": "Historical Verification Benchmark",
                        "text": (
                            "Paris is the capital of France. "
                            "However, Apollo 11 landed on Mars in 1969 according to viral rumors."
                        ),
                        "max_claims": 2,
                    },
                )
            assert resp.status_code == 200
            data = resp.json()
            assert data["overall_verdict"] == "PARTIALLY_TRUE"
            assert data["article_classifier"]["prediction"] == isot_pred
            assert len(captured_queries) == 2
            assert all({"support", "contradict", "neutral"}.issubset(dq.keys()) for _, dq in captured_queries)
            assert len(captured_ext_claims) == 1
            assert len(captured_ext_claims[0][0]) == 2
        finally:
            svc.external_aggregator = orig_agg

    def test_multi_claim_and_compound_claim_external_evidence_isolation(self, tmp_path):
        db = str(tmp_path / "isolation.db")
        tracker = GdeltUsageTracker(db_path=db)
        cache = ExternalEvidenceCache(db_path=db)
        settings = self._make_ext_settings()

        def _fc_by_claim(_url, params=None, **_kwargs):
            q = (params or {}).get("query", "").lower()
            if "zorvax" in q or "emissions" in q:
                return MagicMock(
                    status_code=200,
                    ok=True,
                    json=lambda: {
                        "claims": [
                            {
                                "text": "Zorvax Emissions Pact capped carbon output at 40 percent.",
                                "claimReview": [
                                    {
                                        "publisher": {"name": "CheckAlpha", "site": "checkalpha.example"},
                                        "url": "https://checkalpha.example/1",
                                        "title": "Zorvax Emissions Pact rating True",
                                        "reviewDate": "2026-01-10",
                                        "textualRating": "True",
                                    },
                                    {
                                        "publisher": {"name": "CheckBeta", "site": "checkbeta.example"},
                                        "url": "https://checkbeta.example/2",
                                        "title": "Zorvax Emissions Pact rating False",
                                        "reviewDate": "2026-01-11",
                                        "textualRating": "False",
                                    },
                                ],
                            }
                        ]
                    },
                )
            return MagicMock(status_code=200, ok=True, json=lambda: {"claims": []})

        fc_sess = MagicMock()
        fc_sess.get.side_effect = _fc_by_claim
        gd_sess = MagicMock()
        gd_sess.get.return_value = MagicMock(status_code=200, ok=True, json=lambda: {"articles": []})

        svc = verification_service.get_verification_service()
        orig_agg = svc.external_aggregator
        try:
            with (
                patch("backend.app.services.external_apis.google_factcheck_client.get_settings", return_value=settings),
                patch("backend.app.services.external_apis.gdelt_client.get_settings", return_value=settings),
                patch("backend.app.services.external_apis.gdelt_usage_tracker.get_settings", return_value=settings),
            ):
                svc.external_aggregator = ExternalEvidenceAggregator(
                    fact_check_client=GoogleFactCheckClient(cache=cache, session=fc_sess),
                    gdelt_client=GdeltClient(tracker=tracker, cache=cache, session=gd_sess),
                )

                # 1. Article mode isolation: Claim A conflicting Fact Checks MUST NOT force Claim B to UNVERIFIED
                art_resp = client.post(
                    "/api/v1/verify/article",
                    json={
                        "title": "European Cities and Emissions",
                        "text": (
                            "Zorvax Emissions Pact capped carbon output at 40 percent. "
                            "Paris is the capital of France."
                        ),
                        "max_claims": 2,
                    },
                )
                assert art_resp.status_code == 200
                art_claims = art_resp.json()["extracted_claims"]
                claim_a = next(c for c in art_claims if "zorvax" in c["claim"].lower())
                claim_b = next(c for c in art_claims if "paris" in c["claim"].lower())
                assert claim_a["verdict"] == "UNVERIFIED"
                assert claim_a["evidence_audit_trail"]["conflicts_detected"] is True
                assert claim_b["verdict"] == "GENUINE"
                assert claim_b["evidence_audit_trail"]["conflicts_detected"] is False

                # 2. Compound text mode isolation
                txt_resp = client.post(
                    "/api/v1/verify/text",
                    json={
                        "claim": "Zorvax Emissions Pact capped carbon output at 40 percent, and Paris is the capital of France.",
                        "top_k": 5,
                    },
                )
                assert txt_resp.status_code == 200
                subs = txt_resp.json()["claim_verdicts"]
                assert len(subs) == 2
                sub_a = next(s for s in subs if "zorvax" in s["claim"].lower())
                sub_b = next(s for s in subs if "paris" in s["claim"].lower())
                assert sub_a["verdict"] == "UNVERIFIED"
                assert sub_a["evidence_audit_trail"]["conflicts_detected"] is True
                assert sub_b["verdict"] == "GENUINE"
                assert sub_b["evidence_audit_trail"]["conflicts_detected"] is False
        finally:
            svc.external_aggregator = orig_agg

    @pytest.mark.parametrize("num_claims", [2, 3, 5])
    def test_compound_claim_round_robin_fairness_and_skip_telemetry(self, tmp_path, num_claims):
        db = str(tmp_path / f"fair_{num_claims}.db")
        tracker = GdeltUsageTracker(db_path=db)
        cache = ExternalEvidenceCache(db_path=db)
        fc_sess = MagicMock()
        fc_sess.get.return_value = MagicMock(status_code=200, ok=True, json=lambda: {"claims": []})
        gd_sess = MagicMock()
        gd_sess.get.return_value = MagicMock(status_code=200, ok=True, json=lambda: {"articles": []})
        settings = self._make_ext_settings()

        claims = [f"Organization Alpha{i} announced initiative Beta{i} in 2026." for i in range(1, num_claims + 1)]
        cids = [f"sub_{i}" for i in range(1, num_claims + 1)]

        with (
            patch("backend.app.services.external_apis.google_factcheck_client.get_settings", return_value=settings),
            patch("backend.app.services.external_apis.gdelt_client.get_settings", return_value=settings),
            patch("backend.app.services.external_apis.gdelt_usage_tracker.get_settings", return_value=settings),
        ):
            agg = ExternalEvidenceAggregator(
                fact_check_client=GoogleFactCheckClient(cache=cache, session=fc_sess),
                gdelt_client=GdeltClient(tracker=tracker, cache=cache, session=gd_sess),
            )
            res = agg.collect_independent_external_evidence(
                claims,
                claim_ids=cids,
                source_label="verify_text",
                max_fact_check_queries=2,
                max_gdelt_queries=1,
            )

        fc_attempts = [a for a in res.retrieval_attempts if a.provider == "google_fact_check"]
        executed_fc = [a for a in fc_attempts if a.outcome != "skipped_by_policy"]
        skipped_fc = [a for a in fc_attempts if a.outcome == "skipped_by_policy"]
        # Round-robin distributes budget=2 across sub_1 and sub_2 (1 each, never 2 to sub_1 and 0 to sub_2)
        assert [a.claim_id for a in executed_fc] == ["sub_1", "sub_2"]
        assert all(a.direction == "support_oriented" for a in executed_fc)
        # All remaining directions and unqueried claims explicitly logged with claim_id + budget skip reason
        for expected_cid in cids:
            assert any(a.claim_id == expected_cid and a.outcome == "skipped_by_policy" and "budget" in (a.reason or "") for a in skipped_fc)

        # GDELT budget=1 queries sub_1 and explicitly logs skipped sub_2..sub_N
        gd_attempts = [a for a in res.retrieval_attempts if a.provider == "gdelt"]
        assert {a.claim_id for a in gd_attempts} == set(cids)
        for skipped_gd_cid in cids[1:]:
            assert any(a.claim_id == skipped_gd_cid and a.outcome == "skipped_by_policy" for a in gd_attempts)

    def test_wikipedia_cache_hit_differing_three_query_outcomes_and_concurrent_threads(self):
        from ml.rag import wikipedia_fallback

        wiki = wikipedia_fallback.WikipediaFallbackClient()
        with wiki._cache_lock:
            wiki._cache.clear()

        def _mk_wiki_json(title: str, extract: str):
            return MagicMock(
                status_code=200,
                ok=True,
                content=b"{}",
                raise_for_status=lambda: None,
                json=lambda: {
                    "query": {
                        "pages": {
                            "1": {
                                "index": 1,
                                "title": title,
                                "fullurl": f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
                                "revisions": [{"timestamp": "2026-10-01T00:00:00Z"}],
                                "extract": extract,
                            }
                        }
                    }
                },
            )

        # 1. Cache-hit propagation through retrieve_with_status -> FAISSRetriever.retrieve_independent -> SecondPassEvaluator
        claim = "Zephyria Capital inaugurated Quantum Rail in 2026."
        dq = build_directional_queries(claim)
        calls = {"n": 0}

        def _single_fetch(_url, params=None, **_kwargs):
            calls["n"] += 1
            return _mk_wiki_json("Zephyria", "Zephyria Capital opened the Quantum Rail transit network in October 2026 for commuters.")

        with patch.object(wiki._session, "get", side_effect=_single_fetch):
            first = wiki.retrieve_with_status(claim, top_k=3)
            second = wiki.retrieve_with_status(claim, top_k=3)
            # Warm cache for directional contradiction query as well so bidirectional retrieve_independent hits cache cleanly
            if dq.contradiction_query and dq.contradiction_query.lower() != claim.lower():
                wiki.retrieve_with_status(dq.contradiction_query, top_k=3)

        assert first.status == "ok" and first.from_cache is False
        assert second.status == "cache_hit" and second.from_cache is True and len(second.hits) >= 1

        svc = verification_service.get_verification_service()
        with (
            patch.object(svc.retriever, "_needs_wikipedia_fallback", return_value=(True, "missing_entities(zephyria)")),
            patch.object(wikipedia_fallback, "get_wikipedia_fallback", return_value=wiki),
            patch.object(wiki._session, "get", side_effect=AssertionError("Should hit cache cleanly")),
        ):
            _, ret_meta = svc.retriever.retrieve_independent(claim, dq.to_dict(), top_k=3)
        assert ret_meta["wikipedia_status"] == "cache_hit"
        assert ret_meta["wikipedia_from_cache"] is True
        assert any(a["provider"] == "wikipedia_live" and a["outcome"] == "cache_hit" and a["from_cache"] is True for a in ret_meta["local_attempts"])

        # Feed into SecondPassEvaluator to assert end-to-end cache_hit audit outcome
        p1 = VerdictSynthesizer().synthesize(claim, [], retrieval_meta=ret_meta)
        _, sp_audit = SecondPassEvaluator().evaluate(
            claim=claim,
            initial_signals=InitialMLSignals(
                liar_signal=ModelSignalRecord(model_name="liar", dataset_origin="LIAR", applicable_input_type="short_claim", applicable=True, prediction="true"),
                isot_signal=ModelSignalRecord(model_name="isot", dataset_origin="ISOT", applicable_input_type="full_article", applicable=False),
                preliminary_verdict="GENUINE",
            ),
            directional_queries=dq,
            documentary_evidence=[],
            phase1_synthesis=p1,
            retrieval_meta=ret_meta,
        )
        assert any(a.provider == "wikipedia_live" and a.outcome == "cache_hit" and a.from_cache is True for a in sp_audit.retrieval_attempts)

        # 2. Three-query fallback with differing per-query outcomes preserves prior timeout & query_outcomes
        with wiki._cache_lock:
            wiki._cache.clear()
        diff_claim = "Aldebaran Minister of Transport announced Orbital Ferry during First Congress of Aldebaran."
        diff_queries = wikipedia_fallback.build_wikipedia_search_queries(diff_claim)
        assert len(diff_queries) >= 2

        def _differing_get(_url, params=None, **_kwargs):
            q = (params or {}).get("gsrsearch", "")
            if q == diff_queries[0]:
                raise requests.Timeout("Simulated Q1 timeout")
            return MagicMock(status_code=200, ok=True, content=b"{}", raise_for_status=lambda: None, json=lambda: {"query": {}})

        with patch.object(wiki._session, "get", side_effect=_differing_get):
            diff_res = wiki.retrieve_with_status(diff_claim, top_k=3)
        assert diff_res.status == "timeout"
        assert diff_res.query_outcomes[0]["status"] == "timeout"
        assert any(o["status"] == "no_results" for o in diff_res.query_outcomes[1:])

        # 3. Concurrent requests with differing outcomes maintain strict request-local isolation
        with wiki._cache_lock:
            wiki._cache.clear()

        def _concurrent_get(_url, params=None, **_kwargs):
            q = (params or {}).get("gsrsearch", "").lower()
            if "timeouttarget" in q:
                raise requests.Timeout("Concurrent timeout")
            return _mk_wiki_json("ConcurAlpha", "ConcurAlpha entity operates solar turbines across northern regions regularly.")

        with patch.object(wiki._session, "get", side_effect=_concurrent_get):
            with ThreadPoolExecutor(max_workers=2) as pool:
                f_timeout = pool.submit(wiki.retrieve_with_status, "TimeoutTarget Entity verified operation.", 3)
                f_ok = pool.submit(wiki.retrieve_with_status, "ConcurAlpha Entity solar turbines.", 3)
                r_timeout = f_timeout.result()
                r_ok = f_ok.result()
        assert r_timeout.status == "timeout"
        assert r_ok.status == "ok" and len(r_ok.hits) >= 1

    def test_read_first_sqlite_cache_access_preserves_gdelt_cache_hit_counter(self, tmp_path):
        db = str(tmp_path / "cache_rw.db")
        cache = ExternalEvidenceCache(db_path=db)
        tracker = GdeltUsageTracker(db_path=db)
        # Miss returns None via read-first SELECT without touching gdelt cache_hits
        assert cache.get("gdelt", "uncached miss query") is None
        assert tracker.get_status().cache_hits == 0

        cache.set("gdelt", "cached hit query", {"articles": [], "retrieved_at": datetime.now(timezone.utc).isoformat()})
        payload = cache.get("gdelt", "cached hit query")
        assert payload is not None
        assert tracker.get_status().cache_hits == 1

    def test_external_provider_exception_creates_explicit_failure_attempts_and_rollup_preserves_over_30_attempts(self, tmp_path):
        svc = verification_service.get_verification_service()
        # 1. Provider exception telemetry in _collect_external_safe & verify_text_claim
        with patch.object(
            svc.external_aggregator,
            "collect_independent_external_evidence",
            side_effect=RuntimeError("Simulated failure with key=SHOULD_BE_REDACTED_KEY123"),
        ):
            r_err = client.post("/api/v1/verify/text", json={"claim": "Apollo 11 landed on the Moon in 1969.", "top_k": 3})
        assert r_err.status_code == 200
        err_audit = r_err.json()["evidence_audit_trail"]
        assert "SHOULD_BE_REDACTED_KEY123" not in r_err.text
        ext_err_attempts = [
            a for a in err_audit["retrieval_attempts"]
            if a["provider"] in ("google_fact_check", "gdelt") and a["outcome"] == "network_error"
        ]
        assert len(ext_err_attempts) == 2

        # 2. >30 retrieval attempts preserved without silent truncation in _rollup_multi_claim_audit_trail & verify_article
        db = str(tmp_path / "rollup30.db")
        tracker = GdeltUsageTracker(db_path=db)
        cache = ExternalEvidenceCache(db_path=db)
        fc_sess = MagicMock()
        fc_sess.get.return_value = MagicMock(status_code=200, ok=True, json=lambda: {"claims": []})
        gd_sess = MagicMock()
        gd_sess.get.return_value = MagicMock(status_code=200, ok=True, json=lambda: {"articles": []})

        orig_agg = svc.external_aggregator
        try:
            svc.external_aggregator = ExternalEvidenceAggregator(
                fact_check_client=GoogleFactCheckClient(cache=cache, session=fc_sess),
                gdelt_client=GdeltClient(tracker=tracker, cache=cache, session=gd_sess),
            )
            five_claim_text = (
                "Paris is the capital of France. "
                "Neil Armstrong walked on the Moon in July 1969. "
                "Barack Obama served as the 44th President of the United States. "
                "Albert Einstein developed the theory of relativity in Europe. "
                "The Pacific Ocean is the largest oceanic division on Earth."
            )
            r_5 = client.post(
                "/api/v1/verify/article",
                json={"title": "Five Claim Rollup Stress Test", "text": five_claim_text, "max_claims": 5},
            )
            assert r_5.status_code == 200
            audit_5 = r_5.json()["evidence_audit_trail"]
            assert audit_5["total_retrieval_attempts"] == len(audit_5["retrieval_attempts"])
            assert audit_5["total_retrieval_attempts"] > 30
            assert audit_5["omitted_retrieval_attempts"] == 0
        finally:
            svc.external_aggregator = orig_agg

    def test_single_tier2_source_and_same_page_passages_cannot_force_genuine(self):
        evaluator = SecondPassEvaluator()
        claim = "Helios Research Center operates a solar observatory in Chile."

        def _run_t2(docs):
            p1 = VerdictSynthesizer().synthesize(claim, docs)
            dq = build_directional_queries(claim)
            init = InitialMLSignals(
                liar_signal=ModelSignalRecord(model_name="liar", dataset_origin="LIAR", applicable_input_type="short_claim", applicable=True, prediction="true", preliminary_verdict_tag="GENUINE"),
                isot_signal=ModelSignalRecord(model_name="isot", dataset_origin="ISOT", applicable_input_type="full_article", applicable=False),
                preliminary_verdict="GENUINE",
            )
            return evaluator.evaluate(
                claim=claim,
                initial_signals=init,
                directional_queries=dq,
                documentary_evidence=docs,
                phase1_synthesis=p1,
                retrieval_meta={"wikipedia_status": "ok"},
            )

        # 1. Single strong Wikipedia passage cannot force GENUINE
        one_wiki = _mk_verified(
            claim_text=claim,
            page="Helios Research Center",
            text="Helios Research Center operates a high-altitude solar observatory in Chile.",
            sim=0.92,
            nli_label="SUPPORTS",
            sup=0.99,
            ref=0.01,
            source_type="wikipedia_live",
            sentence_id=0,
        )
        res_one, audit_one = _run_t2([one_wiki])
        assert res_one.verdict == "UNVERIFIED"
        assert audit_one.evidence_quality_summary.independent_supporting_sources == 1

        # 2. Multiple passages from SAME underlying Wikipedia page + FEVER mirror still count as 1 underlying source -> UNVERIFIED
        second_same_page = _mk_verified(
            claim_text=claim,
            page="Helios Research Center",
            text="The Helios Research Center solar observatory facility opened in Chile in 2014.",
            sim=0.90,
            nli_label="SUPPORTS",
            sup=0.98,
            ref=0.02,
            source_type="fever_local",
            sentence_id=1,
        )
        res_same, audit_same = _run_t2([one_wiki, second_same_page])
        assert res_same.verdict == "UNVERIFIED"
        assert audit_same.evidence_quality_summary.independent_supporting_sources == 1

        # 3. Offline single-Tier-2 Baptists claim (only 1 underlying FEVER page) returns UNVERIFIED end-to-end
        r_single = client.post(
            "/api/v1/verify/text",
            json={"claim": "19 Kids and Counting: The reality show focused on the life of the Duggar family who are devout Baptists.", "top_k": 5},
        )
        assert r_single.status_code == 200
        assert r_single.json()["verdict"] == "UNVERIFIED"

    def test_second_pass_case_precedence_tier1_vs_tier3_claimreviews_and_outdated(self):
        helper = TestTieredSufficiencyAndQualityGates()

        # 1. Qualifying Tier 1 official support vs SINGLE Tier 3 ClaimReview contradiction stays GENUINE (conflict noted)
        t1_claim = "FDA officially approved Drug Vexel-2026 under clinical dossier NDA-909 in July 2026."
        t1_doc = _mk_verified(
            claim_text=t1_claim,
            page="FDA NDA-909 Approval Letter",
            text="On July 18, 2026, FDA officially approved Drug Vexel-2026 under clinical dossier NDA-909 following phase 3 review.",
            sim=0.92,
            nli_label="SUPPORTS",
            sup=0.99,
            ref=0.01,
            source_type="official_record",
            source_url="https://www.fda.gov/drugs/nda-909",
            pub_date="2026-07-18",
        )
        res_t1_1fc, audit_t1_1fc = helper._run_second_pass(
            claim=t1_claim,
            initial_verdict="UNVERIFIED",
            doc_ev=[t1_doc],
            fc_matches=[_mock_fc_match("Single Reviewer", "False", t1_claim, "Single Reviewer disputes FDA Drug Vexel-2026 NDA-909 approval")],
        )
        assert res_t1_1fc.verdict == "GENUINE"
        assert audit_t1_1fc.conflicts_detected is True
        assert audit_t1_1fc.evidence_quality_summary.tier1_official_primary_count == 1

        # 2. Two independent Tier 3 ClaimReviews "True" WITHOUT Tier 1/Tier 2 CANNOT establish GENUINE
        claim_fc_only = "Aurora Labs commissioned a geothermal plant in Zurich in 2026."
        res_2fc_sup, audit_2fc_sup = helper._run_second_pass(
            claim=claim_fc_only,
            initial_verdict="GENUINE",
            fc_matches=[
                _mock_fc_match("Publisher One", "True", claim_fc_only, "Aurora Labs geothermal plant Zurich verified"),
                _mock_fc_match("Publisher Two", "True", claim_fc_only, "Aurora Labs Zurich geothermal plant confirmed"),
            ],
        )
        assert res_2fc_sup.verdict == "UNVERIFIED"
        assert audit_2fc_sup.evidence_quality_summary.tier1_official_primary_count == 0
        assert audit_2fc_sup.evidence_quality_summary.primary_official_sources_available is False

        # 3. Official-record claim with NO Tier 1 and >=2 independent ClaimReview refutations -> FAKE (with tier1 count still 0)
        hoax_claim = "Leaked confidential memo revealed Pentagon dismantled NORAD radar in 2026."
        res_hoax_ref, audit_hoax_ref = helper._run_second_pass(
            claim=hoax_claim,
            initial_verdict="UNVERIFIED",
            fc_matches=[
                _mock_fc_match("PolitiFact", "False", hoax_claim, "No leaked confidential memo exists about Pentagon dismantling NORAD radar"),
                _mock_fc_match("FactCheck.org", "False", hoax_claim, "Fabricated claim regarding leaked Pentagon NORAD memo debunked"),
            ],
        )
        assert res_hoax_ref.verdict == "FAKE"
        assert audit_hoax_ref.evidence_quality_summary.tier1_official_primary_count == 0
        assert audit_hoax_ref.evidence_quality_summary.primary_official_sources_available is False

        # 4. Outdated claim stays OUTDATED when resolved cleanly, but yields UNVERIFIED if credible ClaimReviews conflict
        liz_claim = "Queen Elizabeth II is the current reigning monarch of the United Kingdom."
        live_end = _mk_verified(
            claim_text=liz_claim,
            page="Elizabeth II",
            text="Elizabeth II (21 April 1926 - 8 September 2022) was Queen of the United Kingdom from 1952 until her death in 2022.",
            sim=0.88,
            nli_label="REFUTES",
            sup=0.01,
            ref=0.99,
            source_type="wikipedia_live",
        )
        res_out_ok, _ = helper._run_second_pass(claim=liz_claim, initial_verdict="GENUINE", doc_ev=[live_end], ret_meta={"wikipedia_status": "ok"})
        assert res_out_ok.verdict == "OUTDATED"

        res_out_conflict, _ = helper._run_second_pass(
            claim=liz_claim,
            initial_verdict="GENUINE",
            doc_ev=[live_end],
            ret_meta={"wikipedia_status": "ok"},
            fc_matches=[
                _mock_fc_match("Checker A", "True", liz_claim, "Elizabeth II UK monarch current check"),
                _mock_fc_match("Checker B", "False", liz_claim, "Elizabeth II UK monarch died 2022 check", is_conflicting=True),
            ],
            ext_meta={"has_conflicting_fact_checks": True},
        )
        assert res_out_conflict.verdict == "UNVERIFIED"

        # 5. Established pre-2017 historical closure stays OUTDATED even with only 2017 FEVER evidence offline
        obama_claim = "Barack Obama is the current President of the United States."
        obama_stale_sup = _mk_verified(
            claim_text=obama_claim,
            page="Barack Obama",
            text="Obama, a Democrat, took office as the 44th United States president following a decisive victory over John McCain.",
            sim=0.79,
            nli_label="SUPPORTS",
            sup=0.95,
            ref=0.03,
            source_type="fever_local",
            pub_date="2017-06 (FEVER Wikipedia Corpus)",
            sentence_id=1,
        )
        obama_ended = _mk_verified(
            claim_text=obama_claim,
            page="Barack Obama",
            text="Barack Hussein Obama II served as the 44th president of the United States from 2009 to 2017 and was succeeded by Donald Trump.",
            sim=0.86,
            nli_label="REFUTES",
            sup=0.01,
            ref=0.99,
            source_type="fever_local",
            pub_date="2017-06 (FEVER Wikipedia Corpus)",
            sentence_id=2,
        )
        res_obama_off, audit_obama_off = helper._run_second_pass(
            claim=obama_claim,
            initial_verdict="GENUINE",
            doc_ev=[obama_stale_sup, obama_ended],
            ret_meta={"wikipedia_status": "offline"},
        )
        assert res_obama_off.verdict == "OUTDATED"
        assert audit_obama_off.final_verdict == "OUTDATED"

    def test_outdated_obama_presidency_and_unsupported_claim_offline(self, tmp_path):
        from ml.rag.wikipedia_fallback import WikipediaRetrievalResult, get_wikipedia_fallback

        db = str(tmp_path / "ieve_outdated_api.db")
        tracker = GdeltUsageTracker(db_path=db)
        cache = ExternalEvidenceCache(db_path=db)
        fc_sess = MagicMock()
        fc_sess.get.return_value = MagicMock(status_code=200, ok=True, json=lambda: {"claims": []})
        gd_sess = MagicMock()
        gd_sess.get.return_value = MagicMock(status_code=200, ok=True, json=lambda: {"articles": []})

        svc = verification_service.get_verification_service()
        orig_agg = svc.external_aggregator
        wiki = get_wikipedia_fallback()
        try:
            svc.external_aggregator = ExternalEvidenceAggregator(
                fact_check_client=GoogleFactCheckClient(cache=cache, session=fc_sess),
                gdelt_client=GdeltClient(tracker=tracker, cache=cache, session=gd_sess),
            )
            with patch.object(
                wiki,
                "retrieve_with_status",
                return_value=WikipediaRetrievalResult(hits=[], status="offline"),
            ):
                resp_obama = client.post(
                    "/api/v1/verify/text",
                    json={"claim": "Barack Obama is the current President of the United States.", "top_k": 5},
                )
                assert resp_obama.status_code == 200
                data_obama = resp_obama.json()
                assert data_obama["verdict"] == "OUTDATED"
                assert data_obama["evidence_audit_trail"]["final_verdict"] == "OUTDATED"

                resp_unsup = client.post(
                    "/api/v1/verify/text",
                    json={"claim": "Biologists discovered alien potatoes on Pluto in 2026.", "top_k": 5},
                )
                assert resp_unsup.status_code == 200
                data_unsup = resp_unsup.json()
                assert data_unsup["verdict"] == "UNVERIFIED"
                assert data_unsup["evidence_audit_trail"]["final_verdict"] == "UNVERIFIED"
        finally:
            svc.external_aggregator = orig_agg
        # Mocked temp tracker recorded 1 balanced neutral GDELT request per claim (zero live calls)
        assert tracker.get_status().requests_used == 2

    def test_ordinal_orbital_reversals_and_multi_claim_isolation_offline(self, tmp_path):
        from ml.rag.wikipedia_fallback import WikipediaRetrievalResult, get_wikipedia_fallback

        db = str(tmp_path / "ieve_ordinal_orbital.db")
        tracker = GdeltUsageTracker(db_path=db)
        cache = ExternalEvidenceCache(db_path=db)
        fc_sess = MagicMock()
        fc_sess.get.return_value = MagicMock(status_code=200, ok=True, json=lambda: {"claims": []})
        gd_sess = MagicMock()
        gd_sess.get.return_value = MagicMock(status_code=200, ok=True, json=lambda: {"articles": []})

        svc = verification_service.get_verification_service()
        orig_agg = svc.external_aggregator
        wiki = get_wikipedia_fallback()
        try:
            svc.external_aggregator = ExternalEvidenceAggregator(
                fact_check_client=GoogleFactCheckClient(cache=cache, session=fc_sess),
                gdelt_client=GdeltClient(tracker=tracker, cache=cache, session=gd_sess),
            )
            with patch.object(
                wiki,
                "retrieve_with_status",
                return_value=WikipediaRetrievalResult(hits=[], status="offline"),
            ):
                r_earth = client.post(
                    "/api/v1/verify/text",
                    json={"claim": "The Earth is the fourth planet from the Sun.", "top_k": 5},
                )
                assert r_earth.status_code == 200
                assert r_earth.json()["verdict"] == "FAKE"

                r_sun = client.post(
                    "/api/v1/verify/text",
                    json={"claim": "The Sun revolves around the Earth.", "top_k": 5},
                )
                assert r_sun.status_code == 200
                sun_data = r_sun.json()
                # Corroborated directional orbital reversal across >=2 independent Tier 2 sources produces FAKE
                assert sun_data["verdict"] == "FAKE"
                sun_summary = sun_data["evidence_audit_trail"]["evidence_quality_summary"]
                assert sun_summary["support_count"] == 0
                assert sun_summary["contradict_count"] >= 3
                assert sun_summary["independent_contradicting_sources"] >= 2
                sun_cons = sun_data["evidence_audit_trail"]["contradicting_evidence"]
                assert any(
                    c["ml_nli_label"] == "REFUTES"
                    and c["ml_nli_probabilities"]["supports"] >= 0.90
                    and c["ml_nli_probabilities"]["refutes"] <= 0.05
                    and 0.55 <= c["contradiction_strength"] < 0.65
                    for c in sun_cons
                )

                r_true_orbit = client.post(
                    "/api/v1/verify/text",
                    json={"claim": "The Earth revolves around the Sun.", "top_k": 5},
                )
                assert r_true_orbit.status_code == 200
                assert r_true_orbit.json()["verdict"] == "GENUINE"

                r_unrelated = client.post(
                    "/api/v1/verify/text",
                    json={"claim": "The Moon is made entirely of cheese.", "top_k": 5},
                )
                assert r_unrelated.status_code == 200
                assert r_unrelated.json()["verdict"] == "UNVERIFIED"

                r_india = client.post(
                    "/api/v1/verify/text",
                    json={"claim": "India is located in South America.", "top_k": 5},
                )
                assert r_india.status_code == 200
                assert r_india.json()["verdict"] == "FAKE"

                # Multi-claim isolation remains intact across ordinal + genuine claims
                r_art = client.post(
                    "/api/v1/verify/article",
                    json={
                        "title": "Planetary and Geography Check",
                        "text": (
                            "The Earth is the fourth planet from the Sun. "
                            "Paris is the capital of France."
                        ),
                        "max_claims": 2,
                    },
                )
                assert r_art.status_code == 200
                d_art = r_art.json()
                assert d_art["overall_verdict"] == "PARTIALLY_TRUE"
                assert len(d_art["extracted_claims"]) == 2
                verdicts_by_claim = {c["claim"]: c["verdict"] for c in d_art["extracted_claims"]}
                assert any("fourth planet" in k and v == "FAKE" for k, v in verdicts_by_claim.items())
                assert any("Paris is the capital of France" in k and v == "GENUINE" for k, v in verdicts_by_claim.items())
                # Verify per-claim evidence isolation (no cross-claim page contamination)
                for ec in d_art["extracted_claims"]:
                    pages = " ".join(ev["page"].lower() for ev in ec["evidence"])
                    if "Paris" in ec["claim"]:
                        assert "planet" not in pages
                    if "fourth planet" in ec["claim"]:
                        assert "paris" not in pages
        finally:
            svc.external_aggregator = orig_agg

    def test_directional_contradiction_strength_safeguards_and_independence(self):
        """
        Verify EvidenceQuality contradiction_strength respects:
          - Raw NLI probabilities vs calibrated REFUTES label distinction
          - Conservative cap (<0.65) so 1 uncorroborated Tier 2 override remains UNVERIFIED
          - >=2 independent Tier 2 sources produce FAKE via SecondPassEvaluator
          - Arbitrary/low-relevance/missing-entity/missing/unrelated evidence stays conservative
        """
        evaluator = SecondPassEvaluator()
        synth = VerdictSynthesizer()
        sun_claim = "The Sun revolves around the Earth."
        init_sig = InitialMLSignals(
            liar_signal=ModelSignalRecord(
                model_name="BERT-LIAR",
                dataset_origin="LIAR",
                applicable_input_type="short_claim",
                applicable=True,
                prediction="FALSE",
                confidence=0.80,
                probabilities={"false": 0.80, "true": 0.20},
                preliminary_verdict_tag="FAKE",
                disclaimer="Mock LIAR signal",
            ),
            isot_signal=ModelSignalRecord(
                model_name="isot",
                dataset_origin="ISOT",
                applicable_input_type="full_article",
                applicable=False,
            ),
            preliminary_verdict="FAKE",
        )

        def _eval(claim_str: str, docs):
            p1 = synth.synthesize(claim_str, docs)
            dq = build_directional_queries(claim_str)
            return evaluator.evaluate(
                claim=claim_str,
                initial_signals=init_sig,
                directional_queries=dq,
                phase1_synthesis=p1,
                documentary_evidence=docs,
                retrieval_meta={"wikipedia_status": "offline"},
                external_meta={"google_status": "no_results", "gdelt_status": "ok"},
            )

        ev_orbit = _mk_verified(
            claim_text=sun_claim,
            page="Earth's orbit",
            text="Earth's orbit is the path through which the Earth travels around the Sun.",
            sim=0.92,
            nli_label="SUPPORTS",
            raw_label="SUPPORTS",
            sup=0.9987,
            ref=0.0013,
            nei=0.0,
            source_type="fever_local",
            doc_id="orbit_high",
        )
        ev_sun = _mk_verified(
            claim_text=sun_claim,
            page="Sun",
            text="The Earth revolves around the Sun every year in an elliptical orbit.",
            sim=0.71,
            nli_label="SUPPORTS",
            raw_label="SUPPORTS",
            sup=0.9990,
            ref=0.0010,
            nei=0.0,
            source_type="fever_local",
            doc_id="sun_orbit",
            sentence_id=4,
        )

        # Raw probability distinction preserved & strength bounded <0.65 so 1 source stays UNVERIFIED
        q_orbit = evaluate_documentary_evidence(sun_claim, ev_orbit)
        assert q_orbit.stance == "contradicting"
        assert q_orbit.ml_nli_label == "REFUTES"
        assert q_orbit.ml_nli_probabilities["refutes"] == 0.0013
        assert q_orbit.ml_nli_probabilities["supports"] == 0.9987
        assert 0.55 <= q_orbit.contradiction_strength <= 0.64

        ev_orbit_copy = VerifiedEvidence(**{**ev_orbit.__dict__, "nli_label": "SUPPORTS", "evidence_role": "contextual", "alignment_notes": ""})
        res_single, _ = _eval(sun_claim, [ev_orbit_copy])
        assert res_single.verdict == "UNVERIFIED"

        # 2 independent Tier 2 sources corroborate directional reversal -> FAKE
        ev_o2 = VerifiedEvidence(**{**ev_orbit.__dict__, "nli_label": "SUPPORTS", "evidence_role": "contextual", "alignment_notes": ""})
        ev_s2 = VerifiedEvidence(**{**ev_sun.__dict__, "nli_label": "SUPPORTS", "evidence_role": "contextual", "alignment_notes": ""})
        res_multi, audit_multi = _eval(sun_claim, [ev_o2, ev_s2])
        assert res_multi.verdict == "FAKE"
        assert audit_multi.evidence_quality_summary.independent_contradicting_sources == 2

        # Low-relevance / missing-entity / non-directional alignment overrides stay conservative
        ev_weak_sim = _mk_verified(
            claim_text=sun_claim,
            page="Earth's orbit",
            text="The Earth revolves around the Sun every astronomical year in an elliptical orbit.",
            sim=0.49,
            nli_label="SUPPORTS",
            raw_label="SUPPORTS",
            sup=0.99,
            ref=0.01,
            nei=0.0,
            source_type="fever_local",
            doc_id="orbit_weak_sim",
            sentence_id=8,
        )
        q_weak = evaluate_documentary_evidence(sun_claim, ev_weak_sim)
        assert q_weak.contradiction_strength < 0.55

        ev_mismatched_entity = _mk_verified(
            claim_text=sun_claim,
            page="Venus",
            text="Venus revolves around the Sun.",
            sim=0.75,
            nli_label="SUPPORTS",
            raw_label="SUPPORTS",
            sup=0.99,
            ref=0.01,
            nei=0.0,
            source_type="fever_local",
            doc_id="venus_0",
            sentence_id=1,
        )
        q_mismatch = evaluate_documentary_evidence(sun_claim, ev_mismatched_entity)
        assert q_mismatch.is_relevant is False
        assert q_mismatch.contradiction_strength == 0.0

        # Non-directional slot override with low raw refutes is NOT boosted automatically
        ev_non_dir = _mk_verified(
            claim_text="India is located in South America.",
            page="India",
            text="India is a country in South Asia.",
            sim=0.70,
            nli_label="SUPPORTS",
            raw_label="SUPPORTS",
            sup=0.99,
            ref=0.01,
            nei=0.0,
            source_type="fever_local",
            doc_id="india_non_dir",
        )
        q_non_dir = evaluate_documentary_evidence("India is located in South America.", ev_non_dir)
        assert q_non_dir.ml_nli_label == "REFUTES"
        assert q_non_dir.contradiction_strength < 0.55

        # Missing & unrelated evidence stay UNVERIFIED
        res_missing, _ = _eval(sun_claim, [])
        assert res_missing.verdict == "UNVERIFIED"

        cheese_ev = _mk_verified(
            claim_text="The Moon is made entirely of cheese.",
            page="Cheese",
            text="Cheese is a dairy food produced from milk.",
            sim=0.52,
            nli_label="REFUTES",
            raw_label="REFUTES",
            sup=0.01,
            ref=0.99,
            nei=0.0,
            source_type="fever_local",
            doc_id="cheese_unrel",
        )
        res_unrel, _ = _eval("The Moon is made entirely of cheese.", [cheese_ev])
        assert res_unrel.verdict == "UNVERIFIED"
