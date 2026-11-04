"""PART 0c: spaCy dependency-parser domain-fit check on REAL atomized
propositions (not clean prose), focused on the intra-proposition
attachment-direction question that broke all four LLM-judge iterations:
given a single proposition containing a Condition/Concession marker,
which clause does the marker grammatically introduce (the "mark"-tagged
subordinate clause), and does that match the ground-truth satellite
(the normal case) or the ground-truth nucleus (the fronted/reversed
case, e.g. pool 4117/arm_2)?

Method: find the marker token, walk to its head (should be an "advcl" or
similarly subordinated verb spacy tags as attached via "mark"), take that
verb's full subtree as "the marker's own clause", and everything else in
the sentence as "the other clause". Report both spans plus spaCy's raw
dependency labels for manual inspection -- accuracy is checked by hand
against known ground truth, not scored automatically, since this is a
domain-fit CHECK, not the final pipeline.
"""

import json

import spacy

nlp = spacy.load("en_core_web_sm")

MARKER_WORDS = {
    "although", "though", "but", "however", "yet", "despite", "nonetheless",
    "still", "rather", "if", "unless", "when", "while",
}


def find_marker_tokens(doc):
    return [t for t in doc if t.text.lower().strip(",") in MARKER_WORDS]


def clause_span_for_marker(marker_tok):
    """Walk from the marker to its clause root (the verb it's a `mark`
    child of, or its head more generally), then return that root's full
    subtree text as the marker's own clause.
    """
    head = marker_tok.head
    subtree_tokens = sorted(head.subtree, key=lambda t: t.i)
    return " ".join(t.text for t in subtree_tokens), head.text, head.dep_, marker_tok.dep_


CASES = [
    # (id, proposition text, connective, ground_truth_satellite,
    #  ground_truth_nucleus, expected_marker_clause_matches)
    {
        "id": "4117-arm2-REVERSED",
        "text": "Although Dutch was allowed for official purposes in Flanders, French remained the only official language in Belgium.",
        "connective": "Although", "satellite": "French remained the only official language in Belgium",
        "nucleus": "Dutch was allowed to be used for official purposes in Flanders",
        "expected_matches": "nucleus",  # the KNOWN reversed case
    },
    {
        "id": "4117-arm3-normal",
        "text": "Dutch was allowed to be used for official purposes in Flanders in 1878, although French remained the only official language in Belgium.",
        "connective": "although", "satellite": "French remained the only official language in Belgium",
        "nucleus": "Dutch was allowed to be used for official purposes in Flanders",
        "expected_matches": "satellite",
    },
    {
        "id": "2004-arm3-merged",
        "text": "The emblem of 2010 Winter Olympics was 'Ilanaaq the Inukshuk', however, it met criticism from some aboriginal groups over its design.",
        "connective": "however", "satellite": "it met criticism from some aboriginal groups over its design",
        "nucleus": "The emblem of 2010 Winter Olympics was 'Ilanaaq the Inukshuk'",
        "expected_matches": "satellite",
    },
    {
        "id": "2004-arm2-split-marker-with-nucleus",
        "text": "However, in January 2013, King announced that he had changed his mind about this commitment.",
        "connective": "However", "satellite": "In July 2012, King verbally committed to transfer to the University of South Alabama",
        "nucleus": "King announced that he had changed his mind",
        "expected_matches": "nucleus",  # satellite stated in a SEPARATE proposition, this one marks nucleus
    },
    {
        "id": "3278-misattach",
        "text": "The paragraph discusses B. J. Harris's observations about Humphrey Stafford, highlighting his loyalty to the Crown and efforts to maintain peace among his peers, despite his involvement in the political conflicts of the 1450s.",
        "connective": "despite", "satellite": "he died a staunch Lancastrian",
        "nucleus": "he never showed any personal dislike of York in the 1450s",
        "expected_matches": "neither",  # marker governs a THIRD, wrong fact
    },
    {
        "id": "4200-misattach",
        "text": "The paragraph discusses Marc-Andre Fleury's participation in a high-profile tournament with Team Canada, highlighting that despite his desire to stay with the Pittsburgh Penguins, the team lent him to represent Canada for his development.",
        "connective": "despite", "satellite": "Fleury was playing in the NHL the next year leading up to the tournament",
        "nucleus": "the Pittsburgh Penguins lent him to Team Canada",
        "expected_matches": "neither",
    },
    {
        "id": "3038-condition-merged",
        "text": "This list ranks some proposed buildings in the UK if built as planned.",
        "connective": "if", "satellite": "if built as planned",
        "nucleus": "This list ranks some proposed buildings in the UK",
        "expected_matches": "satellite",
    },
    {
        "id": "1964-rather-merged",
        "text": "The research provides no support for the view that civilization or viable social orders depend upon marriage as an exclusively heterosexual institution. Rather, anthropological research supports the conclusion that a vast array of family types, including families built upon same-sex partnerships, can contribute to stable and humane societies.",
        "connective": "Rather", "satellite": "provides no support for the view that civilization or viable social orders depend upon marriage as an exclusively heterosexual institution",
        "nucleus": "anthropological research supports the conclusion that a vast array of family types can contribute to stable and humane societies",
        "expected_matches": "nucleus",  # "Rather, X" marks the nucleus turn, satellite in prior sentence
    },
    {
        "id": "2659-arm4-but-merged",
        "text": "The Guadalajara area's attractions are principally in the city itself and nearby urban areas, but it also includes rural zones such as Bosque La Primavera, El Diente, and Ixtepete.",
        "connective": "but", "satellite": "the area is mostly urban",
        "nucleus": "there are also rural zones such as the Bosque La Primavera, El Diente and Ixtepete",
        "expected_matches": "nucleus",  # "but" here directly precedes/governs the nucleus clause
    },
    {
        "id": "1902-eventhough",
        "text": "Edward did not return to England for two years.",
        "connective": "when", "satellite": "he did not return for two years",
        "nucleus": "the barons swore allegiance to him",
        "expected_matches": "n/a-no-marker-in-this-proposition",
    },
    {
        "id": "2394-condition-merged",
        "text": "When the condition of perfect substitutability is not satisfied, the market is characterized by product differentiation.",
        "connective": "When", "satellite": "this condition is not satisfied",
        "nucleus": "the market is characterized by product differentiation",
        "expected_matches": "satellite",
    },
    {
        "id": "2405-if-merged",
        "text": "If service providers in some developing economies are not competitive enough to succeed on world markets, overseas companies will be attracted to invest.",
        "connective": "If", "satellite": "service providers in some developing economies are not competitive enough",
        "nucleus": "overseas companies will be attracted to invest",
        "expected_matches": "satellite",
    },
    {
        "id": "2618-despite-merged",
        "text": "Despite the negative description, the team won the 1986-87 Ashes series 2-1.",
        "connective": "Despite", "satellite": "being described as a team that can't bat, can't bowl and can't field",
        "nucleus": "they went on to win the series 2-1",
        "expected_matches": "satellite",
    },
    {
        "id": "2965-while-merged",
        "text": "While the mechanism by which survivin may regulate cell mitosis and cytokinesis is not known, the observations made on its localization during mitosis suggests strongly that it may play a role in these processes.",
        "connective": "While", "satellite": "the mechanism by which survivin may regulate cell mitosis and cytokinesis is not known",
        "nucleus": "the observations made on its localization during mitosis suggests strongly that it may play a role",
        "expected_matches": "satellite",
    },
    {
        "id": "2894-despite-merged",
        "text": "Despite modern depictions, hardly anyone actually rode in the wagons; it was too dusty, too rough, and too hard on the livestock.",
        "connective": "Despite", "satellite": "modern depictions",
        "nucleus": "hardly anyone actually rode in the wagons",
        "expected_matches": "satellite",
    },
    {
        "id": "4831-however-split",
        "text": "However, this CASM advantage has often been attributed solely to the lower labor costs of newly hired and lower pay grade workers of new start-up carriers.",
        "connective": "However", "satellite": "this CASM advantage has often been attributed solely to the lower labor costs",
        "nucleus": "these lower costs can also be attributed to the less complex aircraft fleets and route networks",
        "expected_matches": "satellite",
    },
    {
        "id": "2901-though-merged",
        "text": "Though Vaastu Shastra and Feng Shui contain certain similarities, Feng Shui is more commonly used throughout the world.",
        "connective": "Though", "satellite": "Vaastu Shastra and Feng Shui contain certain similarities",
        "nucleus": "Both Vaastu Shastra and Feng Shui try to harmonise the flow of energy",
        "expected_matches": "satellite",
    },
    {
        "id": "4611-arm4-but-merged",
        "text": "Counterflow configuration was found to obtain lower temperatures more suitable for home cooling, but crossflow configurations were adopted more widely due to simpler and less costly construction.",
        "connective": "but", "satellite": "crossflow configurations were adopted more widely due to simpler and less costly construction",
        "nucleus": "there was still Iggy and the Stooges",  # NOTE: mismatched pairing intentionally not fixed (spot-check parse quality only)
        "expected_matches": "n/a-mismatched-gt-skip-semantic-check",
    },
]


def main():
    results = []
    for c in CASES:
        doc = nlp(c["text"])
        markers = find_marker_tokens(doc)
        if not markers:
            results.append({**c, "parser_found_marker": False, "marker_clause": None,
                             "dep_info": None})
            print(f"[{c['id']}] NO MARKER TOKEN FOUND by spaCy (expected={c['expected_matches']})")
            continue
        # use the first marker occurrence matching the stated connective if possible
        conn_lower = c["connective"].lower().strip(",")
        chosen = next((m for m in markers if m.text.lower() == conn_lower), markers[0])
        clause_text, head_text, head_dep, marker_dep = clause_span_for_marker(chosen)
        results.append({
            **c, "parser_found_marker": True, "marker_token": chosen.text,
            "marker_dep": marker_dep, "clause_head": head_text, "clause_head_dep": head_dep,
            "marker_clause_text": clause_text,
        })
        print(f"[{c['id']}]")
        print(f"  marker={chosen.text!r} (dep={marker_dep}) head={head_text!r} (dep={head_dep})")
        print(f"  marker's clause subtree: {clause_text!r}")
        print(f"  expected_matches={c['expected_matches']}")
        print()

    json.dump(results, open("results/parser_domain_fit_part0c_report.json", "w"), indent=2)
    print(f"\nWrote {len(results)} cases to results/parser_domain_fit_part0c_report.json")


if __name__ == "__main__":
    main()
