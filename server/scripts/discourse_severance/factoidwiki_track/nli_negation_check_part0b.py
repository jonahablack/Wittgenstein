"""PART 0b: negation-specific NLI check.

Tests whether roberta-large-mnli correctly distinguishes genuine content
presence/absence under negation, not just topical overlap. For each
case: premise = atomized propositions joined into one text, hypothesis =
the ground-truth satellite or nucleus text (the negated clause). Ground
truth ("expected") is Claude's own direct reading of whether that exact
negated content is present, verbatim or as a clear paraphrase, in the
propositions -- not the (already known to be unreliable)
severance_a/severance_atomicrag judge verdict.

Three case types:
  - "present" (10 real corpus cases, drawn from Condition/Concession
    relations whose nucleus/satellite contains a negation word):
    negated content genuinely IS in the propositions. Expect ENTAILMENT.
  - "absent" (3 constructed by removing the one proposition carrying the
    negated content from an otherwise-real case): genuinely NOT present.
    Expect NOT ENTAILMENT (top label NEUTRAL or CONTRADICTION).
  - "contradicted" (2 constructed by flipping an existing proposition's
    polarity, e.g. deleting "not"): propositions assert the OPPOSITE of
    the hypothesis. Expect CONTRADICTION specifically, not just
    NOT ENTAILMENT.
"""

import json

import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

MODEL_NAME = "roberta-large-mnli"
tok = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME)
model.eval()
ID2LABEL = model.config.id2label


def nli(premise, hypothesis):
    inputs = tok(premise, hypothesis, return_tensors="pt", truncation=True, max_length=512)
    with torch.no_grad():
        logits = model(**inputs).logits
    probs = torch.softmax(logits, dim=1)[0]
    scores = {ID2LABEL[i]: float(probs[i]) for i in range(len(probs))}
    top = max(scores, key=scores.get)
    return top, scores


CASES = [
    # --- "present": real corpus cases, negated content genuinely there ---
    {"id": "1902-present", "type": "present", "hypothesis": "he did not return for two years",
     "propositions": ["Savage retribution was inflicted upon the rebels.", "Authority was restored to Henry.",
                       "The realm became peaceful.", "Edward left England to join Louis IX on the Ninth Crusade.",
                       "Edward was one of the last crusaders.", "Louis IX died before Edward's arrival.",
                       "Edward decided to continue the crusade after Louis IX's death.",
                       "Edward's small force only enabled him to capture Acre and launch a handful of raids.",
                       "Edward survived an assassination attempt.", "Edward left for Sicily later in the year.",
                       "Edward never participated in a crusade again.", "Henry III died.",
                       "Edward acceded to the throne after Henry III's death.",
                       "The barons swore allegiance to Edward.", "Edward did not return to England for two years."]},
    {"id": "1936-present", "type": "present", "hypothesis": "some say it does not include shoplifting",
     "propositions": ["In the Islamic legal system called Sharia, 'hudud' means limits or restrictions.",
                       "Sharia calls for 'Sariqa', which means theft, to be punished by amputation of the thief's hand.",
                       "This punishment is categorized as 'hadd', meaning a punishment that restrains or prevents further crime.",
                       "Sariqa is interpreted differently in different countries and by different scholars.",
                       "Some scholars say Sariqa does not include shoplifting.",
                       "In Saudi Arabia, shoplifters' hands may be amputated."]},
    {"id": "1972-present", "type": "present", "hypothesis": "taxes are not specifically addressed in the written terms of any treaties",
     "propositions": ["Taxes are not specifically addressed in the written terms of any treaties.",
                       "Assurances regarding taxation were clearly offered when at least some treaties were negotiated.",
                       "These treaties involve Canadian Crown and First Nations relations."]},
    {"id": "2056-present", "type": "present", "hypothesis": "no material from Commercial Zone or PiL's two live albums was included",
     "propositions": ["In 1993, Lydon worked on his memoirs.",
                       "Lydon's memoirs were first published in 1994 as Rotten: No Irish, No Blacks, No Dogs.",
                       "In 1996, Lydon regrouped with Steve Jones, Glen Matlock, and Paul Cook for the Sex Pistols' Filthy Lucre Tour.",
                       "Steve Jones, Glen Matlock, and Paul Cook were members of the Sex Pistols.",
                       "Lydon released a solo album, Psycho's Path, in 1997.",
                       "In 1999, a 4-disc PiL compilation called Plastic Box was released.",
                       "Plastic Box offered a more comprehensive retrospective of PiL's recorded output than the single-disc The Greatest Hits, So Far.",
                       "Plastic Box contained a mixture of previously released and unreleased material spanning PiL's entire career.",
                       "No material from Commercial Zone or PiL's two live albums was included in Plastic Box.",
                       "In the compilation's liner notes, Lydon wrote about his intentions to continue with PiL."]},
    {"id": "2848-present", "type": "present", "hypothesis": "Angel of Death did not chart",
     "propositions": ["Angel of Death is a song by Slayer.", "Angel of Death did not chart.",
                       "Critics highly praised Angel of Death while reviewing Reign in Blood.",
                       "Clay Jarvas is from Stylus Magazine.",
                       "Clay Jarvas observed that Angel of Death outperforms any band playing fast and/or heavy today.",
                       "Angel of Death's lyrics outline the horrors to come.",
                       "Angel of Death's music is fast, lean, and filthy.", "Adrien Begrand is from PopMatters.",
                       "Adrien Begrand called Angel of Death 'one of the most monumental songs in metal history'.",
                       "Angel of Death is the opening song of Reign in Blood."]},
    {"id": "3137-present", "type": "present", "hypothesis": "no contemporary evidence has been found to support the claim",
     "propositions": ["No contemporary evidence has been found to support the claim that 'The Wednesday Cricket Club' was formed in 1820.",
                       "It is commonly believed that 'The Wednesday Cricket Club' was formed in 1820.",
                       "An 1842 article in Bell's Life magazine states the club was founded in 1816."]},
    {"id": "3844-present", "type": "present", "hypothesis": "capitalism has not entered mainstream economics at the time of Smith",
     "propositions": ["In the works of Adam Smith, capitalism is made possible through competition which creates growth.",
                       "Adam Smith was an economist.",
                       "Capitalism had not entered mainstream economics at the time of Adam Smith.",
                       "Capitalism is vital to the construction of Adam Smith's ideal society.",
                       "One foundational block of capitalism is competition."]},
    {"id": "4738-present", "type": "present", "hypothesis": "Mallet's schemes were never actually applied",
     "propositions": ["Mallet's rigid wheelbase divided-drive schemes were never actually applied.",
                       "Francis Webb may have been inspired by Mallet's schemes in Britain.",
                       "Francis Webb conducted trials with an old single-driver converted into a 2-cylinder compound in 1878."]},
    {"id": "4765-present", "type": "present", "hypothesis": "his plantation was given to a white colonist, not to Johnson's children",
     "propositions": ["The history of slavery in Virginia involves the story of Anthony Johnson.",
                       "Anthony Johnson was an African who was freed soon after 1635.",
                       "Anthony Johnson later bought African indentured servants as laborers.",
                       "Anthony Johnson died in 1670.",
                       "On Anthony Johnson's death, his plantation was given to a white colonist, not to his children.",
                       "A judge ruled that Anthony Johnson was not a citizen of the colony because he was black."]},
    {"id": "3980-present-paraphrase", "type": "present", "hypothesis": "the state is not immune to freeway revolts",
     "propositions": ["The state's freeway network in California has expanded since the Arroyo Seco Parkway.",
                       "California has experienced freeway revolts.",
                       "Freeway revolts prevented a freeway in San Francisco between the Golden Gate Bridge and the San Francisco-Oakland Bay Bridge.",
                       "Freeway revolts prevented an expansion of I-710 through South Pasadena."]},

    # --- "absent": real premises with the ONE proposition carrying the
    # negated content deliberately removed -----------------------------
    {"id": "1902-absent", "type": "absent", "hypothesis": "he did not return for two years",
     "propositions": ["Savage retribution was inflicted upon the rebels.", "Authority was restored to Henry.",
                       "The realm became peaceful.", "Edward left England to join Louis IX on the Ninth Crusade.",
                       "Edward was one of the last crusaders.", "Louis IX died before Edward's arrival.",
                       "Henry III died.", "Edward acceded to the throne after Henry III's death.",
                       "The barons swore allegiance to Edward."]},
    {"id": "2056-absent", "type": "absent", "hypothesis": "no material from Commercial Zone or PiL's two live albums was included",
     "propositions": ["In 1993, Lydon worked on his memoirs.",
                       "In 1999, a 4-disc PiL compilation called Plastic Box was released.",
                       "Plastic Box contained a mixture of previously released and unreleased material spanning PiL's entire career.",
                       "In the compilation's liner notes, Lydon wrote about his intentions to continue with PiL."]},
    {"id": "4738-absent", "type": "absent", "hypothesis": "Mallet's schemes were never actually applied",
     "propositions": ["Francis Webb may have been inspired by Mallet's schemes in Britain.",
                       "Francis Webb conducted trials with an old single-driver converted into a 2-cylinder compound in 1878.",
                       "In 1882, Francis Webb introduced his first Experiment class with a similar divided-drive."]},

    # --- "contradicted": polarity flipped, propositions assert the
    # OPPOSITE of the hypothesis ----------------------------------------
    {"id": "1902-contradicted", "type": "contradicted", "hypothesis": "he did not return for two years",
     "propositions": ["Savage retribution was inflicted upon the rebels.", "Authority was restored to Henry.",
                       "Edward left England to join Louis IX on the Ninth Crusade.",
                       "The barons swore allegiance to Edward.",
                       "Edward returned to England within a year of leaving."]},
    {"id": "2848-contradicted", "type": "contradicted", "hypothesis": "Angel of Death did not chart",
     "propositions": ["Angel of Death is a song by Slayer.", "Angel of Death charted at number 12.",
                       "Critics highly praised Angel of Death while reviewing Reign in Blood."]},
]

EXPECTED_TOP = {"present": "ENTAILMENT", "absent": None, "contradicted": "CONTRADICTION"}


def main():
    results = []
    for c in CASES:
        premise = " ".join(c["propositions"])
        top, scores = nli(premise, c["hypothesis"])
        expected = EXPECTED_TOP[c["type"]]
        if c["type"] == "absent":
            passed = top != "ENTAILMENT"
        else:
            passed = top == expected
        results.append({
            "id": c["id"], "type": c["type"], "hypothesis": c["hypothesis"],
            "top_label": top, "scores": {k: round(v, 4) for k, v in scores.items()},
            "expected": expected or "NOT ENTAILMENT", "passed": passed,
        })
        print(f"[{'PASS' if passed else 'FAIL'}] {c['id']} ({c['type']}) -> {top} "
              f"(E={scores['ENTAILMENT']:.3f} N={scores['NEUTRAL']:.3f} C={scores['CONTRADICTION']:.3f}) "
              f"expected={expected or 'NOT ENTAILMENT'}")

    n_pass = sum(r["passed"] for r in results)
    print(f"\n{n_pass}/{len(results)} passed")
    json.dump(results, open("results/nli_negation_check_part0b_report.json", "w"), indent=2)


if __name__ == "__main__":
    main()
