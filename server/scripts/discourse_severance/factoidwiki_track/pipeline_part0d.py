"""PART 0d: combined parser+NLI AND-gate, run against the known hard
case set (real propositions, pulled directly from
results/task8_factoidwiki_exp3_report.json -- not constructed text).

Routing:
  - nucleus and satellite entailed by the SAME proposition (checked via
    NLI): intra-proposition case -> dependency-parser attachment check
    (parser_attachment_resolver.resolve_marker_clause), confirmed via
    NLI whether the resolved clause matches the ground-truth satellite.
  - nucleus and satellite entailed by DIFFERENT propositions: cross-
    proposition case -> CODE-LEVEL membership check only (does a marker
    occur in either of the two propositions already confirmed to carry
    the right content?), no parser call -- there is no single sentence
    for the parser to resolve attachment within.
  - nucleus or satellite not entailed anywhere: severed (absent).
"""

import json
import sys

import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

sys.path.insert(0, ".")
from parser_attachment_resolver import resolve_marker_clause  # noqa: E402

MODEL_NAME = "roberta-large-mnli"
_tok = AutoTokenizer.from_pretrained(MODEL_NAME)
_model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME)
_model.eval()
_ID2LABEL = _model.config.id2label

ENTAIL_THRESHOLD = 0.5

MARKER_SYNONYMS = {
    "Concession": ["although", "though", "but", "however", "yet", "despite",
                   "in spite of", "nonetheless", "nevertheless", "still", "rather"],
    "Condition": ["if", "only if", "when", "unless", "provided that",
                  "as long as", "in the event"],
}


def nli(premise, hypothesis):
    inputs = _tok(premise, hypothesis, return_tensors="pt", truncation=True, max_length=512)
    with torch.no_grad():
        logits = _model(**inputs).logits
    probs = torch.softmax(logits, dim=1)[0]
    scores = {_ID2LABEL[i]: float(probs[i]) for i in range(len(probs))}
    return scores


def entails(premise, hypothesis):
    scores = nli(premise, hypothesis)
    return scores["ENTAILMENT"] >= ENTAIL_THRESHOLD, scores


def _sorted_variants(relation_type, connective):
    # Longest-first: "although" must be tried before "though" since
    # "though" is a literal substring of "although" -- naive unordered
    # substring matching can pick the wrong (shorter) variant, which then
    # fails resolve_marker_clause's exact-token lookup ("though" is not
    # a token in "Although Dutch was allowed...").
    variants = set(MARKER_SYNONYMS.get(relation_type, [])) | {connective.strip(",").lower()}
    return sorted((v for v in variants if v), key=len, reverse=True)


def find_marker_hits(propositions, relation_type, connective):
    """Returns {prop_idx: matched_variant} for every proposition containing
    a marker, using the longest-first variant so the substring actually
    present is the one resolve_marker_clause will look for as a token.
    """
    variants = _sorted_variants(relation_type, connective)
    hits = {}
    for i, p in enumerate(propositions):
        low = p.lower()
        for v in variants:
            if v in low:
                hits[i] = v
                break
    return hits


def entails_any(propositions, hypothesis):
    """Single-proposition entailment first; if that finds nothing, also
    check entailment against every adjacent 2-proposition window, since
    a compound nucleus/satellite can be legitimately split across two
    propositions with neither one alone entailing the full statement
    (found in testing: pool 2272's nucleus combines "changed his mind"
    + "signed to Auburn", split across two adjacent propositions).
    """
    idx = [i for i, p in enumerate(propositions) if entails(p, hypothesis)[0]]
    if idx:
        return idx, "single-proposition"
    for i in range(len(propositions) - 1):
        window = propositions[i] + " " + propositions[i + 1]
        if entails(window, hypothesis)[0]:
            return [i, i + 1], "two-proposition-window"
    return [], "not-found"


def evaluate(propositions, nucleus, satellite, connective, relation_type):
    nucleus_idx, nucleus_mode = entails_any(propositions, nucleus)
    satellite_idx, satellite_mode = entails_any(propositions, satellite)

    if not nucleus_idx or not satellite_idx:
        return {"preserved": False, "reason": "content absent",
                "nucleus_idx": nucleus_idx, "satellite_idx": satellite_idx,
                "nucleus_mode": nucleus_mode, "satellite_mode": satellite_mode}

    marker_hits = find_marker_hits(propositions, relation_type, connective)
    marker_idx = sorted(marker_hits)
    shared = set(nucleus_idx) & set(satellite_idx)
    relevant_idx = set(nucleus_idx) | set(satellite_idx)
    # Run the parser attachment check whenever a marker shares a
    # proposition with EITHER nucleus or satellite content -- not only
    # when nucleus and satellite themselves share a proposition. Found
    # in testing: pool 4200/arm_4's marker and the nucleus sit in the
    # same (long, merged) proposition, but the marker is actually
    # attached to a third, wrong clause within it -- co-occurrence with
    # the nucleus alone is not evidence of correct attachment.
    marker_in_relevant = set(marker_idx) & relevant_idx

    if marker_in_relevant:
        prop_idx = sorted(marker_in_relevant)[0]
        prop_text = propositions[prop_idx]
        found_conn = marker_hits[prop_idx]
        clause, dep, rule = resolve_marker_clause(prop_text, found_conn)
        if clause is None:
            return {"preserved": False, "reason": "parser could not locate marker token",
                     "nucleus_idx": nucleus_idx, "satellite_idx": satellite_idx, "marker_idx": marker_idx}
        clause_matches_satellite, clause_scores = entails(clause, satellite)
        clause_matches_nucleus, nucleus_scores = entails(clause, nucleus)
        if shared and prop_idx in shared:
            # nucleus AND satellite both fully in this one proposition:
            # correct attachment means the marker's own clause matches
            # the satellite side specifically (see pool 4117/arm_2 vs
            # arm_3 -- reversed vs normal).
            preserved = bool(clause_matches_satellite)
            reason = "intra-proposition parser check (nucleus+satellite co-located)"
        else:
            # marker co-occurs with only ONE of {nucleus, satellite} in
            # this proposition, the other is confirmed elsewhere. Correct
            # attachment means the marker's own clause matches EITHER
            # the satellite (classic "Although Q, [nucleus elsewhere]")
            # or the nucleus (the pool 2272 "[satellite elsewhere].
            # However, [nucleus]" pattern) -- not some third, wrong
            # clause (pool 4200's failure mode).
            preserved = bool(clause_matches_satellite or clause_matches_nucleus)
            reason = "intra-proposition parser check (marker shares a proposition with one of the two)"
        return {
            "preserved": preserved, "reason": reason,
            "prop_idx": prop_idx, "resolved_clause": clause, "dep": dep, "rule": rule,
            "clause_vs_satellite_scores": {k: round(v, 3) for k, v in clause_scores.items()},
            "clause_vs_nucleus_scores": {k: round(v, 3) for k, v in nucleus_scores.items()},
            "nucleus_idx": nucleus_idx, "satellite_idx": satellite_idx, "marker_idx": marker_idx,
        }

    return {"preserved": False, "reason": "marker absent or floating away from both nucleus and satellite",
            "nucleus_idx": nucleus_idx, "satellite_idx": satellite_idx, "marker_idx": marker_idx}


CASES = [
    {"id": "2004/arm_2", "expected": True,
     "relation": {"relation_type": "Concession",
                  "nucleus": 'The emblem of 2010 Winter Olympics, "Ilanaaq the Inukshuk", was picked through an open contest.',
                  "satellite": "However, it met criticism from some aboriginal groups over its design.",
                  "connective": "However"},
     "propositions": ['The emblem of the 2010 Winter Olympics, "Ilanaaq the Inukshuk", was picked through an open contest.',
                       "However, it met criticism from some aboriginal groups over its design.",
                       "As a result, the mascot artist was selected through a competition."]},
    {"id": "2004/arm_3", "expected": True,
     "relation": {"relation_type": "Concession",
                  "nucleus": 'The emblem of 2010 Winter Olympics, "Ilanaaq the Inukshuk", was picked through an open contest.',
                  "satellite": "However, it met criticism from some aboriginal groups over its design.",
                  "connective": "However"},
     "propositions": ["The emblem of 2010 Winter Olympics was 'Ilanaaq the Inukshuk', however, it met criticism from some aboriginal groups over its design.",
                       "Ilanaaq the Inukshuk was picked through an open contest.",
                       "Ilanaaq the Inukshuk met criticism from some aboriginal groups over its design.",
                       "The mascot artist for the 2010 Winter Olympics was selected through a competition."]},
    {"id": "2004/arm_4", "expected": False,
     "relation": {"relation_type": "Concession",
                  "nucleus": 'The emblem of 2010 Winter Olympics, "Ilanaaq the Inukshuk", was picked through an open contest.',
                  "satellite": "However, it met criticism from some aboriginal groups over its design.",
                  "connective": "However"},
     "propositions": ['The paragraph discusses the selection process of the emblem for the 2010 Winter Olympics, specifically highlighting that "Ilanaaq the Inukshuk" was chosen through an open contest, while also noting the criticism it received from some aboriginal groups regarding its design. The emblem of 2010 Winter Olympics was \'Ilanaaq the Inukshuk\'.',
                       "Ilanaaq the Inukshuk was picked through an open contest.",
                       "Ilanaaq the Inukshuk met criticism from some aboriginal groups over its design.",
                       "The mascot artist for the 2010 Winter Olympics was selected through a competition."]},
    {"id": "2272/arm_2", "expected": True,
     "relation": {"relation_type": "Concession",
                  "nucleus": "King announced that he had changed his mind, and on National Signing Day a month later, signed to play for the Tigers of Auburn University beginning in the 2013 FBS season.",
                  "satellite": "In July 2012, King verbally committed to transfer to the University of South Alabama and to play for the Jaguars football team.",
                  "connective": "However"},
     "propositions": ["In July 2012, King verbally committed to transfer to the University of South Alabama and to play for the Jaguars football team.",
                       "However, in January 2013, King announced that he had changed his mind about this commitment.",
                       "On National Signing Day a month later, King signed to play for the Tigers of Auburn University beginning in the 2013 FBS season."]},
    {"id": "3278/arm_4", "expected": False,
     "relation": {"relation_type": "Concession",
                  "nucleus": "he never showed any personal dislike of York in the 1450s, and that his personal motivation throughout the decade was loyalty to the Crown and keeping the peace between his peers.",
                  "satellite": "B. J. Harris noted that, although he died a staunch Lancastrian,",
                  "connective": "although"},
     "propositions": ["Humphrey Stafford was the 1st Duke of Buckingham.", "B. J. Harris is a historian.",
                       "Humphrey Stafford died a staunch Lancastrian.",
                       "Humphrey Stafford never showed any personal dislike of York in the 1450s.",
                       "The paragraph discusses B. J. Harris's observations about Humphrey Stafford, highlighting his loyalty to the Crown and efforts to maintain peace among his peers, despite his involvement in the political conflicts of the 1450s. Humphrey Stafford's personal motivation was loyalty to the Crown and keeping the peace between his peers.",
                       "Rawcliffe is another historian.",
                       "Rawcliffe suggested that Humphrey Stafford lacked the necessary qualities to become a great statesman or leader.",
                       "Humphrey Stafford was an unimaginative and unlikeable man according to Rawcliffe.",
                       "Humphrey Stafford had a reputation as a harsh taskmaster on his estates.",
                       "Humphrey Stafford displayed offensive behavior towards Joan of Arc.",
                       "Rawcliffe says that Humphrey Stafford's political judgement could be clouded by his attitude.",
                       "Humphrey Stafford had an ungovernable temper according to Rawcliffe."]},
    {"id": "4200/arm_4", "expected": False,
     "relation": {"relation_type": "Concession",
                  "nucleus": "the Pittsburgh Penguins lent him to Team Canada.",
                  "satellite": "Although Fleury was playing in the NHL the next year leading up to the tournament,",
                  "connective": "Although"},
     "propositions": ["Marc-André Fleury was playing in the NHL the next year leading up to the tournament.",
                       "The paragraph discusses Marc-André Fleury's participation in a high-profile tournament with Team Canada, highlighting that despite his desire to stay with the Pittsburgh Penguins, the team lent him to represent Canada for his development. The Pittsburgh Penguins lent Marc-André Fleury to Team Canada.",
                       "Marc-André Fleury expressed a desire to remain with his NHL club.",
                       "Penguins management decided the high-profile tournament would be good for Marc-André Fleury's development.",
                       "Marc-André Fleury led Team Canada to the gold medal game for the second consecutive year.",
                       "Marc-André Fleury made a costly mistake that lost his team the championship.",
                       "The game was tied 3-3 with less than five minutes remaining in regulation.",
                       "Marc-André Fleury left his net to play the puck and avert a breakaway opportunity for Patrick O'Sullivan of Team USA.",
                       "Marc-André Fleury's clearing attempt hit his own defenceman, Braydon Coburn, and trickled into the net.",
                       "The Americans held on for a 4-3 win.", "This mistake proved to be the difference in the game."]},
    {"id": "4117/arm_2-REVERSED", "expected": False,
     "relation": {"relation_type": "Concession",
                  "nucleus": "Dutch was allowed to be used for official purposes in Flanders",
                  "satellite": "although French remained the only official language in Belgium",
                  "connective": "although"},
     "propositions": ["Certain events led to a silent uprising in Flanders against French-speaking domination.",
                       "Dutch was not allowed to be used for official purposes in Flanders until 1878.",
                       "Although Dutch was allowed for official purposes in Flanders, French remained the only official language in Belgium."]},
    {"id": "4117/arm_3", "expected": True,
     "relation": {"relation_type": "Concession",
                  "nucleus": "Dutch was allowed to be used for official purposes in Flanders",
                  "satellite": "although French remained the only official language in Belgium",
                  "connective": "although"},
     "propositions": ["These events led to a silent uprising in Flanders against French-speaking domination.",
                       "Dutch was allowed to be used for official purposes in Flanders in 1878, although French remained the only official language in Belgium.",
                       "Language legislation in Belgium is related to the use of Dutch for official purposes in Flanders.",
                       "French remained the only official language in Belgium."]},
    {"id": "4117/arm_4", "expected": True,
     "relation": {"relation_type": "Concession",
                  "nucleus": "Dutch was allowed to be used for official purposes in Flanders",
                  "satellite": "although French remained the only official language in Belgium",
                  "connective": "although"},
     "propositions": ["These events led to a silent uprising in Flanders against French-speaking domination.",
                       "The paragraph discusses the historical context of language dominance in Belgium, highlighting the silent uprising in Flanders against French-speaking control and the eventual recognition of Dutch for official use in 1878, despite French remaining the sole official language in the country. Dutch was allowed to be used for official purposes in Flanders in 1878.",
                       "Language legislation in Belgium is related to the use of Dutch for official purposes in Flanders.",
                       "French remained the only official language in Belgium."]},
]


def main():
    results = []
    for c in CASES:
        r = c["relation"]
        out = evaluate(c["propositions"], r["nucleus"], r["satellite"], r["connective"], r["relation_type"])
        correct = out["preserved"] == c["expected"]
        results.append({"id": c["id"], "expected": c["expected"], **out, "correct": correct})
        print(f"[{'PASS' if correct else 'FAIL'}] {c['id']}: expected={c['expected']} "
              f"actual={out['preserved']} ({out['reason']})")
        if "resolved_clause" in out:
            print(f"    resolved clause: {out['resolved_clause']!r}")
        print(f"    nucleus_idx={out.get('nucleus_idx')} satellite_idx={out.get('satellite_idx')} "
              f"marker_idx={out.get('marker_idx')}")

    n_pass = sum(r["correct"] for r in results)
    print(f"\n{n_pass}/{len(results)} passed")
    json.dump(results, open("results/pipeline_part0d_report.json", "w"), indent=2)


if __name__ == "__main__":
    main()
