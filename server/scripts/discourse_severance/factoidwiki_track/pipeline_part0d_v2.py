"""PART 0d, v2: redesigned marker handling + first-class anaphora
resolution, on top of pipeline_part0d.py's proven parser-attachment
logic (16/16 on 0c, correctly caught the 3278/4200 misattachment
controls and the 4117/arm_2 reversal in 0d -- none of that is being
replaced).

What changes, and why (per explicit instruction after the 0e
calibration sample showed 7/21 agreement with all 14 disagreements
in the over-rejection direction):

1. Marker-word search is DEMOTED from "final severed gate" to a
   ROUTING signal only.
     - If a marker word IS found (as before): still run the parser
       attachment check. This is untouched and is what correctly
       catches real misattachment (3278/4200: marker present, attached
       to the wrong content) and reversal (4117/arm_2: marker present,
       attached to the wrong SIDE). Nothing about that mechanism was
       broken by calibration -- only the case where NO marker exists at
       all was.
     - If NO marker word is found anywhere (the old design's default:
       automatically severed): now falls through to a new NLI relation-
       entailment check instead -- does the located nucleus+satellite
       content, taken together, entail the canonical relation-marked
       sentence ("Although {satellite}, {nucleus}." for Concession;
       "If {satellite}, {nucleus}." for Condition)? This reuses the
       already-validated NLI model for a second, legitimate purpose
       (verifying the content substantively supports the relational
       claim) instead of requiring a lexical trigger word RST itself
       does not require. Calibration items 3, 9, 18 are exactly this
       pattern: real juxtaposition-only Concessions with no surviving
       connective.

2. Anaphora resolution as a first-class pre-entailment stage, applied
   in BOTH directions found in testing:
     - ground-truth nucleus/satellite text opening with a bare pronoun
       ("it was nonetheless under the scrutiny...") -- resolved against
       the SOURCE PARAGRAPH before the content-location entailment check
       (calibration item 20).
     - a parser-resolved candidate clause opening with a definite
       description ("the country") -- resolved against the propositions
       already confirmed to carry real content, before the clause-vs-
       satellite/nucleus entailment check (pool 4117/arm_4).
"""

import re
import sys

import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

sys.path.insert(0, ".")
from parser_attachment_resolver import resolve_marker_clause, nlp  # noqa: E402
from pipeline_part0d import MARKER_SYNONYMS, find_marker_hits  # noqa: E402

MODEL_NAME = "roberta-large-mnli"
_DEVICE = "mps" if torch.backends.mps.is_available() else "cpu"
_tok = AutoTokenizer.from_pretrained(MODEL_NAME)
_model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME).to(_DEVICE)
_model.eval()
_ID2LABEL = _model.config.id2label
ENTAIL_THRESHOLD = 0.5

PRONOUNS = {"it", "he", "she", "they", "this", "that", "its", "his", "her", "their"}
# Narrowly scoped on purpose (per explicit instruction: not a general
# coreference system): only these generic place/organization referring
# nouns trigger resolution, since a broad "the <any noun phrase>" search
# was tested and found to fire on plain descriptive noun phrases that
# are not anaphoric at all ("the only official language"), corrupting
# clauses that needed no resolution.
_GENERIC_REFERENTS = ("country", "nation", "region", "area", "city", "team",
                      "organization", "organisation", "company", "state", "place")
DEFINITE_DESC_RE = re.compile(
    r"\bthe\s+(" + "|".join(_GENERIC_REFERENTS) + r")\b", re.I
)


def nli(premise, hypothesis):
    inputs = _tok(premise, hypothesis, return_tensors="pt", truncation=True, max_length=512).to(_DEVICE)
    with torch.no_grad():
        logits = _model(**inputs).logits
    probs = torch.softmax(logits, dim=1)[0]
    return {_ID2LABEL[i]: float(probs[i]) for i in range(len(probs))}


def entails(premise, hypothesis):
    scores = nli(premise, hypothesis)
    return scores["ENTAILMENT"] >= ENTAIL_THRESHOLD, scores


def resolve_leading_pronoun(text, context_text):
    if not context_text:
        return text, False
    doc_text = nlp(text)
    if not doc_text or doc_text[0].text.lower() not in PRONOUNS:
        return text, False
    doc_ctx = nlp(context_text)
    antecedent = doc_ctx.ents[0].text if doc_ctx.ents else None
    if not antecedent:
        chunks = list(doc_ctx.noun_chunks)
        antecedent = chunks[0].text if chunks else None
    if not antecedent:
        return text, False
    first_tok = doc_text[0]
    rest = text[first_tok.idx + len(first_tok.text):]
    return antecedent + rest, True


def resolve_definite_description(text, context_text):
    if not context_text:
        return text, False
    # search anywhere in the clause, not just the leading position -- a
    # definite description like "the country" can trail a prepositional
    # marker ("despite ... in the country") rather than open the clause
    # (pool 4117/arm_4's actual pattern).
    m = DEFINITE_DESC_RE.search(text.strip())
    if not m:
        return text, False
    doc_ctx = nlp(context_text)
    ents = [e.text for e in doc_ctx.ents if e.label_ in ("GPE", "LOC", "ORG", "PERSON", "NORP")]
    if not ents:
        return text, False
    antecedent = ents[-1]
    return text.replace(m.group(0), antecedent, 1), True


def _locate(propositions, hypothesis):
    """Single-proposition check, then two-proposition-window fallback.
    No anaphora resolution here -- that is a SEPARATE, outer fallback
    layer (see entails_any), tried only if this already fails on the
    hypothesis as given.
    """
    idx = [i for i, p in enumerate(propositions) if entails(p, hypothesis)[0]]
    if idx:
        return idx, "single-proposition"
    for i in range(len(propositions) - 1):
        window = propositions[i] + " " + propositions[i + 1]
        if entails(window, hypothesis)[0]:
            return [i, i + 1], "two-proposition-window"
    return [], "not-found"


def entails_any(propositions, hypothesis, context_for_anaphora=None):
    """STANDING DESIGN RULE for this pipeline: no correction step
    (anaphora/definite-description resolution, or any future one) runs
    unconditionally. Always attempt the unresolved/simpler path first;
    only fall back to a correction if that attempt fails outright. Found
    the hard way: pool 1943's "it costs double." already correctly
    entails its matching proposition unresolved (0.975), but the
    original unconditional-resolution design rewrote "it" to "Metro"
    (the first named entity in that paragraph, unrelated to the actual
    referent) before ever trying the original text, flipping a correct
    case to severed. Same two-step shape as _locate's own single-
    proposition-then-window fallback -- try the cheap/direct thing,
    escalate only on failure.
    """
    idx, mode = _locate(propositions, hypothesis)
    if idx:
        return idx, mode, hypothesis
    resolved_hyp, changed = resolve_leading_pronoun(hypothesis, context_for_anaphora)
    if changed:
        idx, mode = _locate(propositions, resolved_hyp)
        if idx:
            return idx, mode + "-anaphora-resolved", resolved_hyp
    return [], "not-found", hypothesis


def relation_entailed(premise_text, nucleus, satellite, relation_type):
    if relation_type == "Condition":
        canonical = f"If {satellite}, {nucleus}"
    else:
        canonical = f"Although {satellite}, {nucleus}"
    return entails(premise_text, canonical)


def evaluate_v2(propositions, nucleus, satellite, connective, relation_type, source_paragraph=None):
    nucleus_idx, _, nucleus_resolved = entails_any(propositions, nucleus, source_paragraph)
    satellite_idx, _, satellite_resolved = entails_any(propositions, satellite, source_paragraph)

    if not nucleus_idx or not satellite_idx:
        return {"preserved": False, "reason": "content absent",
                "nucleus_idx": nucleus_idx, "satellite_idx": satellite_idx,
                "nucleus_resolved": nucleus_resolved, "satellite_resolved": satellite_resolved}

    marker_hits = find_marker_hits(propositions, relation_type, connective)
    marker_idx = sorted(marker_hits)
    shared = set(nucleus_idx) & set(satellite_idx)
    relevant_idx = set(nucleus_idx) | set(satellite_idx)
    marker_in_relevant = set(marker_idx) & relevant_idx

    if marker_in_relevant:
        prop_idx = sorted(marker_in_relevant)[0]
        prop_text = propositions[prop_idx]
        found_conn = marker_hits[prop_idx]
        clause, dep, rule = resolve_marker_clause(prop_text, found_conn)
        if clause is None:
            return {"preserved": False, "reason": "parser could not locate marker token (marker branch)",
                     "nucleus_idx": nucleus_idx, "satellite_idx": satellite_idx, "marker_idx": marker_idx}

        # When satellite/nucleus content is compound and spans multiple
        # propositions (pool 1986: satellite split across two
        # propositions, marker in only one of them), do NOT ask the
        # single narrow clause to entail the full raw ground-truth
        # string -- a part cannot entail a whole that adds new specific
        # content it never mentions (that direction is what actually
        # broke pool 1986/2386 on the first attempt at this fix: it
        # compared clause-as-premise against a BROADER union-as-
        # hypothesis, still backwards). Reuse entails_any's own
        # windowing result directly instead of re-deriving a check from
        # the clause alone: if the marker's own proposition is one of
        # the propositions entails_any already confirmed jointly convey
        # the content, that attachment is corroborated by construction.
        # Only fall back to the strict narrow clause-vs-groundtruth
        # check (still needed for misattachment, e.g. 3278/4200) when
        # satellite/nucleus is a single proposition.
        if len(satellite_idx) > 1 and prop_idx in satellite_idx:
            clause_matches_satellite, sat_scores = True, {"note": "compound content confirmed via entails_any window"}
        else:
            clause_matches_satellite, sat_scores = entails(clause, satellite)
        if len(nucleus_idx) > 1 and prop_idx in nucleus_idx:
            clause_matches_nucleus, nuc_scores = True, {"note": "compound content confirmed via entails_any window"}
        else:
            clause_matches_nucleus, nuc_scores = entails(clause, nucleus)

        # Try the clause UNRESOLVED first (standing rule: no correction
        # step runs unconditionally); only fall back to definite-
        # description resolution if that fails outright.
        clause_resolved, clause_changed = clause, False
        if not (clause_matches_satellite or clause_matches_nucleus):
            anaphora_context = " ".join(propositions[i] for i in sorted(relevant_idx))
            candidate_resolved, changed = resolve_definite_description(clause, anaphora_context)
            if changed:
                resolved_matches_satellite, resolved_sat_scores = entails(candidate_resolved, satellite)
                resolved_matches_nucleus, resolved_nuc_scores = entails(candidate_resolved, nucleus)
                if resolved_matches_satellite or resolved_matches_nucleus:
                    clause_resolved, clause_changed = candidate_resolved, True
                    clause_matches_satellite, sat_scores = resolved_matches_satellite, resolved_sat_scores
                    clause_matches_nucleus, nuc_scores = resolved_matches_nucleus, resolved_nuc_scores

        if shared and prop_idx in shared:
            preserved = bool(clause_matches_satellite)
        else:
            preserved = bool(clause_matches_satellite or clause_matches_nucleus)
        return {
            "preserved": preserved, "reason": "marker-present: parser attachment check"
                                               + (" (anaphora-resolved)" if clause_changed else ""),
            "prop_idx": prop_idx, "resolved_clause": clause, "clause_resolved": clause_resolved,
            "dep": dep, "rule": rule,
            "clause_vs_satellite_scores": {k: (round(v, 3) if isinstance(v, float) else v) for k, v in sat_scores.items()},
            "clause_vs_nucleus_scores": {k: (round(v, 3) if isinstance(v, float) else v) for k, v in nuc_scores.items()},
            "nucleus_idx": nucleus_idx, "satellite_idx": satellite_idx, "marker_idx": marker_idx,
        }

    # No marker anywhere -- NEW: NLI relation-entailment check instead of
    # an automatic severed verdict.
    premise_text = " ".join(propositions[i] for i in sorted(relevant_idx))
    ok, rel_scores = relation_entailed(premise_text, nucleus, satellite, relation_type)
    return {
        "preserved": bool(ok), "reason": "marker-absent: NLI relation-entailment check",
        "nucleus_idx": nucleus_idx, "satellite_idx": satellite_idx,
        "relation_scores": {k: round(v, 3) for k, v in rel_scores.items()},
        "premise_used": premise_text,
    }
