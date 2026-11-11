"""
backend/tests/test_verdict_classification.py
Tests targeting every root cause diagnosed in the Six-Class Verdict Audit:
  1. DeBERTa binary-collapse safeguard (NOT ENOUGH INFO calibration on unrelated/non-contradictory evidence)
  2. Stemming & numeric token normalization ("Water freezes at 0 degrees Celsius")
  3. Primary subject entity gate (preventing unrelated article matches like Martin Van Buren / Peter Sarsgaard)
  4. Compound claim splitting & article aggregation -> PARTIALLY_TRUE
  5. Temporal & rebrand reasoning -> OUTDATED vs GENUINE
  6. Public Wikipedia API fallback domain allowlisting & graceful offline/timeout handling
  7. Legacy SQLite / Sepolia canonical hash preservation & history filter aliasing
"""

from unittest.mock import patch
import requests
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.database.repository import get_verification_record, list_verification_records
from backend.app.schemas.verification import VerdictEnum
from backend.app.services.verification_service import _aggregate_multi_claim_verdicts
from ml.inference.claim_verifier import VerifiedEvidence
from ml.inference.evidence_alignment import (
    evaluate_evidence_alignment,
    extract_subject_entities,
    split_compound_claims,
)
from ml.inference.verdict_synthesizer import SynthesisResult, VerdictSynthesizer
from ml.rag.wikipedia_fallback import (
    build_wikipedia_search_queries,
    get_wikipedia_fallback,
    is_allowlisted_wikipedia_url,
)

client = TestClient(app)


def test_wikipedia_allowlist_ssrf_guard():
    """Verify strict HTTPS en.wikipedia.org domain allowlisting."""
    assert is_allowlisted_wikipedia_url("https://en.wikipedia.org/w/api.php")
    assert is_allowlisted_wikipedia_url("https://en.wikipedia.org/wiki/Barack_Obama")
    assert not is_allowlisted_wikipedia_url("http://en.wikipedia.org/wiki/Barack_Obama")
    assert not is_allowlisted_wikipedia_url("https://127.0.0.1/w/api.php")
    assert not is_allowlisted_wikipedia_url("https://evil.example.com/en.wikipedia.org")


def test_wikipedia_fallback_graceful_offline_handling():
    """Verify timeouts or connection failures degrade gracefully without raising exceptions."""
    wiki = get_wikipedia_fallback()
    with patch.object(wiki._session, "get", side_effect=requests.Timeout("Simulated timeout")):
        hits = wiki.retrieve("Unique Test Query 999888 XYZ", top_k=3)
    assert hits == []
    assert wiki.last_status == "timeout"


def test_deberta_binary_collapse_safeguard_abstain_to_nei():
    """
    When DeBERTa outputs raw REFUTES (~96%) on unrelated text or non-contradictory omissions,
    alignment calibration must downgrade to NOT ENOUGH INFO rather than polluting REFUTES.
    """
    unrelated_ev = VerifiedEvidence(
        rank=1,
        page="Banana",
        sentence_id=0,
        doc_id="test_1",
        text="Bananas are yellow tropical fruit grown in warm climates.",
        retrieval_similarity=0.52,
        nli_label="REFUTES",
        nli_confidence=0.9632,
        nli_probabilities={"supports": 0.0368, "refutes": 0.9632, "not_enough_info": 0.0},
        raw_nli_label="REFUTES",
    )
    assmt = evaluate_evidence_alignment("Water boils at 100 degrees Celsius.", unrelated_ev)
    assert assmt.calibrated_nli == "NOT ENOUGH INFO"
    assert assmt.evidence_role == "contextual"

    # Subject-matched but non-contradictory omission (Neil Armstrong commander sentence vs walked on Moon)
    omission_ev = VerifiedEvidence(
        rank=2,
        page="Neil Armstrong",
        sentence_id=3,
        doc_id="test_2",
        text="Armstrong's second and last spaceflight was as commander of Apollo 11.",
        retrieval_similarity=0.68,
        nli_label="REFUTES",
        nli_confidence=0.9900,
        nli_probabilities={"supports": 0.0100, "refutes": 0.9900, "not_enough_info": 0.0},
        raw_nli_label="REFUTES",
    )
    assmt2 = evaluate_evidence_alignment("Neil Armstrong walked on the Moon.", omission_ev)
    assert assmt2.calibrated_nli == "NOT ENOUGH INFO"
    assert assmt2.evidence_role == "contextual"


def test_subject_entity_mismatch_prevents_false_support():
    """Martin Van Buren sentence must not verify or refute an Albert Einstein claim."""
    ev = VerifiedEvidence(
        rank=1,
        page="Martin Van Buren",
        sentence_id=1,
        doc_id="test_3",
        text="He was the first president to be born a United States citizen.",
        retrieval_similarity=0.63,
        nli_label="SUPPORTS",
        nli_confidence=0.9994,
        nli_probabilities={"supports": 0.9994, "refutes": 0.0006, "not_enough_info": 0.0},
        raw_nli_label="SUPPORTS",
    )
    assmt = evaluate_evidence_alignment("Albert Einstein was the first President of the United States.", ev)
    assert assmt.missing_primary_entity is True
    assert assmt.calibrated_nli == "NOT ENOUGH INFO"


def test_temporal_outdated_vs_active_office_nuance():
    """
    'Barack Obama is the current President' -> OUTDATED.
    Historical unrelated office ('Chief Minister 2001-2014') must NOT override active PM tenure -> GENUINE.
    """
    synth = VerdictSynthesizer()

    obama_ev = [
        VerifiedEvidence(
            rank=1,
            page="Barack Obama",
            sentence_id=0,
            doc_id="obama_0",
            text="Barack Hussein Obama II is an American politician who served as the 44th president of the United States from 2009 to 2017.",
            retrieval_similarity=0.81,
            nli_label="SUPPORTS",
            nli_confidence=0.98,
            nli_probabilities={"supports": 0.98, "refutes": 0.02, "not_enough_info": 0.0},
            raw_nli_label="SUPPORTS",
            source_type="wikipedia_live",
            source_url="https://en.wikipedia.org/wiki/Barack_Obama",
            publication_date="2026-11-11T05:17:22Z",
        )
    ]
    res_obama = synth.synthesize("Barack Obama is the current President of the United States.", obama_ev)
    assert res_obama.verdict == "OUTDATED"

    modi_ev = [
        VerifiedEvidence(
            rank=1,
            page="Narendra Modi",
            sentence_id=0,
            doc_id="modi_0",
            text="Narendra Damodardas Modi is an Indian politician who has served as the prime minister of India since 26 May 2014.",
            retrieval_similarity=0.82,
            nli_label="SUPPORTS",
            nli_confidence=0.999,
            nli_probabilities={"supports": 0.999, "refutes": 0.001, "not_enough_info": 0.0},
            raw_nli_label="SUPPORTS",
            source_type="wikipedia_live",
            source_url="https://en.wikipedia.org/wiki/Narendra_Modi",
            publication_date="2026-11-10T21:32:11Z",
        ),
        VerifiedEvidence(
            rank=2,
            page="Narendra Modi",
            sentence_id=1,
            doc_id="modi_1",
            text="Modi was the chief minister of Gujarat from 2001 to 2014.",
            retrieval_similarity=0.65,
            nli_label="REFUTES",
            nli_confidence=0.95,
            nli_probabilities={"supports": 0.05, "refutes": 0.95, "not_enough_info": 0.0},
            raw_nli_label="REFUTES",
            source_type="wikipedia_live",
            source_url="https://en.wikipedia.org/wiki/Narendra_Modi",
            publication_date="2026-11-10T21:32:11Z",
        ),
    ]
    res_modi = synth.synthesize("Narendra Modi is the current Prime Minister of India.", modi_ev)
    assert res_modi.verdict == "GENUINE"


def test_compound_claim_splitting_and_partially_true_endpoint():
    """Verify compound claims split with pronoun propagation and classify PARTIALLY_TRUE end-to-end."""
    clauses = split_compound_claims(
        "Albert Einstein developed the theory of relativity, and he was the first President of the United States."
    )
    assert len(clauses) == 2
    assert "Albert Einstein" in clauses[1]

    resp = client.post(
        "/api/v1/verify/text",
        json={
            "claim": "Paris is the capital of France, and Apollo 11 landed on Mars in 1969.",
            "top_k": 4,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["verdict"] == "PARTIALLY_TRUE"
    assert len(data["claim_verdicts"]) == 2
    sub_verdicts = {c["verdict"] for c in data["claim_verdicts"]}
    assert "GENUINE" in sub_verdicts
    assert "FAKE" in sub_verdicts


def test_article_partially_true_endpoint():
    """Verify article combining true and false claims classifies PARTIALLY_TRUE."""
    resp = client.post(
        "/api/v1/verify/article",
        json={
            "title": "Mixed Duggar Documentary Facts",
            "text": (
                "19 Kids and Counting is an American reality television show featuring the Duggar family. "
                "However, 19 Kids and Counting was cancelled in 2030 after decades on television."
            ),
            "max_claims": 2,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["overall_verdict"] == "PARTIALLY_TRUE"
    assert len(data["extracted_claims"]) == 2


def test_legacy_sepolia_record_and_history_alias_compatibility():
    """
    Ensure confirmed Sepolia record verif-9c524ca7b6f5 retains its original canonical verdict & SHA-256,
    and querying history by 'GENUINE' includes both 'GENUINE' and legacy 'LIKELY_GENUINE' records.
    """
    rec = get_verification_record("verif-9c524ca7b6f5")
    assert rec is not None
    assert rec["verdict"] == "LIKELY_GENUINE"
    assert rec["record_hash"] == "42007960ae4bf66cbc74dfb24ef80429fdba86ca34de3bc1a8d0ff9c16a2cc53"

    rows, total = list_verification_records(verdict="GENUINE", limit=100)
    assert total >= 1
    verdict_set = {r["verdict"] for r in rows}
    assert verdict_set.issubset({"GENUINE", "LIKELY_GENUINE"})


def test_pathogen_and_singleton_exclusivity_alignment():
    """
    Verify biologically exclusive pathogen conflict (coronavirus vs bacterial) -> REFUTES -> FAKE,
    and singleton exclusivity vs multiplicity ('only astronaut' vs 'two humans') -> REFUTES -> MISLEADING.
    """
    synth = VerdictSynthesizer()

    covid_ev = [
        VerifiedEvidence(
            rank=1,
            page="COVID-19",
            sentence_id=0,
            doc_id="covid_0",
            text="Coronavirus disease 2019 (COVID-19) is a contagious disease caused by the coronavirus SARS-CoV-2.",
            retrieval_similarity=0.72,
            nli_label="REFUTES",
            nli_confidence=0.9989,
            nli_probabilities={"supports": 0.0011, "refutes": 0.9989, "not_enough_info": 0.0},
            raw_nli_label="REFUTES",
            source_type="wikipedia_live",
            source_url="https://en.wikipedia.org/wiki/COVID-19",
            publication_date="2026-11-07T12:20:24Z",
        )
    ]
    res_covid = synth.synthesize("COVID-19 is caused by a bacterial infection.", covid_ev)
    assert res_covid.verdict == "FAKE"

    apollo_ev = [
        VerifiedEvidence(
            rank=1,
            page="Apollo 11",
            sentence_id=0,
            doc_id="apollo_0",
            text="Apollo 11 was the spaceflight that landed the first two humans on the Moon.",
            retrieval_similarity=0.65,
            nli_label="REFUTES",
            nli_confidence=0.9984,
            nli_probabilities={"supports": 0.0016, "refutes": 0.9984, "not_enough_info": 0.0},
            raw_nli_label="REFUTES",
            source_type="fever_local",
        )
    ]
    res_apollo = synth.synthesize("Neil Armstrong was the only astronaut on Apollo 11.", apollo_ev)
    assert res_apollo.verdict == "MISLEADING"


def test_ordinal_office_holder_replacement_and_true_support():
    """
    Verify unique ordinal office holder conflict ('Einstein was first President of US' vs George Washington) -> FAKE,
    while matching subject ('George Washington was the first President of the US') -> GENUINE.
    """
    synth = VerdictSynthesizer()
    gw_ev = [
        VerifiedEvidence(
            rank=1,
            page="George Washington",
            sentence_id=0,
            doc_id="gw_0",
            text="George Washington was a Founding Father and the first president of the United States, serving from 1789 to 1797.",
            retrieval_similarity=0.62,
            nli_label="REFUTES",
            nli_confidence=0.99,
            nli_probabilities={"supports": 0.01, "refutes": 0.99, "not_enough_info": 0.0},
            raw_nli_label="REFUTES",
            source_type="wikipedia_live",
            source_url="https://en.wikipedia.org/wiki/George_Washington",
            publication_date="2026-11-01T00:00:00Z",
        )
    ]
    res_fake = synth.synthesize("Albert Einstein was the first President of the United States.", gw_ev)
    assert res_fake.verdict == "FAKE"

    gw_true_ev = [
        VerifiedEvidence(
            rank=1,
            page="George Washington",
            sentence_id=0,
            doc_id="gw_true",
            text="George Washington was a Founding Father and the first president of the United States, serving from 1789 to 1797.",
            retrieval_similarity=0.85,
            nli_label="SUPPORTS",
            nli_confidence=0.998,
            nli_probabilities={"supports": 0.998, "refutes": 0.002, "not_enough_info": 0.0},
            raw_nli_label="SUPPORTS",
            source_type="wikipedia_live",
        )
    ]
    res_true = synth.synthesize("George Washington was the first President of the United States.", gw_true_ev)
    assert res_true.verdict == "GENUINE"


def test_wikipedia_query_builder_prioritizes_mid_sentence_and_ordinal_entities():
    """Verify non-initial proper nouns ('Celsius') and ordinal office phrases appear in search queries."""
    water_queries = build_wikipedia_search_queries("Water freezes at 0 degrees Celsius.")
    assert any(q.lower() == "celsius" for q in water_queries)
    assert all(not q.endswith(".") for q in water_queries)

    einstein_queries = build_wikipedia_search_queries("Albert Einstein was the first President of the United States.")
    assert any("first president of the united states" in q.lower() for q in einstein_queries)


def test_correction1_syntactic_clause_splitting():
    """
    Validate syntactic Subject+Predicate clause validation:
      - Rejects coordinated noun lists (even ending in -s / preceded by -ed modifiers)
      - Splits finite passive constructions cleanly while rejecting reduced participial modifiers
      - Splits compound sentences across non-whitelisted verbs
      - Resolves anaphoric subject pronouns cleanly while keeping expletive 'it' intact
    """
    # Coordinated noun lists -> MUST NOT SPLIT
    assert len(split_compound_claims("Alice, Bob, and Carol attended the summit in Geneva.")) == 1
    assert len(split_compound_claims("The committee evaluated physics, chemistry, and three other science prizes.")) == 1
    assert len(split_compound_claims("Developed nations, coastal cities, and island territories face flooding.")) == 1
    assert len(split_compound_claims("The museum displayed ancient coins, Roman statues, and medieval crowns.")) == 1

    # Passive constructions -> finite passives split; reduced participial modifiers do NOT
    passive_parts = split_compound_claims(
        "Penicillin was discovered by Alexander Fleming, whereas influenza is caused by a virus."
    )
    assert len(passive_parts) == 2
    assert len(split_compound_claims("Founded in 1975 and led by Bill Gates, Microsoft grew rapidly.")) == 1

    # Compound sentences & non-whitelisted verbs -> MUST SPLIT
    assert len(split_compound_claims("Tokyo is the capital city of Japan, and Mount Everest lies inside Brazil.")) == 2
    assert len(split_compound_claims("Photosynthesis converts sunlight into energy, while Jupiter orbits the Sun.")) == 2
    assert len(split_compound_claims("Hydrogen gas burns cleanly, and pure water boils at 100 degrees Celsius.")) == 2

    # Clauses containing pronouns -> split & resolve anaphoric subject, leave expletive 'it' uncorrupted
    pron_parts = split_compound_claims("Marie Curie isolated radium, and she won two Nobel Prizes.")
    assert len(pron_parts) == 2
    assert pron_parts[1].startswith("Marie Curie")

    the_pron_parts = split_compound_claims("The Titanic sank in 1912, and it remains an enduring tragedy.")
    assert len(the_pron_parts) == 2
    assert the_pron_parts[1].startswith("The Titanic")

    expletive_parts = split_compound_claims("The experiment failed, and it is widely believed that error contributed.")
    assert len(expletive_parts) == 2
    assert expletive_parts[1].lower().startswith("it is widely believed")

    # Sentences that must NOT split
    assert len(split_compound_claims("Although tired after the long climb, Edmund Hillary reached the summit.")) == 1
    assert len(split_compound_claims("Albert Einstein, who formulated relativity, was born in Germany.")) == 1
    assert len(split_compound_claims("Between 1914 and 1918, World War I reshaped modern Europe.")) == 1


def test_group_a_entity_subtype_namesake_and_possessive_guards():
    """Verify orthogonal subtypes, middle-initial namesakes, possessive heads, and topic nouns."""
    peace_ev = VerifiedEvidence(
        rank=1, page="Nobel Peace Prize", sentence_id=0, doc_id="peace_0",
        text="Marie Curie attended Oslo ceremonies related to Nobel prizes.",
        retrieval_similarity=0.72, nli_label="SUPPORTS", nli_confidence=0.80,
        nli_probabilities={"supports": 0.80, "refutes": 0.20, "not_enough_info": 0.0},
        raw_nli_label="SUPPORTS",
    )
    a_subtype = evaluate_evidence_alignment("Marie Curie won the Nobel Prize in Chemistry.", peace_ev)
    assert a_subtype.calibrated_nli == "NOT ENOUGH INFO"
    assert a_subtype.missing_primary_entity is True

    mark_s_ev = VerifiedEvidence(
        rank=1, page="Mark S. Zuckerberg", sentence_id=0, doc_id="msz_0",
        text="Mark S. Zuckerberg is an Indianapolis attorney sued in corporate name disputes.",
        retrieval_similarity=0.68, nli_label="REFUTES", nli_confidence=0.90,
        nli_probabilities={"supports": 0.10, "refutes": 0.90, "not_enough_info": 0.0},
        raw_nli_label="REFUTES",
    )
    a_namesake = evaluate_evidence_alignment("Facebook, Inc. is Mark Zuckerberg's social media company.", mark_s_ev)
    assert a_namesake.calibrated_nli == "NOT ENOUGH INFO"
    assert a_namesake.missing_primary_entity is True

    ents = extract_subject_entities("India's Chandrayaan-3 mission landed near the lunar south pole in August 2023.")
    assert ents[0].startswith("chandrayaan")

    reptile_ev = VerifiedEvidence(
        rank=1, page="Antarctica", sentence_id=0, doc_id="ant_0",
        text="Antarctica contains vast ice sheets across the Antarctic continent.",
        retrieval_similarity=0.72, nli_label="SUPPORTS", nli_confidence=0.85,
        nli_probabilities={"supports": 0.85, "refutes": 0.15, "not_enough_info": 0.0},
        raw_nli_label="SUPPORTS",
    )
    a_penguin = evaluate_evidence_alignment("All penguin species live exclusively on the Antarctic continent.", reptile_ev)
    assert a_penguin.calibrated_nli == "NOT ENOUGH INFO"


def test_group_c_temporal_noncontiguous_and_stale_fever_override():
    """
    Verify live Wikipedia overrides stale 2017 FEVER for expired monarchs/leaders/rebrands/World Cup,
    while non-contiguous sitting President Donald Trump remains GENUINE.
    """
    synth = VerdictSynthesizer()

    trump_ev = [
        VerifiedEvidence(
            rank=1, page="Donald Trump", sentence_id=0, doc_id="trump_0",
            text="Donald John Trump is an American politician, media personality, and businessman who is the 47th president of the United States.",
            retrieval_similarity=0.82, nli_label="SUPPORTS", nli_confidence=0.99,
            nli_probabilities={"supports": 0.99, "refutes": 0.01, "not_enough_info": 0.0},
            raw_nli_label="SUPPORTS", source_type="wikipedia_live",
            source_url="https://en.wikipedia.org/wiki/Donald_Trump", publication_date="2026-11-10T23:58:17Z",
        ),
        VerifiedEvidence(
            rank=2, page="Donald Trump", sentence_id=1, doc_id="trump_1",
            text="A member of the Republican Party, he served as the 45th president from 2017 to 2021.",
            retrieval_similarity=0.70, nli_label="REFUTES", nli_confidence=0.98,
            nli_probabilities={"supports": 0.02, "refutes": 0.98, "not_enough_info": 0.0},
            raw_nli_label="REFUTES", source_type="wikipedia_live",
            source_url="https://en.wikipedia.org/wiki/Donald_Trump", publication_date="2026-11-10T23:58:17Z",
        ),
    ]
    assert synth.synthesize("Donald Trump is the current President of the United States.", trump_ev).verdict == "GENUINE"

    liz_ev = [
        VerifiedEvidence(
            rank=1, page="Elizabeth II", sentence_id=0, doc_id="liz_local",
            text="Elizabeth II is the current reigning Queen of the United Kingdom and other Commonwealth realms.",
            retrieval_similarity=0.88, nli_label="SUPPORTS", nli_confidence=0.99,
            nli_probabilities={"supports": 0.99, "refutes": 0.01, "not_enough_info": 0.0},
            raw_nli_label="SUPPORTS", source_type="fever_local", publication_date="2017-06 (FEVER Wikipedia Corpus)",
        ),
        VerifiedEvidence(
            rank=2, page="Elizabeth II", sentence_id=0, doc_id="liz_live",
            text="Elizabeth II (21 April 1926 – 8 September 2022) was Queen of the United Kingdom and other Commonwealth realms from 6 February 1952 until her death in 2022.",
            retrieval_similarity=0.86, nli_label="REFUTES", nli_confidence=0.99,
            nli_probabilities={"supports": 0.01, "refutes": 0.99, "not_enough_info": 0.0},
            raw_nli_label="REFUTES", source_type="wikipedia_live",
            source_url="https://en.wikipedia.org/wiki/Elizabeth_II", publication_date="2026-11-10T16:51:29Z",
        ),
    ]
    assert synth.synthesize("Queen Elizabeth II is the current reigning monarch of the United Kingdom.", liz_ev).verdict == "OUTDATED"

    wc_ev = [
        VerifiedEvidence(
            rank=1, page="FIFA World Cup", sentence_id=0, doc_id="wc_0",
            text="The reigning champion is Spain, who won their second title at the 23rd edition of the competition, the 2026 World Cup, by defeating the holders, Argentina.",
            retrieval_similarity=0.79, nli_label="REFUTES", nli_confidence=0.99,
            nli_probabilities={"supports": 0.01, "refutes": 0.99, "not_enough_info": 0.0},
            raw_nli_label="REFUTES", source_type="wikipedia_live",
            source_url="https://en.wikipedia.org/wiki/FIFA_World_Cup", publication_date="2026-11-10T11:12:02Z",
        )
    ]
    assert synth.synthesize("Argentina is the current reigning men's FIFA World Cup champion.", wc_ev).verdict == "OUTDATED"


def test_correction2_missing_evidence_never_infers_fake():
    """Verify M&A silence on Apple Inc. falls back to UNVERIFIED rather than guessing FAKE."""
    synth = VerdictSynthesizer()
    apple_ev = [
        VerifiedEvidence(
            rank=1, page="Apple Inc.", sentence_id=0, doc_id="apple_0",
            text="Apple Inc. is an American multinational technology company headquartered in Cupertino, California.",
            retrieval_similarity=0.58, nli_label="REFUTES", nli_confidence=0.96,
            nli_probabilities={"supports": 0.04, "refutes": 0.96, "not_enough_info": 0.0},
            raw_nli_label="REFUTES", source_type="wikipedia_live",
        )
    ]
    res = synth.synthesize("Apple acquired Tesla Motors for 500 billion dollars in 2023.", apple_ev)
    assert res.verdict == "UNVERIFIED"


def test_correction4_weighted_central_vs_peripheral_article_aggregation():
    """
    Verify centrality x materiality x evidence weighting across article claims:
      (a) 3 central GENUINE + 1 minor UNVERIFIED -> GENUINE (with uncertainty note)
      (b) 2 central GENUINE + 1 central FAKE -> PARTIALLY_TRUE
      (c) 3 minor GENUINE + 1 central FAKE -> FAKE (never masked as GENUINE)
      (d) 3 central FAKE -> FAKE
      (e) 1 central GENUINE + 1 central UNVERIFIED -> UNVERIFIED
    """
    def _mk(verdict: str, conf: float = 0.90) -> SynthesisResult:
        return SynthesisResult(
            verdict=verdict, confidence_score=conf, explanation=verdict,
            uncertainty_explanation=verdict, conflicting_evidence_detected=False,
            strongest_evidence_page="Test", limitations=[],
        )

    # (a) 3 central GENUINE + 1 minor UNVERIFIED -> GENUINE with explicit note
    v_a, _, expl_a, unc_a = _aggregate_multi_claim_verdicts(
        [
            ("Alexander Fleming discovered penicillin in 1928.", _mk("GENUINE", 0.90)),
            ("Penicillin treated bacterial infections cleanly in clinical trials.", _mk("GENUINE", 0.88)),
            ("Howard Florey and Ernst Chain shared the 1945 Nobel Prize.", _mk("GENUINE", 0.87)),
            ("Some observers later mentioned an unrecorded cafe remark.", _mk("UNVERIFIED", 0.25)),
        ],
        context_label="extracted claims",
        candidate_weights=[(1, 5.2), (2, 4.6), (3, 4.2), (4, 0.7)],
    )
    assert v_a == VerdictEnum.GENUINE
    assert "minor" in expl_a.lower()
    assert "unverified minor" in unc_a.lower()

    # (b) 2 central GENUINE + 1 central FAKE -> PARTIALLY_TRUE
    v_b, _, expl_b, _ = _aggregate_multi_claim_verdicts(
        [
            ("Tokyo is the capital of Japan.", _mk("GENUINE", 0.90)),
            ("OpenAI released ChatGPT in November 2022.", _mk("GENUINE", 0.89)),
            ("Mount Everest is located in Africa.", _mk("FAKE", 0.92)),
        ],
        context_label="extracted claims",
        candidate_weights=[(1, 5.0), (2, 4.5), (3, 4.2)],
    )
    assert v_b == VerdictEnum.PARTIALLY_TRUE
    assert "central" in expl_b.lower()

    # (c) 3 minor GENUINE + 1 central FAKE -> FAKE (minor truths must not hide central falsehood)
    v_c, _, expl_c, _ = _aggregate_multi_claim_verdicts(
        [
            ("Microsoft was founded in London in 1995 by Tim Berners-Lee.", _mk("FAKE", 0.93)),
            ("Computers use electrical circuits.", _mk("GENUINE", 0.80)),
            ("Software relies on binary logic.", _mk("GENUINE", 0.78)),
            ("London sits along the River Thames.", _mk("GENUINE", 0.79)),
        ],
        context_label="extracted claims",
        candidate_weights=[(1, 5.4), (4, 0.9), (5, 0.8), (6, 0.7)],
    )
    assert v_c == VerdictEnum.FAKE
    assert "minor truths do not offset central falsification" in expl_c.lower()

    # (d) 3 central FAKE -> FAKE
    v_d, _, _, _ = _aggregate_multi_claim_verdicts(
        [
            ("World War II ended in 1955.", _mk("FAKE", 0.91)),
            ("Titanic sank in the Pacific Ocean in 1925.", _mk("FAKE", 0.92)),
            ("Mount Everest lies on the African continent.", _mk("FAKE", 0.90)),
        ],
        context_label="extracted claims",
        candidate_weights=[(1, 5.0), (2, 4.8), (3, 4.5)],
    )
    assert v_d == VerdictEnum.FAKE

    # (e) 1 central GENUINE + 1 central UNVERIFIED -> UNVERIFIED
    v_e, _, expl_e, _ = _aggregate_multi_claim_verdicts(
        [
            ("Jupiter is the largest planet in the Solar System.", _mk("GENUINE", 0.91)),
            ("Sundar Pichai secretly met NASA engineers in Bengaluru in 2025.", _mk("UNVERIFIED", 0.28)),
        ],
        context_label="extracted claims",
        candidate_weights=[(1, 5.0), (2, 4.6)],
    )
    assert v_e == VerdictEnum.UNVERIFIED
    assert "central" in expl_e.lower()


def test_ordinal_conflict_and_directional_orbital_alignment():
    """
    Regression checks for:
      1. Ordinal rank disagreement (first/1st..tenth/10th) on aligned subject + property -> REFUTES
      2. Directional orbital role reversal ('Sun revolves around Earth' vs 'Earth revolves around Sun') -> REFUTES even if DeBERTa predicts SUPPORTS
      3. Correctly aligned supporting orbital & ordinal evidence -> SUPPORTS
      4. Unrelated / superlative / distinct-entity ordinals -> NO false contradiction
      5. Non-orbital co-occurrence ('rotate about respective axes') & missing/irrelevant evidence -> NOT ENOUGH INFO
      6. Existing India vs South America geographical refutation remains REFUTES
    """
    earth_third_ev = VerifiedEvidence(
        rank=1,
        page="Earth",
        sentence_id=0,
        doc_id="earth_0",
        text="Earth (from Eorde Terra), otherwise known as the World or the Globe, is the third planet from the Sun and the only object in the Universe known to harbor life.",
        retrieval_similarity=0.61,
        nli_label="REFUTES",
        nli_confidence=0.9987,
        nli_probabilities={"supports": 0.0013, "refutes": 0.9987, "not_enough_info": 0.0},
        raw_nli_label="REFUTES",
    )
    assmt_earth_4th = evaluate_evidence_alignment("The Earth is the fourth planet from the Sun.", earth_third_ev)
    assert assmt_earth_4th.has_exclusive_slot_conflict is True
    assert assmt_earth_4th.calibrated_nli == "REFUTES"
    assert assmt_earth_4th.evidence_role == "contradicting"

    # Correctly aligned ordinal still produces SUPPORTS
    earth_third_sup = VerifiedEvidence(
        rank=1,
        page="Earth",
        sentence_id=0,
        doc_id="earth_0_sup",
        text="Earth is the third planet from the Sun and the only astronomical object known to harbor life.",
        retrieval_similarity=0.82,
        nli_label="SUPPORTS",
        nli_confidence=0.998,
        nli_probabilities={"supports": 0.998, "refutes": 0.002, "not_enough_info": 0.0},
        raw_nli_label="SUPPORTS",
    )
    assmt_earth_3rd = evaluate_evidence_alignment("The Earth is the third planet from the Sun.", earth_third_sup)
    assert assmt_earth_3rd.has_exclusive_slot_conflict is False
    assert assmt_earth_3rd.calibrated_nli == "SUPPORTS"

    # Unrelated ordinals & superlatives do NOT trigger false contradiction
    neptune_superlative = VerifiedEvidence(
        rank=1,
        page="Earth",
        sentence_id=2,
        doc_id="earth_rel",
        text="Earth is the fifth-largest planet in the Solar System, and Mars is the fourth planet from the Sun.",
        retrieval_similarity=0.71,
        nli_label="SUPPORTS",
        nli_confidence=0.95,
        nli_probabilities={"supports": 0.95, "refutes": 0.05, "not_enough_info": 0.0},
        raw_nli_label="SUPPORTS",
    )
    assmt_super = evaluate_evidence_alignment("The Earth is the fifth-largest planet in the Solar System.", neptune_superlative)
    assert assmt_super.has_exclusive_slot_conflict is False

    # Competing planet clause ("Mars is the fourth planet") and superlative ("fourth-largest") must not falsely refute "Earth is the third planet"
    earth_vs_competing = evaluate_evidence_alignment("The Earth is the third planet from the Sun.", neptune_superlative)
    assert earth_vs_competing.has_exclusive_slot_conflict is False

    # Directional orbital reversal overrides DeBERTa's role-blind SUPPORTS -> REFUTES
    earth_orbits_sun_blind = VerifiedEvidence(
        rank=1,
        page="Earth's orbit",
        sentence_id=0,
        doc_id="orbit_0",
        text="Earth's orbit is the path through which the Earth travels around the Sun.",
        retrieval_similarity=0.714,
        nli_label="SUPPORTS",
        nli_confidence=0.9987,
        nli_probabilities={"supports": 0.9987, "refutes": 0.0013, "not_enough_info": 0.0},
        raw_nli_label="SUPPORTS",
    )
    assmt_sun_rev = evaluate_evidence_alignment("The Sun revolves around the Earth.", earth_orbits_sun_blind)
    assert assmt_sun_rev.has_exclusive_slot_conflict is True
    assert assmt_sun_rev.calibrated_nli == "REFUTES"
    assert assmt_sun_rev.evidence_role == "contradicting"

    # Non-orbital axial rotation sentence must NOT pass SUPPORTS via entity co-occurrence
    axial_spin_ev = VerifiedEvidence(
        rank=2,
        page="Earth's orbit",
        sentence_id=11,
        doc_id="orbit_11",
        text="From the same vantage point, both the Earth and the Sun would appear to rotate in a counterclockwise direction about their respective axes.",
        retrieval_similarity=0.648,
        nli_label="SUPPORTS",
        nli_confidence=0.9992,
        nli_probabilities={"supports": 0.9992, "refutes": 0.0008, "not_enough_info": 0.0},
        raw_nli_label="SUPPORTS",
    )
    assmt_axial = evaluate_evidence_alignment("The Sun revolves around the Earth.", axial_spin_ev)
    assert assmt_axial.calibrated_nli == "NOT ENOUGH INFO"

    # Correctly aligned orbital claim + supporting evidence -> SUPPORTS
    assmt_earth_rev = evaluate_evidence_alignment("The Earth revolves around the Sun.", earth_orbits_sun_blind)
    assert assmt_earth_rev.has_exclusive_slot_conflict is False
    assert assmt_earth_rev.calibrated_nli == "SUPPORTS"
    assert assmt_earth_rev.evidence_role == "supporting"

    # Irrelevant evidence remains NOT ENOUGH INFO
    cheese_ev = VerifiedEvidence(
        rank=1,
        page="Cheese",
        sentence_id=0,
        doc_id="cheese_0",
        text="Cheese is a food derived from milk that is produced in a wide range of flavors.",
        retrieval_similarity=0.47,
        nli_label="REFUTES",
        nli_confidence=0.998,
        nli_probabilities={"supports": 0.002, "refutes": 0.998, "not_enough_info": 0.0},
        raw_nli_label="REFUTES",
    )
    assmt_cheese = evaluate_evidence_alignment("The Moon is made entirely of cheese.", cheese_ev)
    assert assmt_cheese.calibrated_nli == "NOT ENOUGH INFO"

    # Existing India vs South America remains REFUTES
    india_ev = VerifiedEvidence(
        rank=1,
        page="India",
        sentence_id=0,
        doc_id="india_0",
        text="India, officially the Republic of India, is a country in South Asia.",
        retrieval_similarity=0.68,
        nli_label="REFUTES",
        nli_confidence=0.9985,
        nli_probabilities={"supports": 0.0015, "refutes": 0.9985, "not_enough_info": 0.0},
        raw_nli_label="REFUTES",
    )
    assmt_india = evaluate_evidence_alignment("India is located in South America.", india_ev)
    assert assmt_india.has_exclusive_slot_conflict is True
    assert assmt_india.calibrated_nli == "REFUTES"

    # VerdictSynthesizer produces FAKE when aligned contradicting evidence refutes Earth/Sun claims
    synth = VerdictSynthesizer()
    assert synth.synthesize("The Earth is the fourth planet from the Sun.", [earth_third_ev]).verdict == "FAKE"
    assert synth.synthesize("The Sun revolves around the Earth.", [earth_orbits_sun_blind, axial_spin_ev]).verdict == "FAKE"
    assert synth.synthesize("The Earth revolves around the Sun.", [earth_orbits_sun_blind]).verdict == "GENUINE"
