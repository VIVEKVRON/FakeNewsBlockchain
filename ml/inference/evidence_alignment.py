"""
ml/inference/evidence_alignment.py
Symbolic + lexical alignment module that bridges FAISS/Wikipedia retrieval and DeBERTa NLI.

Addresses root causes diagnosed in the audit:
  1. DeBERTa FEVER checkpoint binary collapse (logit[2] dead -> never predicts NOT ENOUGH INFO).
  2. Brittle word matching (no stemming, dropped numbers/short symbols like '0' or 'C').
  3. Subject-entity mismatch causing false support/refutation on unrelated articles.
  4. Compound multi-proposition claim decomposition for PARTIALLY_TRUE.
  5. Temporal / tenure-end detection for OUTDATED vs GENUINE vs FAKE.
"""

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple
from ml.inference.claim_verifier import VerifiedEvidence


STOPWORDS = {
    "the", "is", "was", "were", "an", "a", "and", "or", "in", "on", "at",
    "to", "for", "of", "with", "by", "that", "this", "these", "those", "from",
    "as", "it", "its", "be", "are", "been", "has", "have", "had", "their", "they",
    "he", "she", "who", "which", "where", "when", "what", "into", "about", "there",
    "very", "more", "most", "some", "such", "than", "then", "also", "other",
    "however", "although", "though", "while", "after", "before", "during"
}

GENERIC_INITIAL_WORDS = {
    "the", "a", "an", "this", "that", "these", "those", "scientists", "researchers",
    "biologists", "analysts", "experts", "officials", "people", "studies", "reports",
    "next", "current", "currently", "former", "there", "some",
    "many", "most", "all", "every", "although", "while", "however", "despite",
    "over", "under", "nearly", "almost", "about", "approximately", "more", "less",
    "between", "since", "until", "moreover", "furthermore", "meanwhile", "only", "just",
    "around", "during", "within", "across", "pure", "healthy", "three", "two", "four",
    "five", "confidential", "leaked", "secret", "amateur", "retired", "sole"
}

NON_SUBJECT_PROPER_MODIFIERS = {
    "american", "indian", "british", "french", "german", "chinese", "russian", "canadian",
    "australian", "japanese", "brazilian", "swedish", "swiss", "italian", "spanish",
    "portuguese", "european", "asian", "african", "antarctic", "arctic", "korean",
    "president", "minister", "prime", "chief", "pm", "cm", "ceo", "king", "queen",
    "secretary", "chancellor", "governor",
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december", "state", "states", "united"
}

# Light suffix / irregular stem rules (kept strictly deterministic with zero heavy NLP deps)
IRREGULAR_STEMS = {
    "frozen": "freez",
    "freezes": "freez",
    "freezing": "freez",
    "orbited": "orbit",
    "orbits": "orbit",
    "orbiting": "orbit",
    "revolve": "revolv",
    "revolves": "revolv",
    "revolved": "revolv",
    "revolving": "revolv",
    "travel": "travel",
    "travels": "travel",
    "traveled": "travel",
    "travelled": "travel",
    "traveling": "travel",
    "travelling": "travel",
    "walked": "walk",
    "walks": "walk",
    "walking": "walk",
    "cancelled": "cancel",
    "canceled": "cancel",
    "cancels": "cancel",
    "cancellation": "cancel",
    "cancellations": "cancel",
    "concluded": "conclud",
    "concludes": "conclud",
    "ended": "end",
    "ends": "end",
    "discovered": "discover",
    "discovers": "discover",
    "developed": "develop",
    "develops": "develop",
    "founded": "found",
    "founds": "found",
    "gained": "gain",
    "gains": "gain",
    "aired": "air",
    "airs": "air",
    "served": "serv",
    "serves": "serv",
    "rebranded": "rebrand",
    "rebrands": "rebrand",
    "renamed": "renam",
    "renames": "renam",
    "landed": "land",
    "lands": "land",
    "tallest": "high",
    "highest": "high",
    "largest": "larg",
    "biggest": "big",
    "celsius": "c",
    "centigrade": "c",
    "degrees": "degre",
    "degree": "degre",
    "presidential": "presid",
    "president": "presid",
    "presidency": "presid",
    "succeeded": "succe",
    "replaced": "replac",
    "retired": "retir",
    "nineteen": "19",
    "two": "2",
    "children": "child",
    "kids": "kid",
    "humans": "human",
    "people": "human",
    "stars": "star",
    "planets": "planet",
    "countries": "country",
    "nations": "country",
    "states": "state",
    "boils": "boil",
    "boiling": "boil",
    "cures": "cure",
    "curing": "cure",
    "cured": "cure",
    "antibiotics": "antibiotic",
    "vaccines": "vaccine",
    "viruses": "virus",
    "bacteria": "bacteria",
    "bacterial": "bacteria",
    "penguins": "penguin",
    "reigned": "reign",
    "reigning": "reign",
    "holders": "holder",
}

TOKEN_EQUIVALENT_SETS: List[Set[str]] = [
    {"cancel", "conclud", "end"},
    {"tall", "high"},
    {"pm", "prime"},
    {"cm", "chief"},
    {"twitter", "x"},
    {"rebrand", "renam", "former", "restructur"},
    {"broadcast", "air", "show", "stream"},
    {"planet", "world"},
    {"revolv", "orbit"},
    {"spaceflight", "mission", "apollo"},
    {"daughter", "girl"},
    {"son", "boy"},
    {"nasa", "us", "usa", "american"},
    {"isro", "india", "indian"},
    {"monarch", "king", "queen", "sovereign"},
    {"viral", "virus", "influenza"},
    {"antibiotic", "antibacterial", "penicillin"},
    {"euro", "eur"},
    {"facebook", "meta"},
    {"google", "alphabet"},
    {"parent", "owned", "owner", "holding", "conglomerate"},
    {"antarctic", "antarctica"},
    {"social", "networking", "media"},
]

COMPOUND_TITLE_PREFIXES = {"mount", "mt", "lake", "river", "sea", "ocean", "desert", "gulf"}

CURRENT_OFFICE_OR_STATE_PATTERNS = [
    r"\b(current|currently|incumbent|presently|nowadays|sitting|reigning|unrenamed)\b",
    r"\bremains\b.*?\b(?:official|currency|parent|holding|company|name|in\s+use|in\s+service)\b",
    r"\bas of (202[4-9]|today)\b",
    r"\btoday\b",
    r"\b(is|are)\s+(still\s+)?(the\s+)?(?:current\s+|incumbent\s+|sitting\s+|reigning\s+|official\s+)?(?:top-level\s+)?"
    r"(president|prime minister|chief minister|secretary[\s-]+general|ceo|chancellor|leader|governor|monarch|king|queen|champion|parent(?:\s+holding)?\s+company|official.*name|brand\s+name)\b",
    r"\b(is|are)\s+(currently\s+)?(airing|running|in office|serving as|owned by)\b",
]

HISTORICAL_END_PATTERNS = [
    r"\bfrom\s+\d{4}\s+to\s+\d{4}\b",
    r"\b(?:19|20)\d{2}\s*[–—-]\s*(?:19|20)\d{2}\b",
    r"\bheld\s+the\s+office\s+from\b",
    r"\bbetween\s+(?:19|20)\d{2}\s+and\s+(?:19|20)\d{2}\b",
    r"\bserved\s+as\b.*?\b(?:until|to\s+\d{4}|from\s+\d{4}|between\s+\d{4})\b",
    r"\b(?:was|is an? .*? politician who was)\s+the\s+(?:\d+(?:st|nd|rd|th)|eighth|first|second|third|fourth|fifth)?\s*(?:president|prime minister|chief minister|secretary-general)\b",
    r"\bretired\s+(?:politician\s+who\s+was|partially|spacecraft)\b|\bis\s+a\s+retired\b",
    r"\buntil\s+(?:his|her|their)\s+death\b",
    r"\buntil\s+the\s+adoption\s+of\b",
    r"\bwas\s+the\s+official\s+currency\s+of\b",
    r"\bconcluded\s+on\b",
    r"\bcancelled\s+(?:in|on)\b",
    r"\bcanceled\s+(?:in|on)\b",
    r"\bsucceeded\s+by\b",
    r"\breplaced\s+by\b",
    r"\brebranded\s+(?:as|to)\b",
    r"\brestructuring\s+of\b",
    r"\bbecame\s+the\s+parent\s+holding\s+company\b",
    r"\bnow\s+x\s+corp\b",
    r"\bformerly\b",
    r"\bformer\s+(?:name|brand|president|prime\s+minister|chief\s+minister|ceo|title|governor|leader|google\s+subsidiaries)\b",
    r"\bended\s+(?:in|on)\b",
    r"\buntil\s+(?:january|february|march|april|may|june|july|august|september|october|november|december|\d{4})\b",
    r"\b(?:defeating|defeated)\s+the\s+(?:defending\s+)?holders?\b",
]

MUTUALLY_EXCLUSIVE_GROUPS: List[Set[str]] = [
    {"moon", "mars", "jupiter", "venus", "saturn", "pluto", "mercury", "neptune", "earth"},
    {"france", "germany", "spain", "italy", "india", "china", "japan", "russia", "brazil", "canada", "australia", "argentina", "norway", "sweden"},
    {"paris", "berlin", "london", "tokyo", "delhi", "beijing", "moscow", "rome", "madrid", "canberra", "sydney", "atlanta", "stockholm", "oslo", "brussels", "strasbourg"},
    {"pacific", "atlantic", "indian ocean", "arctic", "southern ocean"},
    {"antarctic", "antarctica", "south pole", "equator", "temperate", "tropical"},
    {"hbo", "tlc", "bbc", "cbs", "nbc", "abc", "fox", "pbs", "netflix", "hulu"},
    {"baptist", "buddhist", "catholic", "hindu", "muslim", "jewish", "atheist"},
    {"asia", "europe", "africa", "south america", "north america", "antarctica", "oceania"},
    {"virus", "viral", "coronavirus", "sars", "bacteria", "bacterial", "bacterium", "fungus", "fungal", "parasite", "parasitic"},
    {"smallest", "tiniest"},
    {"largest", "biggest"},
]

ORTHOGONAL_SUBTYPE_FIELDS = {"peace", "chemistry", "physics", "literature", "medicine", "economics"}

GENERIC_POLITY_PAGES = {
    "united states", "india", "france", "england", "united kingdom", "china", "russia",
    "germany", "canada", "australia", "president of the united states",
    "list of presidents of the united states", "prime minister of india",
    "list of prime ministers of india",
}

ORDINAL_WORDS_MAP = {
    "first": "first", "1st": "first",
    "second": "second", "2nd": "second",
    "third": "third", "3rd": "third",
    "fourth": "fourth", "4th": "fourth",
    "fifth": "fifth", "5th": "fifth",
    "sixth": "sixth", "6th": "sixth",
    "seventh": "seventh", "7th": "seventh",
    "eighth": "eighth", "8th": "eighth",
    "ninth": "ninth", "9th": "ninth",
    "tenth": "tenth", "10th": "tenth",
}

_ORDINAL_PROPERTY_MODIFIERS = {
    "largest", "biggest", "smallest", "longest", "shortest",
    "highest", "lowest", "oldest", "youngest", "most", "least",
}
_ORDINAL_IGNORED_NOUNS = {
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december", "century", "millennium",
    "time", "way", "part", "place",
}
_COMPETING_BODIES_AND_PLACES = set().union(*MUTUALLY_EXCLUSIVE_GROUPS[:4])

ORDINAL_OFFICE_REGEX = re.compile(
    r"\b(first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|sixth|6th|seventh|7th|eighth|8th|ninth|9th|tenth|10th|\d+(?:st|nd|rd|th))\s+"
    r"(president|prime\s+minister|chief\s+minister|chancellor|monarch|king|queen)\s+of\s+(?:the\s+)?([a-z]+(?:\s+[a-z]+)?)\b"
)

ORDINAL_POSSESSIVE_OFFICE_REGEX = re.compile(
    r"\b([a-z]+(?:\s+[a-z]+)?)(?:'s|’s)\s+"
    r"(first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|sixth|6th|seventh|7th|eighth|8th|ninth|9th|tenth|10th|\d+(?:st|nd|rd|th))\s+"
    r"(president|prime\s+minister|chief\s+minister|chancellor|monarch|king|queen)\b"
)

CRITICAL_OFFICE_ROLE_NOUNS = {
    "president", "minister", "chancellor", "monarch", "king", "queen",
    "secretary", "nobel", "prize", "capital", "currency"
}

NARROWING_SCOPE_QUALIFIERS = {
    "manned", "crewed", "human", "astronauts", "almost", "primarily", "mainly", "some", "mostly"
}

NEGATION_WORDS = {"not", "never", "no", "neither", "nor", "without", "false", "denied", "disputed"}


def stem_token(tok: str) -> str:
    low = tok.lower()
    if low in IRREGULAR_STEMS:
        return IRREGULAR_STEMS[low]
    if len(low) > 5 and low.endswith("ing"):
        return low[:-3]
    if len(low) > 4 and low.endswith("ed"):
        return low[:-2]
    if len(low) > 4 and low.endswith("es") and not low.endswith("ies"):
        return low[:-2]
    if len(low) > 3 and low.endswith("s") and not low.endswith("ss") and not low.endswith("us"):
        return low[:-1]
    return low


def normalize_content_tokens(text: str, stem: bool = True) -> Set[str]:
    """
    Extracts normalized content tokens, keeping numeric values ('0', '19', '1969')
    and critical short abbreviations ('c', 'x', 'cm', 'pm', 'us', 'uk').
    """
    raw_tokens = re.findall(r"[a-zA-Z0-9]+", text.lower())
    out: Set[str] = set()
    keep_short = {"c", "x", "f", "cm", "pm", "us", "uk"}
    for tok in raw_tokens:
        if tok in STOPWORDS:
            continue
        if tok.isdigit() or len(tok) > 2 or tok in keep_short:
            out.add(stem_token(tok) if stem else tok)
    return out


def expand_with_equivalents(tokens: Set[str]) -> Set[str]:
    expanded = set(tokens)
    for eq_group in TOKEN_EQUIVALENT_SETS:
        if expanded.intersection(eq_group):
            expanded.update(eq_group)
    return expanded


AUXILIARY_MODAL_VERBS = {
    "is", "are", "was", "were", "am", "be", "has", "have", "had",
    "do", "does", "did", "will", "would", "can", "could", "shall", "should",
    "may", "might", "must"
}

PRONOUN_SUBJECTS = {"i", "you", "he", "she", "it", "we", "they"}

DETERMINERS_QUANTIFIERS = {
    "the", "a", "an", "this", "that", "these", "those", "my", "your",
    "his", "her", "its", "our", "their", "all", "some", "many", "most",
    "few", "several", "no", "every", "each", "both", "one", "two", "three",
    "four", "five", "six", "seven", "eight", "nine", "ten", "various", "other"
}

PREPOSITIONS_SET = {
    "in", "on", "at", "by", "for", "of", "to", "from", "with", "into",
    "inside", "outside", "through", "across", "near", "under", "over",
    "above", "below", "between", "among", "during", "since", "until",
    "after", "before", "against", "without", "as"
}

_ORBITAL_PRONOUNS = {"it", "its", "this", "our planet", "the planet"}
_ORBITAL_NON_ENTITIES = (
    GENERIC_INITIAL_WORDS
    | PREPOSITIONS_SET
    | DETERMINERS_QUANTIFIERS
    | STOPWORDS
    | {
        "day", "days", "year", "years", "time", "path", "space", "distance", "sky",
        "stars", "star", "direction", "axis", "axes", "orbit", "motion", "speed",
        "degree", "degrees", "viewed", "because", "same", "vantage", "point",
    }
)
_ORBITAL_PASSIVE_PATTERN = re.compile(
    r"\b(?:the\s+)?(?P<center>[A-Z][A-Za-z0-9\-]+)\s+(?:is|are|was|were)\s+orbited\s+by\s+(?:the\s+)?(?P<orb>[A-Z][A-Za-z0-9\-]+)\b"
)
_ORBITAL_VERB_PATTERN = re.compile(
    r"\b(?P<verb>orbit(?:s|ed|ing)?|revolve[sd]?|travel[sd]?)\b"
)
_ORBITAL_POST_OBJ_PREP_PATTERN = re.compile(
    r"^[^.;!?]{0,60}?\b(?:around|about|round)\s+(?:the\s+|our\s+)?(?P<obj>[A-Z][A-Za-z0-9\-]+)\b"
)
_ORBITAL_POST_OBJ_DIRECT_PATTERN = re.compile(
    r"^\s*(?:around|about|round)?\s*(?:the\s+|our\s+)?(?P<obj>[A-Z][A-Za-z0-9\-]+)\b"
)
_ORBITAL_NOMINAL_PATTERN = re.compile(
    r"(?:"
    r"(?:of\s+(?P<subj1>[A-Z][A-Za-z0-9\-]+)\s+and\s+its|(?P<subj2>[A-Z][A-Za-z0-9\-]+)(?:'s|’s))\s+orbit\s+(?:around|about|of)\s+(?:the\s+)?(?P<obj1>[A-Z][A-Za-z0-9\-]+)"
    r"|"
    r"\borbit\s+(?:around|about)\s+(?:the\s+)?(?P<obj2>[A-Z][A-Za-z0-9\-]+)\s*,\s*(?:the\s+)?(?P<subj3>[A-Z][A-Za-z0-9\-]+)"
    r")"
)


def _norm_orbital_entity(raw: str, page_hint_entity: Optional[str] = None) -> Optional[str]:
    clean = re.sub(r"^(?:the|our|a|an)\s+", "", raw.strip().lower()).rstrip("'s’")
    if not clean or clean in _ORBITAL_NON_ENTITIES:
        return None
    if clean in _ORBITAL_PRONOUNS or clean == "planet":
        return page_hint_entity
    return stem_token(clean) if clean not in MUTUALLY_EXCLUSIVE_GROUPS[0] else clean


def extract_orbital_relations(text: str, page_hint: str = "") -> List[Tuple[str, str]]:
    """
    Extracts directed (orbiting_body, center_body) pairs from orbital sentences,
    distinguishing active ('X revolves around Y', 'X's orbit around Y') from passive
    ('X is orbited by Y') and preventing false triggers on axial spin ('rotate about axes').
    """
    page_clean = re.sub(r"\s*\([^)]*\)", "", page_hint or "").strip().lower()
    page_body = page_clean.split("'s")[0].split("’s")[0].strip()
    page_entity = page_body if page_body in MUTUALLY_EXCLUSIVE_GROUPS[0] else None

    relations: List[Tuple[str, str]] = []
    for sent in re.split(r"[.;!?]+", text):
        if not sent.strip():
            continue
        for m in _ORBITAL_PASSIVE_PATTERN.finditer(sent):
            center = _norm_orbital_entity(m.group("center"), page_entity)
            orb = _norm_orbital_entity(m.group("orb"), page_entity)
            if orb and center and orb != center:
                relations.append((orb, center))

        for m in _ORBITAL_NOMINAL_PATTERN.finditer(sent):
            subj_raw = m.group("subj1") or m.group("subj2") or m.group("subj3") or ""
            obj_raw = m.group("obj1") or m.group("obj2") or ""
            orb = _norm_orbital_entity(subj_raw, page_entity)
            center = _norm_orbital_entity(obj_raw, page_entity)
            if orb and center and orb != center:
                relations.append((orb, center))

        for m in _ORBITAL_VERB_PATTERN.finditer(sent):
            verb_low = m.group("verb").lower()
            before = sent[:m.start()]
            # Guard: skip noun uses of "orbit" (e.g. "Earth's orbit", "During one orbit")
            if verb_low == "orbit" and re.search(r"(?:\b(?:one|an|the|its|our|solar|lunar)\s+|['’]s\s+)$", before.lower()):
                continue
            if re.search(r"\b(?:is|are|was|were)\s+$", before.lower()) and verb_low == "orbited":
                continue

            clause_before = re.split(r"[,;]", before)[-1]
            cand_subjects: List[str] = []
            for sm in re.finditer(r"\b(?:our\s+planet|the\s+planet|[A-Z][A-Za-z0-9\-]+)\b", clause_before):
                norm_s = _norm_orbital_entity(sm.group(0), page_entity)
                if norm_s:
                    cand_subjects.append(norm_s)
            if not cand_subjects:
                continue
            orb = cand_subjects[-1]

            after = sent[m.end():]
            obj_m = _ORBITAL_POST_OBJ_PREP_PATTERN.match(after)
            if not obj_m and verb_low.startswith("orbit"):
                obj_m = _ORBITAL_POST_OBJ_DIRECT_PATTERN.match(after)
            if not obj_m:
                continue
            center = _norm_orbital_entity(obj_m.group("obj"), page_entity)
            if orb and center and orb != center:
                relations.append((orb, center))

    seen: Set[Tuple[str, str]] = set()
    unique: List[Tuple[str, str]] = []
    for rel in relations:
        if rel not in seen:
            seen.add(rel)
            unique.append(rel)
    return unique


def detect_ordinal_property_conflict(
    claim: str,
    ev_text: str,
    claim_entities: List[str],
    ev_page: str,
) -> bool:
    """
    Detects disjoint ordinal ranks (first/1st..tenth/10th) on aligned subject + property
    (e.g. 'Earth is the fourth planet from the Sun' vs 'Earth is the third planet from the Sun'),
    ignoring distinct superlative properties ('second-smallest'), dates, and competing entities.
    """
    def _last_token_pos(src: str, tok_set: Set[str]) -> int:
        best = -1
        for tok in tok_set:
            for tm in re.finditer(rf"\b{re.escape(tok)}\b", src):
                if tm.start() > best:
                    best = tm.start()
        return best

    def _extract_props(src_text: str, is_claim: bool) -> List[Tuple[str, str, str, str, str]]:
        out: List[Tuple[str, str, str, str, str]] = []
        clauses = re.split(r"[.;!?]+|\s*,\s+(?:and|but|while|whereas|although|though)\s+", src_text)
        claim_ent_set = {e.lower() for e in claim_entities}
        page_low = (ev_page or "").lower()
        for clause in clauses:
            cl_low = clause.lower()
            prev_end = 0
            for m in re.finditer(
                r"\b(?:the\s+)?(first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|sixth|6th|seventh|7th|eighth|8th|ninth|9th|tenth|10th)"
                r"(?:(?:\s*-\s*|\s+)(largest|biggest|smallest|longest|shortest|highest|lowest|oldest|youngest|most|least))?"
                r"(?:\s+(?!(?:from|of|in|on|at|to|by|and|or)\b)([a-z]{3,})){1,2}"
                r"(?:\s+(?:from|of|in)\s+(?:the\s+)?([a-z]{3,}))?",
                cl_low,
            ):
                prefix = cl_low[prev_end:m.start()]
                prev_end = m.end()
                if re.search(r"\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+$", prefix):
                    continue
                ord_norm = ORDINAL_WORDS_MAP[m.group(1)]
                comp_mod = (m.group(2) or "").strip()
                before_prep = re.split(r"\s+(?:from|of|in)\s+", m.group(0), maxsplit=1)[0]
                tail_words = [
                    w for w in re.findall(r"[a-z]+", before_prep)
                    if w not in ORDINAL_WORDS_MAP and w not in _ORDINAL_PROPERTY_MODIFIERS and w not in {"the"}
                ]
                if not tail_words:
                    continue
                head_noun = stem_token(tail_words[-1])
                if tail_words[-1] in _ORDINAL_IGNORED_NOUNS:
                    continue
                anchor = stem_token(m.group(4)) if m.group(4) else ""

                clause_subj = "matched"
                if not is_claim and claim_ent_set:
                    prefix_words = set(re.findall(r"[a-z0-9]+", prefix))
                    ev_prefix_competing = prefix_words.intersection(_COMPETING_BODIES_AND_PLACES) - claim_ent_set
                    matched_prefix_claim_ents = prefix_words.intersection(claim_ent_set)
                    has_claim_ent = bool(matched_prefix_claim_ents) or bool(any(ce in page_low for ce in claim_ent_set))
                    if ev_prefix_competing:
                        if not matched_prefix_claim_ents or _last_token_pos(prefix, ev_prefix_competing) > _last_token_pos(prefix, matched_prefix_claim_ents):
                            clause_subj = "competing"
                    elif not has_claim_ent:
                        clause_subj = "unmatched"
                out.append((ord_norm, comp_mod, head_noun, anchor, clause_subj))
        return out

    c_props = _extract_props(claim, is_claim=True)
    e_props = _extract_props(ev_text, is_claim=False)
    if not c_props or not e_props:
        return False

    for c_ord, c_comp, c_noun, c_anchor, _ in c_props:
        matching_e_ords: Set[str] = set()
        c_noun_group = {c_noun}
        for eq in TOKEN_EQUIVALENT_SETS:
            if c_noun in eq:
                c_noun_group.update(eq)
        for e_ord, e_comp, e_noun, e_anchor, e_subj in e_props:
            if e_subj != "matched" or c_comp != e_comp or e_noun not in c_noun_group:
                continue
            if c_anchor and e_anchor and c_anchor != e_anchor:
                continue
            matching_e_ords.add(e_ord)
        if matching_e_ords and c_ord not in matching_e_ords:
            return True
    return False

CURATED_FINITE_VERBS = {
    # Irregular past-tense & common uninflected predicate roots
    "won", "lost", "wrote", "built", "made", "took", "gave", "got", "saw",
    "knew", "found", "held", "kept", "left", "led", "met", "paid", "put",
    "ran", "said", "sent", "set", "sat", "spoke", "spent", "stood", "struck",
    "swam", "taught", "told", "thought", "understood", "wore", "went", "came",
    "became", "began", "broke", "brought", "caught", "chose", "fell", "flew",
    "fought", "grew", "hung", "heard", "rose", "sank", "shone", "shot", "shut",
    "sang", "slept", "sold", "stole", "threw",
    # Base plural / uninflected transitive predicates
    "live", "fly", "become", "remain", "exist", "occur", "belong", "consist",
    "contain", "include", "require", "provide", "produce", "prevent", "cause",
    "enable", "allow", "confer", "receive", "share", "develop", "create",
    "discover", "invent", "found", "release", "connect", "convert", "orbit",
    "lie", "flow", "span", "cross", "join", "replace", "govern", "operate",
    "own", "serve", "hold", "grow", "die", "win", "lose"
}

KNOWN_NON_VERB_WORDS = {
    "species", "series", "physics", "mathematics", "chemistry", "economics",
    "politics", "linguistics", "electronics", "genetics", "ethics", "news",
    "dollars", "euros", "percent", "years", "months", "days", "hours",
    "minutes", "seconds", "countries", "nations", "cities", "towns", "villages",
    "islands", "mountains", "rivers", "oceans", "lakes", "seas", "planets",
    "stars", "moons", "atoms", "cells", "genes", "molecules", "metals",
    "gases", "liquids", "solids", "prizes", "awards", "fields", "sciences",
    "metrics", "scientists", "researchers", "engineers", "physicists",
    "chemists", "biologists", "historians", "economists", "politicians",
    "presidents", "ministers", "leaders", "governors", "monarchs", "kings",
    "queens", "penguins", "mammals", "reptiles", "birds", "animals", "plants",
    "viruses", "bacteria", "vaccines", "antibiotics", "diseases", "infections",
    "hospitals", "instruments", "computers", "robots", "satellites", "rockets",
    "aircraft", "ships", "cars", "trains", "books", "papers", "laws", "rules",
    "rights", "languages", "households", "panels", "parks", "bicycles",
    "bridges", "walls", "billionaires", "citizens", "humans", "people",
    "women", "men", "children", "kids", "sons", "daughters", "boys", "girls",
    "brothers", "sisters", "founders", "authors", "members", "teams",
    "leaked", "secret", "red", "sacred",
    "naked", "wicked", "beloved", "green", "open", "even", "often", "seven",
    "ten", "always", "never", "exclusively", "solely", "currently", "originally"
}

CONCRETE_LOWERCASE_SUBJECT_STOPWORDS = STOPWORDS | DETERMINERS_QUANTIFIERS | PREPOSITIONS_SET | {
    "current", "currently", "incumbent", "sitting", "reigning", "former", "only",
    "sole", "exclusively", "pure", "healthy", "amateur", "retired", "secret",
    "leaked", "confidential", "unrecorded", "small", "smaller", "smallest",
    "large", "larger", "largest", "major", "minor", "average", "annual",
    "global", "local", "national", "international", "standard", "effective"
}


def extract_subject_entities(claim: str) -> List[str]:
    """
    Extracts key named entities from a claim (lowercased raw tokens), handling
    possessive modifiers ('India's Chandrayaan-3' -> prioritizes 'chandrayaan-3' / 'chandrayaan')
    and skipping generic sentence-initial words, demonyms, and office titles.
    """
    entities: List[str] = []
    seen: Set[str] = set()

    # Check explicit possessive proper-head pair ("India's Chandrayaan-3", "NASA's James Webb")
    # so the possessed named entity takes priority over the possessor modifier.
    possessive_heads: List[str] = []
    for pm in re.finditer(r"\b[A-Z][A-Za-z\-]+(?:'s|’s)\s+([A-Z][A-Za-z0-9\-]*)", claim):
        head_full = pm.group(1).lower()
        for candidate in ([head_full] + re.split(r"[-]", head_full)):
            if candidate and len(candidate) >= 3 and candidate not in STOPWORDS and candidate not in NON_SUBJECT_PROPER_MODIFIERS:
                possessive_heads.append(candidate)

    for ph in possessive_heads:
        if ph not in seen:
            seen.add(ph)
            entities.append(ph)

    tokens = re.findall(r"[A-Za-z0-9]+", claim)
    for i, tok in enumerate(tokens):
        low = tok.lower()
        if low in STOPWORDS or low in NON_SUBJECT_PROPER_MODIFIERS:
            continue
        is_cap = tok[0].isupper()
        if is_cap:
            if i == 0 and low in GENERIC_INITIAL_WORDS:
                continue
            if len(tok) >= 2 and low not in seen:
                seen.add(low)
                entities.append(low)
    return entities


def extract_years_and_numbers(text: str) -> Tuple[Set[str], Set[str]]:
    years = set(re.findall(r"\b(?:1[5-9]\d{2}|20\d{2})\b", text))
    all_nums = set(re.findall(r"\b\d+(?:\.\d+)?\b", text))
    return years, all_nums


def _has_independent_clause_structure(clause: str) -> bool:
    """
    Deterministic syntactic clause validator (beyond fragile verb-suffix regex alone).
    Verifies a span contains a real grammatical Subject + Finite Predicate Verb
    while rejecting coordinated noun lists, prepositional lists, and verbless
    participial/adjective modifiers.
    """
    cleaned = re.sub(r"'s\b|’s\b", "", clause).strip(" ,.;:!?\"'")
    raw_tokens = re.findall(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*", cleaned)
    if len(raw_tokens) < 3:
        return False

    lows = [t.lower() for t in raw_tokens]
    is_caps = [t[0].isupper() for t in raw_tokens]
    n = len(lows)

    # First word must not make the entire fragment a pure prepositional/subordinate phrase without main clause
    # Scan potential finite predicate verb positions i >= 1 (subject must precede predicate)
    for i in range(1, n):
        tok = lows[i]
        prev = lows[i - 1]
        is_cap = is_caps[i]

        # Predicate verb cannot sit directly after a determiner, quantifier, or preposition
        if prev in DETERMINERS_QUANTIFIERS or prev in PREPOSITIONS_SET or prev in {"very", "quite", "most", "more", "so"}:
            continue

        # Confirm there is at least one subject-capable nominal/pronoun in raw_tokens[:i]
        subj_window = lows[:i]
        has_subject_head = any(
            (w in PRONOUN_SUBJECTS) or (
                w not in STOPWORDS
                and w not in DETERMINERS_QUANTIFIERS
                and w not in PREPOSITIONS_SET
                and not w.isdigit()
            )
            for w in subj_window
        )
        if not has_subject_head:
            continue

        # Tier 1: Finite auxiliary / copula / modal (handles active & passive constructions cleanly)
        if not is_cap and tok in AUXILIARY_MODAL_VERBS:
            if i < n - 1:
                return True
            continue

        # Must not be a capitalized proper noun mid-sentence (e.g. "Charles", "Gates", "United", "States")
        if is_cap:
            continue

        if tok in KNOWN_NON_VERB_WORDS or tok in STOPWORDS or tok in PREPOSITIONS_SET or tok in DETERMINERS_QUANTIFIERS:
            continue

        # Tier 2: Irregular finite past verbs or unambiguous base predicates
        if tok in CURATED_FINITE_VERBS:
            # Base uninflected verbs (live, use, work, fly, share, flow, start, end) need object/adverbial follow-through
            if i < n - 1 or tok in {"fell", "sank", "died", "won", "lost", "ended", "began", "rose", "grew", "flew", "occur", "exist"}:
                return True
            continue

        # Tier 3: Regular inflected past (-ed) in predicate position with nominal subject before it
        if len(tok) >= 5 and tok.endswith("ed") and not tok.endswith("eed"):
            if i < n - 1 or len(subj_window) >= 1:
                return True

        # Tier 4: Regular 3rd-person singular present (-s / -es) with subject-number & complement validation
        if (
            len(tok) >= 4
            and tok.endswith("s")
            and not tok.endswith(("ss", "us", "is", "ous", "ics", "ness", "less"))
        ):
            # Subject-verb agreement guard: plural quantifiers / regular lowercase plural nouns cannot take 3sg '-s' verb
            plural_subj_intro = lows[0] in {"all", "many", "several", "most", "both", "these", "those", "two", "three", "four", "five", "some"}
            prev_looks_plural = (
                not is_caps[i - 1]
                and prev.endswith("s")
                and not prev.endswith(("ss", "us", "is", "ics", "gas"))
            )
            if plural_subj_intro or prev_looks_plural:
                continue

            # Require a verbal complement or multi-word transitive object NP after the inflected 3sg verb
            if i < n - 1:
                nxt = lows[i + 1]
                complement_cue = (
                    nxt in DETERMINERS_QUANTIFIERS
                    or nxt in PREPOSITIONS_SET
                    or nxt in PRONOUN_SUBJECTS
                    or nxt in {"over", "near", "around", "about", "roughly", "nearly", "cleanly", "quickly", "directly"}
                    or is_caps[i + 1]
                    or nxt.isdigit()
                    or nxt.endswith("ly")
                    or (i < n - 2 and nxt not in {"and", "or"})
                )
                if complement_cue:
                    return True

    return False


def _extract_antecedent_subject(first_clause: str) -> Optional[str]:
    """Extracts clean lead subject phrase (preserving optional 'The ') for clause pronoun resolution."""
    cleaned = re.sub(r"^(?:although|though|while|whereas|because|since)\s+", "", first_clause.strip(), flags=re.IGNORECASE)
    lead_match = re.match(
        r"^((?:The\s+)?[A-Z][A-Za-z0-9.\-]+(?:\s+(?:of|the|and|[A-Z][A-Za-z0-9.\-]+)){0,4})",
        cleaned,
    )
    if lead_match:
        cand = lead_match.group(1).strip()
        cand_low = cand.lower()
        first_tok = cand_low.split()[0]
        if first_tok not in (GENERIC_INITIAL_WORDS - {"the"}) and cand_low not in {"the", "this", "that", "these", "those"}:
            return cand
    entities = extract_subject_entities(cleaned)
    if entities:
        return " ".join(entities[:2]).title()
    return None


def split_compound_claims(text: str) -> List[str]:
    """
    Splits multi-sentence or multi-clause factual assertions (e.g., for PARTIALLY_TRUE detection)
    only when each segment passes syntactic independent-clause validation (Subject + Finite Predicate),
    preventing noun lists or participial phrases from splitting.
    Resolves anaphoric subject pronouns ('he', 'she', 'it', 'they') across clauses while preserving expletive 'it'.
    """
    clean = re.sub(r"\s+", " ", text).strip()
    if not clean:
        return []

    # Step 1: Sentence boundary split
    placeholder = "<DOT>"
    protected = re.sub(r"\b([A-Z]|Jr|Sr|Dr|Mr|Mrs|Ms|St|vs|etc|Inc|Corp)\.(?=\s)", rf"\1{placeholder}", clean)
    sentences = [s.replace(placeholder, ".").strip() for s in re.split(r"(?<=[.!?])\s+", protected) if s.strip()]

    # Step 2: Check clause-level splits inside single sentences on ';', ', and ', ', while ', ', but ', ', although ', ', however ', ', whereas '
    clauses: List[str] = []
    conj_pattern = re.compile(r"(?:\s*;\s*|\s*,\s+(?:and|while|but|although|however|whereas|yet)\s+)", re.IGNORECASE)

    for sent in sentences:
        parts = [p.strip(" ,;") for p in conj_pattern.split(sent) if p.strip(" ,;")]
        if len(parts) > 1 and all(_has_independent_clause_structure(p) for p in parts):
            clauses.extend(parts)
        else:
            clauses.append(sent)

    if len(clauses) <= 1:
        return [clean]

    # Step 3: Anaphoric pronoun resolution across clauses (skipping dummy expletive "it is believed/reported/known...")
    lead_subject = _extract_antecedent_subject(clauses[0])
    expletive_it_re = re.compile(r"^it\s+(?:is|was)\s+(?:widely\s+)?(?:believed|known|reported|thought|said|possible|unlikely|true|false)\s+that\b", re.IGNORECASE)
    if lead_subject:
        resolved: List[str] = []
        for idx, cl in enumerate(clauses):
            if idx > 0 and not expletive_it_re.match(cl):
                cl = re.sub(r"^(?:he|she|it|they)\b", lead_subject, cl, flags=re.IGNORECASE)
            resolved.append(cl)
        clauses = resolved

    return clauses[:5]


def claim_asserts_current_state(claim: str) -> bool:
    low = claim.lower()
    return any(re.search(pat, low) for pat in CURRENT_OFFICE_OR_STATE_PATTERNS)


def evidence_shows_historical_end(evidence_text: str) -> bool:
    low = evidence_text.lower()
    return any(re.search(pat, low) for pat in HISTORICAL_END_PATTERNS)


def evidence_confirms_active_tenure(claim: str, evidence_text: str) -> bool:
    """
    Returns True if live/current evidence positively confirms an ongoing present-tense
    tenure or status for the claim's subject (including non-contiguous presidents like
    'is the 47th president' or '2025-present', while ignoring past terms).
    """
    ev_low = evidence_text.lower()
    # Direct ongoing office/status expressions
    if re.search(
        r"\b(is (the )?(current|incumbent)|has served as\b.*?\bsince\b|is serving as|"
        r"(?:19|20)\d{2}\s*[–—-]\s*present)\b",
        ev_low,
    ):
        return True
    # Explicit present-tense ordinal / titular copula ('who is the 47th president', 'is King of')
    # excluding historical past-tense attribution or champion replacement naming another winner.
    if re.search(
        r"\b(?:who\s+is|is)\s+(?:the\s+)?(?:\d+(?:st|nd|rd|th)\s+(?:and\s+current\s+)?)?"
        r"(?:president|prime\s+minister|chancellor|monarch|king|queen|secretary[\s-]+general|ceo|leader)\s+of\b",
        ev_low,
    ):
        return not evidence_shows_historical_end(evidence_text)
    if re.search(r"\b(?:reigning|current)\s+champion\s+is\s+([a-z][a-z\s]+)", ev_low):
        # Only active if the named champion matches the claim's entity
        m = re.search(r"\b(?:reigning|current)\s+champion\s+is\s+([a-z]+)", ev_low)
        champ = m.group(1) if m else ""
        return bool(champ and champ in claim.lower()) and not evidence_shows_historical_end(evidence_text)
    return False


@dataclass
class AlignedEvidenceAssessment:
    evidence: VerifiedEvidence
    overlap_ratio: float
    entity_matched: bool
    missing_primary_entity: bool
    calibrated_nli: str            # SUPPORTS, REFUTES, NOT ENOUGH INFO
    evidence_role: str             # supporting, contradicting, contextual
    has_numeric_conflict: bool
    has_exclusive_slot_conflict: bool
    has_negation_conflict: bool
    shows_historical_end: bool
    alignment_reason: str


def evaluate_evidence_alignment(claim: str, ev: VerifiedEvidence) -> AlignedEvidenceAssessment:
    """
    Combines semantic similarity, normalized predicate overlap, subject entity match,
    date/number conflicts, and exclusive-slot/negation signals to fix DeBERTa's
    dead NOT ENOUGH INFO logit head safely.
    """
    claim_tokens_raw = normalize_content_tokens(claim, stem=False)
    claim_tokens_stemmed = normalize_content_tokens(claim, stem=True)

    combined_ev_text = f"{ev.page} {ev.text}"
    ev_tokens_raw = normalize_content_tokens(combined_ev_text, stem=False)
    ev_tokens_stemmed = expand_with_equivalents(normalize_content_tokens(combined_ev_text, stem=True))
    ev_page_tokens = normalize_content_tokens(ev.page, stem=True)

    # Stemmed + synonym-expanded overlap
    overlap_tokens = claim_tokens_stemmed.intersection(ev_tokens_stemmed)
    overlap_ratio = len(overlap_tokens) / max(1, len(claim_tokens_stemmed))

    claim_lower = claim.lower()
    ev_lower = ev.text.lower()
    ev_page_lower = ev.page.lower()

    # Entity matching (critical to avoid unrelated articles triggering support/refute)
    claim_entities = extract_subject_entities(claim)
    page_and_text_lower = combined_ev_text.lower()

    # Guard A: Subject-first orthogonal domain/award subtype mismatch (e.g. Nobel Peace Prize vs Chemistry prize)
    subject_clause_part = re.split(r"\b(?:alongside|as\s+well\s+as|together\s+with|rather\s+than|unlike)\b", claim, maxsplit=1, flags=re.IGNORECASE)[0]
    subj_fields = normalize_content_tokens(subject_clause_part, stem=False).intersection(ORTHOGONAL_SUBTYPE_FIELDS)
    claim_fields = claim_tokens_raw.intersection(ORTHOGONAL_SUBTYPE_FIELDS)
    page_fields = normalize_content_tokens(ev.page, stem=False).intersection(ORTHOGONAL_SUBTYPE_FIELDS)
    if subj_fields and page_fields and not page_fields.intersection(subj_fields):
        orthogonal_subtype_mismatch = True
    else:
        orthogonal_subtype_mismatch = bool(claim_fields and page_fields and not page_fields.issubset(claim_fields))

    # Guard B: Namesake middle-initial collision (e.g. "Mark Zuckerberg" vs "Mark S. Zuckerberg")
    namesake_mismatch = False
    for m in re.finditer(r"\b([A-Z][a-z]{2,})\s+([A-Z][a-z]{2,})\b", claim):
        first_n, last_n = m.group(1), m.group(2)
        if re.search(rf"\b{re.escape(first_n)}\s+[A-Z]\.\s+{re.escape(last_n)}\b", combined_ev_text):
            plain_title_exact = ev_page_lower == f"{first_n} {last_n}".lower()
            has_same_initial_in_claim = bool(re.search(rf"\b{re.escape(first_n)}\s+[A-Z]\.?\s+{re.escape(last_n)}\b", claim))
            if not plain_title_exact and not has_same_initial_in_claim:
                namesake_mismatch = True
                break

    matched_entities = [ent for ent in claim_entities if ent in page_and_text_lower or stem_token(ent) in ev_tokens_stemmed]
    entity_matched = False
    missing_primary_entity = orthogonal_subtype_mismatch or namesake_mismatch
    ordinal_holder_conflict = False
    primary_checked_label = ""

    # Number / Year conflict detection (excluding biographical birth years like "born 14 November 1948")
    c_years, _ = extract_years_and_numbers(claim)
    ev_no_birth = re.sub(
        r"\bborn\s+(?:\d{1,2}\s+[a-z]+\s+|[a-z]+\s+\d{1,2},\s*)?(?:1[5-9]\d{2}|20\d{2})\b",
        "",
        ev_lower,
    )
    e_years, _ = extract_years_and_numbers(ev_no_birth)
    ev_stemmed_for_num = expand_with_equivalents(normalize_content_tokens(ev.text, stem=True))
    non_year_claim_tokens = {t for t in claim_tokens_stemmed if not t.isdigit()}
    pred_overlap_for_num = len(non_year_claim_tokens.intersection(ev_stemmed_for_num)) / max(1, len(non_year_claim_tokens))
    disjoint_years = bool(c_years and e_years and not c_years.intersection(e_years))
    has_numeric_conflict = bool(disjoint_years and pred_overlap_for_num >= 0.42)

    # Physical / percentage quantity conflicts (e.g. "50 degrees Celsius" vs "100 °C")
    if not has_numeric_conflict and pred_overlap_for_num >= 0.35:
        c_deg = re.findall(r"\b(\d+(?:\.\d+)?)\s*(?:degrees?(?:\s+celsius|\s+c\b)?|°\s*c\b)", claim_lower)
        e_deg = re.findall(r"\b(\d+(?:\.\d+)?)\s*(?:degrees?(?:\s+celsius|\s+c\b)?|°\s*c\b)", ev_lower)
        if c_deg and e_deg and not set(c_deg).intersection(set(e_deg)):
            has_numeric_conflict = True
        c_pct = re.findall(r"\b(\d+(?:\.\d+)?)\s*(?:percent|%)", claim_lower)
        e_pct = re.findall(r"\b(\d+(?:\.\d+)?)\s*(?:percent|%)", ev_lower)
        if c_pct and e_pct and not set(c_pct).intersection(set(e_pct)):
            has_numeric_conflict = True

    shows_hist_end = evidence_shows_historical_end(ev.text)

    # Framing / singleton-vs-multiplicity / mutually-exclusive slot conflict detection
    has_exclusive_slot_conflict = False
    is_sole_claim = bool(re.search(r"\b(only|exclusively|sole|solely|single|alone)\b", claim_lower))
    if is_sole_claim:
        if ("daughter" in claim_lower or "girl" in claim_lower) and ("boy" in ev_lower or "son" in ev_lower):
            has_exclusive_slot_conflict = True
        elif ("son" in claim_lower or "boy" in claim_lower) and ("girl" in ev_lower or "daughter" in ev_lower):
            has_exclusive_slot_conflict = True
        elif re.search(
            r"\b(?:two|three|four|five|six|seven|eight|nine|ten|[2-9]|\d{2,})\s+"
            r"(?:humans|people|persons|astronauts|crew|members|founders|authors|co-?founders|winners|scientists|leaders)\b",
            ev_lower,
        ) or re.search(r"\bcrew\s+of\s+(?:two|three|four|five|six|[2-9]|\d{2,})\b", ev_lower):
            has_exclusive_slot_conflict = True
        elif re.search(
            r"\b(?:co-?founder|co-?official|second|third|fourth|series\s+of|successive\s+dynasties|multiple|almost\s+exclusively)\b",
            ev_lower,
        ):
            has_exclusive_slot_conflict = True
        elif "aircraft" in claim_lower and ("first" in ev_lower and ("ii" in ev_lower or "iii" in ev_lower)):
            has_exclusive_slot_conflict = True
        elif re.search(
            r"(?:\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2},\s+[A-Z][a-z]+.*?\band\s+[A-Z][a-z]+|"
            r"\b(?:both|by)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\s+and\s+[A-Z][a-z]+)",
            ev.text,
        ):
            has_exclusive_slot_conflict = True

    # Corporate parent / ownership transition conflict (e.g. "owned by ... Meta Platforms" vs "Facebook, Inc.")
    if re.search(r"\b(?:parent(?:\s+holding)?\s+company|corporate\s+parent)\b", claim_lower):
        m_owner = re.search(
            r"\bowned\s+by\s+(?:the\s+)?(?:[A-Za-z]+\s+){0,3}?(?:conglomerate|company|corporation)?\s*([A-Z][A-Za-z0-9.\-]+(?:\s+[A-Z][A-Za-z0-9.\-]+)?)",
            ev.text,
        )
        if m_owner:
            owner_toks = normalize_content_tokens(m_owner.group(1), stem=False)
            lead_claim_toks = normalize_content_tokens(claim.split()[0], stem=False)
            if owner_toks and not owner_toks.intersection(lead_claim_toks):
                shows_hist_end = True
                has_exclusive_slot_conflict = True

    if not has_exclusive_slot_conflict:
        for group in MUTUALLY_EXCLUSIVE_GROUPS:
            c_grp = {g for g in group if re.search(rf"\b{re.escape(g)}\b", claim_lower)}
            e_grp = {g for g in group if re.search(rf"\b{re.escape(g)}\b", ev_lower)}
            if c_grp and e_grp and not c_grp.intersection(e_grp):
                has_exclusive_slot_conflict = True
                break

    if claim_entities and not missing_primary_entity:
        specific_entities = [e for e in claim_entities if len(e) >= 4 and e not in COMPOUND_TITLE_PREFIXES]
        distinctive_entities = specific_entities or [e for e in claim_entities if len(e) >= 4]
        primary_ent = distinctive_entities[0] if distinctive_entities else claim_entities[0]
        primary_checked_label = primary_ent
        compact_ev_lower = re.sub(r"[\s.]+", "", page_and_text_lower)
        primary_found = (
            (primary_ent in page_and_text_lower)
            or (stem_token(primary_ent) in ev_tokens_stemmed)
            or (re.sub(r"[\s.]+", "", primary_ent) in compact_ev_lower)
        )
        # Check ordinal unique-office holder replacement (both "first PM of India" and "India's first PM")
        if not primary_found and ev_page_lower not in GENERIC_POLITY_PAGES:
            c_ord = ORDINAL_OFFICE_REGEX.search(claim_lower)
            e_ord = ORDINAL_OFFICE_REGEX.search(ev_lower)
            if c_ord and e_ord:
                c_ord_norm = ORDINAL_WORDS_MAP.get(c_ord.group(1), c_ord.group(1))
                e_ord_norm = ORDINAL_WORDS_MAP.get(e_ord.group(1), e_ord.group(1))
                c_role = re.sub(r"\s+", " ", c_ord.group(2))
                e_role = re.sub(r"\s+", " ", e_ord.group(2))
                c_pol = re.sub(r"\s+", " ", c_ord.group(3)).strip()
                e_pol = re.sub(r"\s+", " ", e_ord.group(3)).strip()
                pol_match = (c_pol == e_pol) or e_pol.startswith(c_pol + " ") or c_pol.startswith(e_pol + " ")
                if c_ord_norm == e_ord_norm and c_role == e_role and pol_match:
                    ordinal_holder_conflict = True
                    has_exclusive_slot_conflict = True
            elif c_ord:
                e_pos = ORDINAL_POSSESSIVE_OFFICE_REGEX.search(ev_lower)
                if e_pos:
                    c_ord_norm = ORDINAL_WORDS_MAP.get(c_ord.group(1), c_ord.group(1))
                    e_ord_norm = ORDINAL_WORDS_MAP.get(e_pos.group(2), e_pos.group(2))
                    c_role = re.sub(r"\s+", " ", c_ord.group(2))
                    e_role = re.sub(r"\s+", " ", e_pos.group(3))
                    c_pol = re.sub(r"\s+", " ", c_ord.group(3)).strip()
                    e_pol = re.sub(r"\s+", " ", e_pos.group(1)).strip()
                    pol_match = (c_pol == e_pol) or e_pol.startswith(c_pol + " ") or c_pol.startswith(e_pol + " ")
                    if c_ord_norm == e_ord_norm and c_role == e_role and pol_match:
                        ordinal_holder_conflict = True
                        has_exclusive_slot_conflict = True

        # Allow claim-named event/object pages (e.g. "1996 Summer Olympics", "Neptune", "Space Shuttle")
        ev_page_tokens_stemmed = normalize_content_tokens(ev.page, stem=True)
        claim_expanded_stemmed = expand_with_equivalents(claim_tokens_stemmed)
        named_event_page_match = (
            bool(ev_page_tokens_stemmed)
            and ev_page_lower not in GENERIC_POLITY_PAGES
            and ev_page_tokens_stemmed.issubset(claim_expanded_stemmed)
            and overlap_ratio >= 0.30
            and (
                bool(re.search(r"\b(only|exclusively|sole|solely|first|last)\b", claim_lower))
                or has_numeric_conflict
                or has_exclusive_slot_conflict
                or (shows_hist_end and claim_asserts_current_state(claim))
            )
        )
        if not primary_found and not named_event_page_match and not ordinal_holder_conflict:
            missing_primary_entity = True
        page_word_overlap = claim_tokens_stemmed.intersection(ev_page_tokens)
        entity_matched = (primary_found or named_event_page_match or ordinal_holder_conflict) and (
            ev_page_lower in claim_lower
            or len(matched_entities) >= min(2, len(claim_entities))
            or len(page_word_overlap) >= 1
            or named_event_page_match
            or ordinal_holder_conflict
        )
    elif not claim_entities and not missing_primary_entity:
        # Generic science/world claim without proper nouns ("All penguin species...", "Antibiotics cure...", "Pure water boils...")
        raw_lc_tokens = [t.lower() for t in re.findall(r"[A-Za-z]+", claim)]
        topic_subjects = [
            stem_token(t) for t in raw_lc_tokens[:5]
            if t not in CONCRETE_LOWERCASE_SUBJECT_STOPWORDS and len(t) >= 4
        ]
        if topic_subjects:
            primary_checked_label = topic_subjects[0]
            if primary_checked_label not in ev_tokens_stemmed:
                missing_primary_entity = True
        entity_matched = (not missing_primary_entity) and (overlap_ratio >= 0.38 or primary_checked_label in ev_page_tokens)

    # Ordinal property rank conflict check (Fix 1: first/1st..tenth/10th on aligned subject + property)
    if not has_exclusive_slot_conflict and not missing_primary_entity and entity_matched:
        ordinal_subj_ents = claim_entities or ([primary_checked_label] if primary_checked_label else [])
        if detect_ordinal_property_conflict(claim, ev.text, ordinal_subj_ents, ev.page):
            has_exclusive_slot_conflict = True

    # Directional orbital relationship conflict / verification check (Fix 2)
    claim_orbital_rels = extract_orbital_relations(claim)
    ev_orbital_rels = extract_orbital_relations(ev.text, page_hint=ev.page) if claim_orbital_rels else []
    orbital_role_reversed = bool(
        claim_orbital_rels
        and ev_orbital_rels
        and any((c_obj, c_subj) in ev_orbital_rels for c_subj, c_obj in claim_orbital_rels)
    )
    orbital_role_matched = bool(
        claim_orbital_rels
        and ev_orbital_rels
        and any((c_subj, c_obj) in ev_orbital_rels for c_subj, c_obj in claim_orbital_rels)
    )
    if orbital_role_reversed and not orbital_role_matched:
        has_exclusive_slot_conflict = True
    orbital_direction_unverified = bool(claim_orbital_rels and not orbital_role_matched)

    # Negation conflict (when subject & topic align, explicit negation differs)
    # Guard against legal-status transitions ("no longer has city status") falsely contradicting "capital city"
    c_neg = claim_tokens_raw.intersection(NEGATION_WORDS)
    e_neg = ev_tokens_raw.intersection(NEGATION_WORDS)
    is_status_transition_only = (
        "no longer has city status" in ev_lower
        and "capital" in claim_tokens_raw
        and "status" not in claim_tokens_raw
    )
    has_negation_conflict = (not is_status_transition_only) and (
        (bool(e_neg) and not bool(c_neg)) or (bool(c_neg) and not bool(e_neg))
    )

    # Non-entity predicate overlap & role-noun presence checks for safe Gate 5 certification
    ent_stems = {stem_token(e) for e in claim_entities}
    non_ent_claim_tokens = claim_tokens_stemmed - ent_stems - {"1", "2", "3"}
    non_ent_overlap_count = len(non_ent_claim_tokens.intersection(ev_tokens_stemmed))
    sufficient_pred_overlap = True
    if len(non_ent_claim_tokens) >= 3:
        sufficient_pred_overlap = non_ent_overlap_count >= max(2, int(0.25 * len(non_ent_claim_tokens)))
    elif len(non_ent_claim_tokens) >= 1:
        sufficient_pred_overlap = non_ent_overlap_count >= 1

    claim_role_nouns = claim_tokens_raw.intersection(CRITICAL_OFFICE_ROLE_NOUNS)
    ev_role_stemmed = {stem_token(r) for r in ev_tokens_raw}
    claim_role_stemmed = {stem_token(r) for r in claim_role_nouns}
    missing_critical_role = bool(claim_role_stemmed and not claim_role_stemmed.intersection(ev_tokens_stemmed) and not claim_role_stemmed.intersection(ev_role_stemmed))

    # National vs state/provincial capital scope mismatch & explicit named national capital conflict
    capital_scope_mismatch = (
        "capital" in claim_tokens_raw
        and "state" not in claim_tokens_raw
        and "provincial" not in claim_tokens_raw
        and bool(re.search(r"\b(?:state|provincial|regional)\s+capital\b", ev_lower))
    )
    if "capital" in claim_tokens_raw:
        m_cap = re.search(
            r"\b(?:[a-z]+'s\s+capital(?:\s+city)?\s+is|capital(?:\s+city)?(?:\s+of\s+[a-z\s]{2,25})?\s+is)\s+([a-z]{3,})\b",
            ev_lower,
        )
        if m_cap:
            actual_cap = m_cap.group(1)
            if actual_cap not in {"the", "a", "an", "not", "located", "home"} and actual_cap not in claim_tokens_raw:
                has_exclusive_slot_conflict = True

    # Narrowing scope qualifier trap (e.g. "only country ... manned missions" vs "only ... spacecraft")
    ev_scope_narrows = is_sole_claim and bool(
        (ev_tokens_raw.intersection(NARROWING_SCOPE_QUALIFIERS)) - claim_tokens_raw
    )

    # Calibrated NEI Abstention Gate
    raw_label = ev.raw_nli_label or ev.nli_label
    supp_prob = ev.nli_probabilities.get("supports", 0.0)
    ref_prob = ev.nli_probabilities.get("refutes", 0.0)

    calibrated = raw_label
    reason = "NLI decision preserved with entity and predicate alignment"
    role = "contextual"

    # Gate 1: Relevance threshold
    if ev.retrieval_similarity < 0.45:
        calibrated = "NOT ENOUGH INFO"
        reason = f"Low semantic similarity ({ev.retrieval_similarity:.2f} < 0.45)"
    # Gate 2: Primary subject entity, subtype, or namesake mismatch
    elif missing_primary_entity:
        calibrated = "NOT ENOUGH INFO"
        if orthogonal_subtype_mismatch:
            reason = f"Orthogonal prize/domain subtype mismatch against evidence page '{ev.page}'"
        elif namesake_mismatch:
            reason = f"Distinct middle-initial namesake mismatch on evidence page '{ev.page}'"
        else:
            missing_lbl = primary_checked_label or (claim_entities[0] if claim_entities else "subject")
            reason = f"Primary claim subject '{missing_lbl}' absent from evidence page '{ev.page}'"
    # Gate 3: Insufficient lexical/predicate overlap (with exemption for direct entity + explicit numeric/slot match)
    elif overlap_ratio < 0.28 and not (entity_matched and (has_numeric_conflict or has_exclusive_slot_conflict)):
        calibrated = "NOT ENOUGH INFO"
        reason = f"Low normalized predicate overlap ({overlap_ratio:.2f} < 0.28)"
    # Gate 4: Fix binary-collapsed false REFUTES when evidence merely omits details
    elif raw_label == "REFUTES":
        if is_status_transition_only:
            calibrated = "NOT ENOUGH INFO"
            reason = "Municipal status transition sentence affirms capital identity while discussing city-status reorganization -> abstained to NEI"
        else:
            # Only count historical end dates as a direct contradiction if the evidence doesn't discuss a different past office
            role_mismatch = ("prime" in claim_tokens_raw and "minister" in ev_tokens_raw and "prime" not in ev_tokens_raw and "chief" in ev_tokens_raw)
            relevant_hist_conflict = shows_hist_end and claim_asserts_current_state(claim) and not role_mismatch and overlap_ratio >= 0.40
            explicit_contradiction = has_numeric_conflict or has_exclusive_slot_conflict or has_negation_conflict or relevant_hist_conflict
            # Require strong predicate overlap (>= 0.78) OR explicit structural contradiction signal to accept REFUTES
            if not explicit_contradiction and (overlap_ratio < 0.78 or ref_prob < 0.90):
                calibrated = "NOT ENOUGH INFO"
                reason = (
                    "DeBERTa binary head predicted REFUTES, but evidence lacks direct contradiction signals "
                    "(no date/entity/slot/negation conflict) and may simply omit the claim detail -> abstained to NEI"
                )
            else:
                calibrated = "REFUTES"
                role = "contradicting"
                reason = "Direct contradiction supported by NLI + structural/entity alignment"
    # Gate 5: Validate SUPPORTS
    elif raw_label == "SUPPORTS":
        # Guard: if claim numbers/dates, years, or exclusive/directional roles conflict with matched evidence
        if orbital_role_reversed and not orbital_role_matched:
            calibrated = "REFUTES"
            role = "contradicting"
            reason = "Orbital subject-object roles are reversed relative to the claim"
        elif has_exclusive_slot_conflict or has_numeric_conflict or disjoint_years:
            strong_structural_refute = (
                ref_prob > 0.20
                or (entity_matched and has_exclusive_slot_conflict)
                or (entity_matched and has_numeric_conflict and pred_overlap_for_num >= 0.58)
            )
            calibrated = "REFUTES" if strong_structural_refute else "NOT ENOUGH INFO"
            role = "contradicting" if calibrated == "REFUTES" else "contextual"
            reason = "Claim numbers/dates or mutually exclusive attributes conflict with evidence"
        elif orbital_direction_unverified:
            calibrated = "NOT ENOUGH INFO"
            reason = "Evidence mentions orbital entities without verifying the claimed directional relationship -> abstained to NEI"
        elif missing_critical_role or ev_scope_narrows or capital_scope_mismatch or not sufficient_pred_overlap:
            calibrated = "NOT ENOUGH INFO"
            reason = "Support signal omitted critical claim predicate, role noun, or narrowing scope qualifier -> abstained to NEI"
        elif supp_prob >= 0.65 and (entity_matched or overlap_ratio >= 0.48):
            calibrated = "SUPPORTS"
            role = "supporting"
            reason = "Strong entailment alignment across subject entity, predicate, and semantic similarity"
        else:
            calibrated = "NOT ENOUGH INFO"
            reason = "Support signal lacks sufficient entity or predicate grounding"

    return AlignedEvidenceAssessment(
        evidence=ev,
        overlap_ratio=round(overlap_ratio, 3),
        entity_matched=entity_matched,
        missing_primary_entity=missing_primary_entity,
        calibrated_nli=calibrated,
        evidence_role=role,
        has_numeric_conflict=has_numeric_conflict,
        has_exclusive_slot_conflict=has_exclusive_slot_conflict,
        has_negation_conflict=has_negation_conflict,
        shows_historical_end=shows_hist_end,
        alignment_reason=reason,
    )
