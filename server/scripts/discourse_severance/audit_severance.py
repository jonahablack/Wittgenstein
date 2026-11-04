"""Post-hoc audit (A1 + A2) of the SAVED discourse-severance results.

This script re-reads `discourse_severance_report.json` and
`corpus_cache/elicitation_log.jsonl` -- it does NOT re-run corpus
sampling, relation elicitation, or atomization. The only new LLM calls
it makes are the A1 step-3 sub-clause-scoped judge calls (2 per
bundled-nucleus sentence: one against the saved Condition-A claims, one
against the saved Condition-B claims). Everything else is pure
string/structural analysis of saved data.

A1 (nucleus-bundling audit)
---------------------------
The original LLM-judge scores severance against the FULL elicited
nucleus. When that nucleus bundles two coordinated, independently-
governed assertions and the satellite only ever governed one of them, a
"severed" verdict can be wrong: atomization that narrowed the
connective's scope to the sub-clause it always modified is arguably
correct. This audit (1) flags bundled nuclei with a documented
structural heuristic, (2) re-examines the saved atomized outputs for
where the connective attached, (3) re-judges ONLY the bundled subset
with the sub-clause-scoped prompt (severance_detection.py's
`judge_prompt_subclause`, added alongside -- not replacing -- the
original `judge_prompt_full_nucleus`), and (4) reports adjusted
SECONDARY severance figures for both conditions (the originals are not
recomputed or replaced).

Bundling heuristic (documented per audit spec; pure string/structural,
no LLM call). A nucleus is flagged as bundled if either:

  Conjunction rules -- for an occurrence of "and"/"or"/"but" where the
  text LEFT of it contains a finite-verb marker (modal, finite
  auxiliary, or a curated list of corpus-common 3rd-person-singular
  verbs), and, scanning the tokens RIGHT of the conjunction (window of
  8 word tokens, aborting at any comma/semicolon, further coordinating
  conjunction, or subordinator -- so verbs inside embedded subordinate
  clauses such as "or, if there is no such outside container, ..." do
  NOT count):
    (a) CLEAR: a modal or finite auxiliary appears (a second full
        predicate, e.g. ", and appropriate pediatric dosage information
        MUST be given");
    (b) CLEAR: the first token after the conjunction is a curated
        finite -s verb (shared-subject VP coordination, e.g. ", and
        IDENTIFIES the drug as a sunscreen");
    (c) BORDERLINE: the left side contains a modal and the conjunction
        is followed (after at most 2 skippable adverbs) by a curated
        base-form verb (shared-modal continuation, e.g. "shall follow
        the title and immediately PRECEDE the heading").

  Participial rule --
    (d) BORDERLINE: a comma followed (after at most 3 tokens drawn from
        -ly adverbs / "and" / "or") by a past participle that ends the
        phrase into "by", a comma, or end-of-nucleus, with a verb-
        bearing left context (a second passive predication attached to
        the same subject, e.g. ", PRECEDED BY the identifying number
        ..." or ", securely and rigidly SUPPORTED,").

  NP-internal coordination ("terms and conditions", "a doctor or
  pharmacist", "each heading and subheading") is excluded by the
  left-verb requirement plus the right-scan rules above. Borderline
  cases are INCLUDED in the bundled subset but marked borderline
  throughout, per the audit spec.

Governed-sub-clause assignment: the flagged nucleus is split at the
chosen coordination site into two sub-clauses; the satellite's position
in the ORIGINAL sentence (located via difflib matching blocks after
normalization) is compared against each sub-clause's span. Overlap wins;
otherwise the nearest sub-clause ENDING BEFORE the satellite wins
(postposed/embedded modifiers attach to the preceding clause); a
satellite preceding the whole coordination is assigned the first
sub-clause, with an explicit note that sentence-initial satellites may
semantically scope over the whole coordination.

A2 (severed-with-no-split audit)
--------------------------------
Finds saved atomization outputs whose claims, joined back together, are
identical or near-identical to the source sentence (normalization:
lowercase; curly quotes/dashes folded; every non-alphanumeric character
dropped; whitespace collapsed. Near-identical = difflib.SequenceMatcher
ratio >= 0.95 on the normalized strings). Cross-references the no-split
set against the rule-based check's "not applicable" cases, and prepares
(does NOT perform) a human review sheet for a seeded random sample of 20
of the 286 Condition-classified elicitation records
(`manual_condition_audit.md`, tallied later by `tally_manual_audit.py`).

Usage
-----
    venv/bin/python server/scripts/discourse_severance/audit_severance.py             # full audit (makes 2*len(bundled) LLM calls)
    venv/bin/python server/scripts/discourse_severance/audit_severance.py --skip-llm  # structural analysis only, no API calls
"""

import argparse
import difflib
import json
import os
import random
import re
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SERVER_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

# Importing run_experiments runs its _load_server_env() at import time --
# the same way the original experiment loaded server/.env for api_call.py.
from scripts.discourse_severance import run_experiments  # noqa: E402,F401
from scripts.discourse_severance import severance_detection  # noqa: E402
from scripts.discourse_severance.corpus import content_keywords  # noqa: E402
from components.risk_triage import _contains_phrase  # noqa: E402

REPORT_PATH = os.path.join(SCRIPT_DIR, "discourse_severance_report.json")
ELICITATION_LOG = os.path.join(SCRIPT_DIR, "corpus_cache", "elicitation_log.jsonl")
ADDENDUM_PATH = os.path.join(SCRIPT_DIR, "audit_addendum.json")
MANUAL_SHEET_PATH = os.path.join(SCRIPT_DIR, "manual_condition_audit.md")

# Seed for the A2 manual-audit sample draw (recorded in the sheet and the
# addendum JSON so the draw is reproducible).
MANUAL_AUDIT_SEED = 20260807
MANUAL_AUDIT_SAMPLE_SIZE = 20
# Suspected mislabeled-Purpose check case (see audit spec): included in
# the sheet even if the random draw misses it, labeled non-random then.
CHECK_CASE_SUBSTRING = "to maximize capture of forward scattered radiation"

NO_SPLIT_SIMILARITY_THRESHOLD = 0.95

# Methodology note carried into the addendum JSON: the FIRST draft of the
# sub-clause judge prompt (scoping note only, no explicit evidence
# requirement) returned preserved=True for all 16 bundled-subset calls,
# INCLUDING six Condition-A outputs in which the connective was absent
# from every claim -- its reasoning showed it judging from the relation
# description rather than from the atomized claims. Those 16 verdicts
# were discarded as claims-blind, and the prompt now in
# severance_detection.py (judge_prompt_subclause) adds an explicit
# requirement that the satellite's qualification must survive in the
# claims themselves. Both prompt iterations' full text history is in git;
# only the tightened prompt's verdicts are reported.
JUDGE_PROMPT_ITERATION_NOTE = (
    "The first draft of judge_prompt_subclause was discarded as "
    "claims-blind (it returned preserved=True for all 16 calls, including "
    "six cases where the connective was absent from every atomized "
    "claim). The reported verdicts come from the tightened prompt that "
    "explicitly requires the satellite's qualification to survive in the "
    "claims. 32 LLM calls were spent across both iterations; 16 retained."
)

# --- A1 bundling heuristic wordlists -----------------------------------------

MODALS = {"shall", "must", "may", "might", "will", "would", "should", "can",
          "could"}
AUXILIARIES = {"is", "are", "was", "were", "has", "have", "had", "do", "does",
               "did"}
# Corpus-common finite 3rd-person-singular verbs (curated from this
# corpus's regulatory register; used for the left-context verb test and
# for rule (b)'s shared-subject coordination).
FINITE_S_VERBS = {"contains", "identifies", "means", "applies", "requires",
                  "depends", "appears", "states", "varies", "remains",
                  "exceeds", "includes", "provides", "expresses", "precedes",
                  "follows"}
# Curated base-form verbs for rule (c)'s shared-modal continuation.
BASE_VERBS = {"precede", "follow", "appear", "contain", "include", "apply",
              "require", "state", "bear", "express", "submit", "provide",
              "describe", "identify", "mean", "comply", "recommend", "agree",
              "occur"}
SKIP_ADVERBS = {"therefore", "thus", "hence", "also", "then", "thereafter"}
SUBORDINATORS = {"if", "when", "unless", "because", "since", "while", "that",
                 "which", "who", "where", "as", "whether"}
CONJUNCTIONS = {"and", "or", "but"}
RIGHT_SCAN_WINDOW = 8  # word tokens


def _word(token):
    """Lowercased token with non-alphanumeric edge characters stripped."""
    return token.strip(",;.“”\"'()").lower()


def _is_skippable_adverb(token):
    w = _word(token)
    return w.endswith("ly") or w in SKIP_ADVERBS


def _tokenize_keep_punct(text):
    """Word tokens plus standalone ','/';' tokens."""
    return re.findall(r"[,;]|[^\s,;]+", text)


def _left_has_finite_verb(text):
    words = {_word(t) for t in _tokenize_keep_punct(text)}
    return bool(words & (MODALS | AUXILIARIES | FINITE_S_VERBS))


def _left_has_modal(text):
    words = {_word(t) for t in _tokenize_keep_punct(text)}
    return bool(words & MODALS)


def _scan_right_of_conjunction(right_text, left_text):
    """Apply rules (a)/(b)/(c) to the text right of a conjunction.
    Returns (rule, clarity) or (None, None)."""
    tokens = _tokenize_keep_punct(right_text)

    # Rule (b): first token is a curated finite -s verb (shared subject).
    if tokens and _word(tokens[0]) in FINITE_S_VERBS:
        return "b_shared_subject_finite_verb", "clear"

    # Rule (a): modal/auxiliary within the window, no interruptions.
    seen_words = 0
    for tok in tokens:
        if tok in {",", ";"}:
            break
        w = _word(tok)
        if w in CONJUNCTIONS or w in SUBORDINATORS:
            break
        seen_words += 1
        if seen_words > RIGHT_SCAN_WINDOW:
            break
        if w in MODALS or w in AUXILIARIES:
            return "a_second_full_predicate", "clear"

    # Rule (c): shared-modal continuation (borderline).
    if _left_has_modal(left_text):
        idx = 0
        skipped = 0
        while idx < len(tokens) and skipped < 2 and _is_skippable_adverb(tokens[idx]):
            idx += 1
            skipped += 1
        if idx < len(tokens) and _word(tokens[idx]) in BASE_VERBS:
            return "c_shared_modal_continuation", "borderline"

    return None, None


_PARTICIPIAL_RE = re.compile(
    r",\s*((?:(?:[A-Za-z]+ly|and|or)\s+){0,3})([A-Za-z]{3,}ed)(\s+by\b|\s*,|\s*$)"
)


def detect_bundling_sites(nucleus):
    """Return every coordination site in the nucleus that the heuristic
    flags, each as a dict with rule, clarity, and the two sub-clauses."""
    sites = []

    for m in re.finditer(r"\b(and|or|but)\b", nucleus, flags=re.IGNORECASE):
        left = nucleus[:m.start()]
        right = nucleus[m.end():]
        if not _left_has_finite_verb(left):
            continue
        rule, clarity = _scan_right_of_conjunction(right, left)
        if rule is None:
            continue
        sites.append({
            "rule": rule,
            "clarity": clarity,
            "conjunction": m.group(1),
            "position": m.start(),
            "subclause_1": left.strip().rstrip(",").strip(),
            "subclause_2": right.strip().rstrip(".").strip(),
        })

    for m in _PARTICIPIAL_RE.finditer(nucleus):
        left = nucleus[:m.start()]
        if not _left_has_finite_verb(left):
            continue
        participle = m.group(2)
        if len(participle) <= 4:  # excludes e.g. "used"
            continue
        # Participial phrase runs from just after the comma to the next
        # comma or end of nucleus.
        phrase_start = m.start(1) if m.group(1) else m.start(2)
        next_comma = nucleus.find(",", phrase_start)
        phrase_end = next_comma if next_comma != -1 else len(nucleus)
        phrase = nucleus[phrase_start:phrase_end].strip().rstrip(".").strip()
        remainder = (nucleus[:m.start()] + nucleus[phrase_end:]).strip().rstrip(",.").strip()
        sites.append({
            "rule": "d_participial_second_predication",
            "clarity": "borderline",
            "conjunction": None,
            "position": m.start(),
            "subclause_1": remainder,
            "subclause_2": phrase,
        })

    return sites


def choose_bundling_site(sites):
    """Prefer the earliest CLEAR site, else the earliest borderline one."""
    clear = [s for s in sites if s["clarity"] == "clear"]
    pool = clear if clear else sites
    return min(pool, key=lambda s: s["position"])


# --- governed sub-clause assignment ------------------------------------------


def _norm_for_matching(text):
    text = text.lower()
    for a, b in [("“", '"'), ("”", '"'), ("‘", "'"),
                 ("’", "'"), ("—", "-"), ("–", "-")]:
        text = text.replace(a, b)
    return re.sub(r"\s+", " ", text).strip()


def _span_in_sentence(sentence_norm, fragment_norm, min_block=5):
    """(start, end) span in sentence_norm covered by matching blocks of
    fragment_norm, or None if nothing matches."""
    sm = difflib.SequenceMatcher(None, sentence_norm, fragment_norm, autojunk=False)
    blocks = [bl for bl in sm.get_matching_blocks() if bl.size >= min_block]
    if not blocks:
        return None
    return (min(bl.a for bl in blocks), max(bl.a + bl.size for bl in blocks))


def assign_governed_subclause(sentence, satellite, subclause_1, subclause_2):
    """Which sub-clause did the satellite originally modify? See module
    docstring for the adjacency rule."""
    s_norm = _norm_for_matching(sentence)
    sat_span = _span_in_sentence(s_norm, _norm_for_matching(satellite))
    c1_span = _span_in_sentence(s_norm, _norm_for_matching(subclause_1))
    c2_span = _span_in_sentence(s_norm, _norm_for_matching(subclause_2))
    if not (sat_span and c1_span and c2_span):
        raise RuntimeError(
            "Could not locate satellite/sub-clauses in the original sentence "
            f"for adjacency assignment: sat={sat_span} c1={c1_span} c2={c2_span}"
        )

    def overlap(a, b):
        return max(0, min(a[1], b[1]) - max(a[0], b[0]))

    ov1, ov2 = overlap(sat_span, c1_span), overlap(sat_span, c2_span)
    if ov1 or ov2:
        governed = 1 if ov1 >= ov2 else 2
        note = "satellite span overlaps this sub-clause's span in the original sentence"
    else:
        preceding = [(i, sp) for i, sp in [(1, c1_span), (2, c2_span)]
                     if sp[1] <= sat_span[0]]
        if preceding:
            governed = min(preceding, key=lambda x: sat_span[0] - x[1][1])[0]
            note = ("postposed/embedded modifier: attached to the nearest "
                    "sub-clause ending before the satellite")
        else:
            governed = 1 if c1_span[0] < c2_span[0] else 2
            note = ("satellite precedes the whole coordination; adjacency "
                    "assigns the first sub-clause (caveat: sentence-initial "
                    "satellites may semantically scope over the whole "
                    "coordination)")
    return {
        "governed_subclause_index": governed,
        "governed_subclause": subclause_1 if governed == 1 else subclause_2,
        "assignment_note": note,
    }


# --- A1 step 2: connective attachment in the saved atomized outputs ----------


def connective_attachment(claims, connective, subclause_1, subclause_2,
                          governed_index):
    """Where does the elicited connective sit in the saved atomized
    output, and does that claim's content belong to the sub-clause the
    satellite originally governed? Pure string analysis, no LLM."""
    conn = (connective or "").strip().lower()
    if not conn:
        return {"connective_present": False, "attachment": None,
                "same_subclause_as_governed": None,
                "detail": "no connective was elicited"}

    hits = [c for c in claims if _contains_phrase(c.lower(), conn)]
    if not hits:
        return {"connective_present": False, "attachment": None,
                "same_subclause_as_governed": False,
                "detail": "connective absent from every atomized claim"}

    kw1, kw2 = content_keywords(subclause_1), content_keywords(subclause_2)
    attachments = []
    for c in hits:
        kw = content_keywords(c)
        cov1 = len(kw & kw1) / len(kw1) if kw1 else 0.0
        cov2 = len(kw & kw2) / len(kw2) if kw2 else 0.0
        if cov1 >= 0.6 and cov2 >= 0.6:
            attachments.append("both")
        elif cov1 > cov2:
            attachments.append(1)
        elif cov2 > cov1:
            attachments.append(2)
        else:
            attachments.append("ambiguous")

    same = any(a == "both" or a == governed_index for a in attachments)
    return {
        "connective_present": True,
        "attachment": attachments if len(attachments) > 1 else attachments[0],
        "same_subclause_as_governed": same,
        "detail": (f"connective found in {len(hits)} claim(s); keyword-overlap "
                   f"attachment per claim: {attachments}"),
    }


# --- A2: no-split detection --------------------------------------------------


def normalize_for_nosplit(text):
    """Lowercase; fold curly quotes/dashes; drop every non-alphanumeric
    character; collapse whitespace. Documented in the module docstring."""
    text = _norm_for_matching(text)
    text = re.sub(r"[^0-9a-z\s]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def no_split_check(sentence, claims):
    joined = normalize_for_nosplit(" ".join(claims))
    source = normalize_for_nosplit(sentence)
    if joined == source:
        return {"no_split": True, "kind": "identical", "similarity": 1.0}
    ratio = difflib.SequenceMatcher(None, joined, source, autojunk=False).ratio()
    if ratio >= NO_SPLIT_SIMILARITY_THRESHOLD:
        return {"no_split": True, "kind": "near_identical", "similarity": round(ratio, 4)}
    return {"no_split": False, "kind": "split", "similarity": round(ratio, 4)}


# --- A2: manual audit sheet ---------------------------------------------------

SHEET_INSTRUCTIONS = """# Manual audit: Condition-classified elicitation records

**This sheet is for a HUMAN reviewer.** Verdicts are deliberately blank:
do not fill them in with a model. For each item, read the sentence and
the elicited relation fields, then write ONE of the following labels on
the `VERDICT:` line:

- `genuine-Condition` -- the sentence really does carry a Condition
  relation (the nucleus holds only if the satellite holds).
- `mislabeled-Purpose` -- the "condition" is really a purpose/in-order-to
  clause (e.g. "to maximize capture of forward scattered radiation").
- `mislabeled-Result` -- the "condition" is really a result/consequence.
- `mislabeled-Elaboration` -- the satellite is just supporting detail.
- `other` -- anything else (add a word of explanation on the NOTES line).

When done, run:

    venv/bin/python server/scripts/discourse_severance/tally_manual_audit.py

Sampling: {n_random} records drawn uniformly at random (seed={seed},
`random.Random(seed).sample`) from all {pool_size} sentences the
elicitation step classified as Condition across both corpus parts
(deterministic pool order: sorted by part label, then sentence index).
Items marked `[NON-RANDOM CHECK CASE]` were added deliberately and are
EXCLUDED from the random mislabel-rate estimate by the tally script.
"""


def build_manual_sheet(condition_pool, seed, sample_size):
    rng = random.Random(seed)
    sample = rng.sample(condition_pool, sample_size)
    sampled_keys = {(r["part_label"], r["sentence_index"]) for r in sample}

    check_case = [r for r in condition_pool
                  if CHECK_CASE_SUBSTRING in r["sentence"]]
    check_case_note = None
    if not check_case:
        check_case_note = ("check case NOT found in the Condition-classified "
                          "pool -- not added")
    else:
        cc = check_case[0]
        if (cc["part_label"], cc["sentence_index"]) in sampled_keys:
            check_case_note = ("check case was already drawn by the random "
                              "sample -- no extra item added")
        else:
            check_case_note = ("check case added as a labeled NON-RANDOM item "
                              "beyond the random sample")
            sample = sample + [cc]

    lines = [SHEET_INSTRUCTIONS.format(
        n_random=sample_size, seed=seed, pool_size=len(condition_pool))]
    for i, rec in enumerate(sample, start=1):
        nonrandom = (check_case and rec is check_case[0]
                     and (check_case[0]["part_label"], check_case[0]["sentence_index"]) not in sampled_keys)
        tag = "[NON-RANDOM CHECK CASE]" if nonrandom else "[RANDOM]"
        lines += [
            f"## Item {i:02d} {tag} part={rec['part_label']} sentence_index={rec['sentence_index']}",
            "",
            f"- Sentence: {rec['sentence']}",
            f"- Elicited nucleus: {rec['nucleus']!r}",
            f"- Elicited satellite: {rec['satellite']!r}",
            f"- Elicited connective: {rec['connective']!r}",
            "- VERDICT: ",
            "- NOTES: ",
            "",
        ]
    return "\n".join(lines), sample, check_case_note


# --- main ---------------------------------------------------------------------


def short_id(rec):
    part = "cfr21p201" if "201" in rec["part_label"] else "cfr29p1910"
    return f"{part}:{rec['sentence_index']}"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--skip-llm", action="store_true",
                        help="structural analysis only; skip the sub-clause "
                             "judge LLM calls (addendum will mark them as "
                             "not run)")
    args = parser.parse_args(argv)

    with open(REPORT_PATH, encoding="utf-8") as fh:
        report = json.load(fh)
    exp1 = report["experiment_1"]["records"]
    if len(exp1) != 47:
        raise RuntimeError(f"Expected 47 Experiment-1 records, found {len(exp1)}")

    # ---------------- A1 step 1: bundled-nucleus detection ----------------
    print("=== A1 step 1: bundled-nucleus detection (structural heuristic) ===")
    a1_records = []
    for rec in exp1:
        sites = detect_bundling_sites(rec["nucleus"])
        entry = {
            "id": short_id(rec),
            "part_label": rec["part_label"],
            "sentence_index": rec["sentence_index"],
            "relation_type": rec["relation_type"],
            "bundled": bool(sites),
            "sites": sites,
        }
        if sites:
            site = choose_bundling_site(sites)
            entry["chosen_site"] = site
            entry["clarity"] = ("clear" if any(s["clarity"] == "clear" for s in sites)
                                else "borderline")
            governed = assign_governed_subclause(
                rec["sentence"], rec["satellite"],
                site["subclause_1"], site["subclause_2"])
            entry.update(governed)
            print(f"  BUNDLED [{entry['clarity']:10s}] {entry['id']} "
                  f"({rec['relation_type']}) rule={site['rule']}")
            print(f"    sub-clause 1: {site['subclause_1'][:90]}")
            print(f"    sub-clause 2: {site['subclause_2'][:90]}")
            print(f"    satellite governs sub-clause {governed['governed_subclause_index']} "
                  f"({governed['assignment_note']})")
        a1_records.append(entry)

    bundled = [e for e in a1_records if e["bundled"]]
    n_borderline = sum(1 for e in bundled if e["clarity"] == "borderline")
    print(f"\nBundled nuclei: {len(bundled)}/47 ({n_borderline} borderline)")

    # ---------------- A1 step 2: connective attachment (read-only) --------
    print("\n=== A1 step 2: connective attachment in saved atomized outputs ===")
    by_key = {(r["part_label"], r["sentence_index"]): r for r in exp1}
    for entry in bundled:
        rec = by_key[(entry["part_label"], entry["sentence_index"])]
        site = entry["chosen_site"]
        for cond, claims_key in [("a", "condition_a_claims"), ("b", "condition_b_claims")]:
            att = connective_attachment(
                rec[claims_key], rec["connective"],
                site["subclause_1"], site["subclause_2"],
                entry["governed_subclause_index"])
            entry[f"attachment_{cond}"] = att
            print(f"  {entry['id']} cond {cond.upper()}: present={att['connective_present']} "
                  f"attachment={att['attachment']} same_as_governed={att['same_subclause_as_governed']}")

    # ---------------- A1 step 3: sub-clause-scoped judge ------------------
    if args.skip_llm:
        print("\n=== A1 step 3: SKIPPED (--skip-llm) ===")
    else:
        print(f"\n=== A1 step 3: sub-clause judge on {len(bundled)} bundled "
              f"sentences x 2 conditions ({2*len(bundled)} LLM calls) ===")
        for entry in bundled:
            rec = by_key[(entry["part_label"], entry["sentence_index"])]
            relation = {k: rec[k] for k in ("relation_type", "nucleus",
                                             "satellite", "connective")}
            for cond, claims_key in [("a", "condition_a_claims"), ("b", "condition_b_claims")]:
                verdict = severance_detection.llm_judge_severance_subclause(
                    rec["sentence"], relation, rec[claims_key],
                    entry["governed_subclause"])
                if verdict["preserved"] is None:
                    raise RuntimeError(
                        f"Sub-clause judge call failed for {entry['id']} "
                        f"condition {cond.upper()}: {verdict['reasoning']} -- "
                        "refusing to compute adjusted figures from missing data.")
                entry[f"subclause_judge_{cond}"] = verdict
                orig = rec[f"severance_{cond}"]["llm_judge_preserved"]
                entry[f"verdict_change_{cond}"] = {
                    "original_full_nucleus_preserved": orig,
                    "subclause_preserved": verdict["preserved"],
                    "changed": orig != verdict["preserved"],
                }
                print(f"  {entry['id']} cond {cond.upper()}: "
                      f"full-nucleus preserved={orig} -> sub-clause "
                      f"preserved={verdict['preserved']}"
                      f"{'  [CHANGED]' if orig != verdict['preserved'] else ''}")

    # ---------------- A1 step 4: adjusted secondary figures ---------------
    a1_summary = {
        "n_experiment_1": 47,
        "n_bundled": len(bundled),
        "n_bundled_borderline": n_borderline,
        "n_bundled_clear": len(bundled) - n_borderline,
        "bundled_ids": [e["id"] for e in bundled],
        "bundled_borderline_ids": [e["id"] for e in bundled if e["clarity"] == "borderline"],
    }
    if not args.skip_llm:
        bundled_by_key = {(e["part_label"], e["sentence_index"]): e for e in bundled}

        def adjusted_counts(cond, subset_pred):
            """Severed count over all 47 with bundled-subset (filtered by
            subset_pred) verdicts swapped for the sub-clause verdicts."""
            severed = 0
            for rec in exp1:
                key = (rec["part_label"], rec["sentence_index"])
                entry = bundled_by_key.get(key)
                if entry is not None and subset_pred(entry):
                    preserved = entry[f"subclause_judge_{cond}"]["preserved"]
                else:
                    preserved = rec[f"severance_{cond}"]["llm_judge_preserved"]
                if preserved is False:
                    severed += 1
            return severed

        adj_a = adjusted_counts("a", lambda e: True)
        adj_b = adjusted_counts("b", lambda e: True)
        adj_a_clear = adjusted_counts("a", lambda e: e["clarity"] == "clear")
        adj_b_clear = adjusted_counts("b", lambda e: e["clarity"] == "clear")
        a1_summary["adjusted_secondary_figures"] = {
            "note": ("Sub-clause-scoped ALTERNATIVE reading: bundled-subset "
                     "sentences use the judge_prompt_subclause verdict, all "
                     "other sentences keep their original judge_prompt_full_"
                     "nucleus verdict. NOT a replacement of the original "
                     "headline numbers."),
            "original_condition_a_severed": "39/47 (83.0%)",
            "original_condition_b_severed": "26/47 (55.3%)",
            "adjusted_condition_a_severed": f"{adj_a}/47 ({100*adj_a/47:.1f}%)",
            "adjusted_condition_b_severed": f"{adj_b}/47 ({100*adj_b/47:.1f}%)",
            "adjusted_condition_a_severed_clear_bundles_only":
                f"{adj_a_clear}/47 ({100*adj_a_clear/47:.1f}%)",
            "adjusted_condition_b_severed_clear_bundles_only":
                f"{adj_b_clear}/47 ({100*adj_b_clear/47:.1f}%)",
        }

        # ---------------- A1 step 5: exclusion list -----------------------
        exclusions = []
        for entry in bundled:
            rec = by_key[(entry["part_label"], entry["sentence_index"])]
            if (rec["severance_a"]["llm_judge_preserved"] is False
                    and entry["subclause_judge_a"]["preserved"] is True):
                exclusions.append({
                    "id": entry["id"],
                    "part_label": entry["part_label"],
                    "sentence_index": entry["sentence_index"],
                    "relation_type": entry["relation_type"],
                    "clarity": entry["clarity"],
                    "sentence": rec["sentence"],
                })
        a1_summary["future_eval_exclusion_list"] = {
            "note": ("Sentences scored severed=True under Condition A by the "
                     "ORIGINAL full-nucleus judge that FLIP to preserved "
                     "under the sub-clause judge. These define exclusions "
                     "from a future experiment's evaluation set."),
            "ids": [x["id"] for x in exclusions],
            "records": exclusions,
        }
        print("\n=== A1 adjusted secondary figures (sub-clause-scoped alternative reading) ===")
        for k, v in a1_summary["adjusted_secondary_figures"].items():
            if k != "note":
                print(f"  {k}: {v}")
        print(f"  exclusion list (A severed -> sub-clause preserved): "
              f"{a1_summary['future_eval_exclusion_list']['ids']}")

    # ---------------- A2 step 1: no-split detection -----------------------
    print("\n=== A2 step 1: severed-with-no-split detection ===")
    a2_records = []
    for rec in exp1:
        row = {"id": short_id(rec),
               "part_label": rec["part_label"],
               "sentence_index": rec["sentence_index"],
               "relation_type": rec["relation_type"],
               "connective": rec["connective"]}
        for cond, claims_key in [("a", "condition_a_claims"), ("b", "condition_b_claims")]:
            chk = no_split_check(rec["sentence"], rec[claims_key])
            chk["n_claims"] = len(rec[claims_key])
            chk["llm_judge_preserved"] = rec[f"severance_{cond}"]["llm_judge_preserved"]
            chk["rule_based_preserved"] = rec[f"severance_{cond}"]["rule_based_preserved"]
            chk["rule_based_not_applicable"] = rec[f"severance_{cond}"]["rule_based_preserved"] is None
            row[f"condition_{cond}"] = chk
        a2_records.append(row)
        for cond in ("a", "b"):
            chk = row[f"condition_{cond}"]
            if chk["no_split"]:
                print(f"  NO-SPLIT {row['id']} cond {cond.upper()} "
                      f"({chk['kind']}, sim={chk['similarity']}, "
                      f"{chk['n_claims']} claim(s)) llm_preserved="
                      f"{chk['llm_judge_preserved']} rule_based_na="
                      f"{chk['rule_based_not_applicable']} "
                      f"rel={row['relation_type']} conn={row['connective']!r}")

    # ---------------- A2 step 2: overlap with rule-based not-applicable ---
    wordlist = severance_detection.CONNECTIVE_WORDLIST
    sentence_by_key = {(r["part_label"], r["sentence_index"]): r["sentence"]
                       for r in exp1}
    a2_summary = {}
    for cond in ("a", "b"):
        no_split = [r for r in a2_records if r[f"condition_{cond}"]["no_split"]]
        na = [r for r in a2_records if r[f"condition_{cond}"]["rule_based_not_applicable"]]
        both = [r for r in no_split if r[f"condition_{cond}"]["rule_based_not_applicable"]]
        severed_no_split = [r for r in no_split
                            if r[f"condition_{cond}"]["llm_judge_preserved"] is False]
        # STRICT no-split: a single claim reproducing the sentence -- the
        # atomizer produced no split at all, so "severed=True" there is
        # the category error this audit targets. Multi-claim joined-
        # identical outputs DID split (near-verbatim segmentation) and
        # are reported separately.
        strict = [r for r in no_split if r[f"condition_{cond}"]["n_claims"] == 1]
        strict_severed = [r for r in strict
                          if r[f"condition_{cond}"]["llm_judge_preserved"] is False]
        conn_not_in_wordlist = [
            r for r in no_split
            if not any(_contains_phrase((r["connective"] or "").lower(), w)
                       for w in wordlist)
        ]
        conn_absent_from_source = [
            r for r in no_split
            if (r["connective"] or "").strip()
            and not _contains_phrase(
                sentence_by_key[(r["part_label"], r["sentence_index"])].lower(),
                (r["connective"] or "").strip().lower())
        ]
        a2_summary[f"condition_{cond}"] = {
            "n_no_split": len(no_split),
            "no_split_ids": [r["id"] for r in no_split],
            "n_no_split_single_claim_strict": len(strict),
            "no_split_single_claim_strict_ids": [r["id"] for r in strict],
            "n_no_split_single_claim_strict_scored_severed": len(strict_severed),
            "no_split_single_claim_strict_scored_severed_ids": [r["id"] for r in strict_severed],
            "n_rule_based_not_applicable": len(na),
            "n_no_split_and_not_applicable": len(both),
            "n_no_split_scored_severed_by_llm_judge": len(severed_no_split),
            "no_split_scored_severed_ids": [r["id"] for r in severed_no_split],
            "n_no_split_with_connective_outside_wordlist": len(conn_not_in_wordlist),
            "n_no_split_with_elicited_connective_absent_from_source": len(conn_absent_from_source),
            "no_split_relation_types": sorted(r["relation_type"] for r in no_split),
            "no_split_connectives": sorted((r["connective"] or "") for r in no_split),
        }
        s = a2_summary[f"condition_{cond}"]
        print(f"\n  Condition {cond.upper()}: no-split={s['n_no_split']} "
              f"(strict single-claim={s['n_no_split_single_claim_strict']}), "
              f"rule-based-not-applicable={s['n_rule_based_not_applicable']}, "
              f"overlap={s['n_no_split_and_not_applicable']}, "
              f"no-split-yet-severed={s['n_no_split_scored_severed_by_llm_judge']} "
              f"(strict={s['n_no_split_single_claim_strict_scored_severed']}), "
              f"no-split-connective-outside-wordlist={s['n_no_split_with_connective_outside_wordlist']}, "
              f"elicited-connective-absent-from-source={s['n_no_split_with_elicited_connective_absent_from_source']}")

    # ---------------- A2 step 3: manual audit sheet (prep only) -----------
    print("\n=== A2 step 3: manual audit sheet (PREPARED, not performed) ===")
    with open(ELICITATION_LOG, encoding="utf-8") as fh:
        elicited = [json.loads(line) for line in fh]
    condition_pool = sorted(
        (r for r in elicited if r.get("relation_type") == "Condition"),
        key=lambda r: (r["part_label"], r["sentence_index"]))
    print(f"  Condition-classified pool size: {len(condition_pool)}")
    if len(condition_pool) != 286:
        raise RuntimeError(
            f"Expected 286 Condition-classified elicitation records, found "
            f"{len(condition_pool)} -- pool construction is wrong, refusing "
            "to sample.")
    sheet_text, sample, check_case_note = build_manual_sheet(
        condition_pool, MANUAL_AUDIT_SEED, MANUAL_AUDIT_SAMPLE_SIZE)
    with open(MANUAL_SHEET_PATH, "w", encoding="utf-8") as fh:
        fh.write(sheet_text)
    print(f"  Wrote {MANUAL_SHEET_PATH} ({len(sample)} items; seed="
          f"{MANUAL_AUDIT_SEED}; {check_case_note})")

    # ---------------- write addendum JSON ---------------------------------
    addendum = {
        "audit_date": "2026-08-07",
        "source_report": os.path.basename(REPORT_PATH),
        "note": ("Post-hoc audit of SAVED results. Original headline numbers "
                 "are untouched; A1 figures are a sub-clause-scoped "
                 "alternative reading reported alongside them."),
        "a1_nucleus_bundling": {
            "summary": a1_summary,
            "records": [e for e in a1_records if e["bundled"]],
            "non_bundled_ids": [e["id"] for e in a1_records if not e["bundled"]],
            "llm_calls_made": 0 if args.skip_llm else 2 * len(bundled),
            "judge_prompt_iteration_note": JUDGE_PROMPT_ITERATION_NOTE,
        },
        "a2_no_split": {
            "normalization": ("lowercase; curly quotes/dashes folded; all "
                              "non-alphanumeric characters dropped; whitespace "
                              "collapsed; near-identical = SequenceMatcher "
                              f"ratio >= {NO_SPLIT_SIMILARITY_THRESHOLD}"),
            "summary": a2_summary,
            "records": a2_records,
        },
        "a2_manual_audit_prep": {
            "seed": MANUAL_AUDIT_SEED,
            "sample_size_random": MANUAL_AUDIT_SAMPLE_SIZE,
            "pool_size": len(condition_pool),
            "check_case_note": check_case_note,
            "sheet_path": os.path.basename(MANUAL_SHEET_PATH),
            "sampled_ids": [short_id(r) for r in sample],
        },
    }
    with open(ADDENDUM_PATH, "w", encoding="utf-8") as fh:
        json.dump(addendum, fh, indent=2, ensure_ascii=False)
    print(f"\nWrote {ADDENDUM_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
