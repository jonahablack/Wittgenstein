"""Triple-aware severance judge for NuggetIndex's `LLMExtractor` output.

JUDGE-DESIGN DECISION (the task that created this track asked this to be
made explicitly and documented, the same way ../condition_b_atomizer.py's
and ../severance_judge_paragraph.py's docstrings document their own
design choices):

NuggetIndex's atomic unit is a (subject, predicate, object) triple with a
normalized, often camelCase predicate (see
../nuggetindex_extractor_adapter.py's docstring and
extractors/prompts/extraction.md's "Predicate normalisation (strict)"
section -- e.g. "chiefExecutiveOfficer", "foundedIn"), NOT a
natural-language sentence-like proposition the way Propositionizer's
`targets` or the gpt-4o-mini relation-aware atomizer's `propositions`
are. Two options were considered for scoring severance against this:

  (A) Reuse ../severance_judge_paragraph.py's `build_paragraph_judge_prompt`
      completely unmodified, feeding it some rendering of the triples in
      place of `propositions`.
  (B) Write a fully bespoke triple-native judge prompt from scratch, with
      its own relation framing.

NEITHER extreme was used. What this file actually does is a THIRD,
explicitly-documented middle path:

  1. Each triple is rendered into a pseudo-sentence via `render_triple`
     (subject + a humanized predicate + object, e.g. the triple
     `(subject="Apple", predicate="foundedIn", object="1976")` renders as
     `"Apple founded in 1976"` -- camelCase is split on internal
     uppercase letters and lowercased; underscores become spaces). This
     is the "triple-to-text rendering step" option (A) suggested.
  2. BUT the prompt this file builds (`build_triple_judge_prompt`) is a
     NEW function, not a call into `severance_judge_paragraph
     .build_paragraph_judge_prompt`, because a bare rendering-only reuse
     would silently ask the judge to evaluate ungrammatical pseudo-prose
     without ever telling it the material it's reading was mechanically
     assembled from structured triples -- risking the judge penalizing
     normal triple terseness (no articles, no copula, camelCase-derived
     phrasing) as "garbled" in a way it would never do for genuine
     natural-language propositions, which would bias severance rates
     upward for a reason that has nothing to do with relation
     preservation. So each triple is shown BOTH as the rendered
     pseudo-sentence AND as its raw (subject, predicate, object) fields
     side by side, with an explicit up-front note telling the judge this
     is the format convention for every case it will see, not a defect
     of this particular one.
  3. What IS reused verbatim, deliberately, for comparability with the
     Propositionizer/gpt-4o-mini-atomizer numbers: the underlying judge
     QUESTION and the `_RELATION_DESCRIPTIONS` text
     (Condition/Concession/Elaboration/None), copied byte-for-byte from
     ../severance_judge_paragraph.py (itself copied byte-for-byte from
     ../../severance_detection.py) -- same "reading ONLY the atomized
     output, would a reader still correctly understand the
     satellite-governs-nucleus relationship" framing, same relation
     definitions. Only the "how the atomized output is presented" part
     changes to fit triples; the "what counts as preserved" definition
     does not, so this track's severance rate stays a like-for-like
     comparison against the other two chunkers' rates on the same
     question, not a differently-calibrated metric.

EVIDENCE_SPAN IS DELIBERATELY EXCLUDED from what the judge sees. Each
triple also carries an `evidence_span` (the original source substring
that supports it -- see nuggetindex_extractor_adapter.py). Feeding that
to the judge would let the judge "cheat" by reading the original
paragraph's own wording back through the evidence span, exactly
contrary to this project's established principle (../severance_detection
.py's `LLM_JUDGE_PROMPT_MARKER`: "Reading ONLY the atomized claims
above, not the original sentence") that the judge must decide based
SOLELY on what a downstream reader of the atomized output would
actually see. A NuggetIndex consumer reading a retrieved fact triple
sees the triple (subject, predicate, object) as the governed record --
evidence_span is provenance/citation metadata, analogous to a source URL,
not part of the fact statement itself. Including it here would make
severance artificially near-zero (the original sentence, connective
included, would always be sitting right there) and would not be
measuring the same thing the other two chunkers' severance rates
measure. This exclusion is a deliberate, load-bearing methodological
choice, not an oversight -- stated here so it's not missed.

Same `preserved: bool | None` / `reasoning: str` return contract as
every other judge function in this project family
(severance_detection.llm_judge_severance,
severance_judge_paragraph.llm_judge_paragraph_severance): `None` only on
an outright call/parse failure, never as a silent stand-in for a real
verdict.
"""

import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FACTOIDWIKI_TRACK_DIR = os.path.dirname(SCRIPT_DIR)
DISCOURSE_SEVERANCE_DIR = os.path.dirname(FACTOIDWIKI_TRACK_DIR)
SERVER_DIR = os.path.dirname(os.path.dirname(DISCOURSE_SEVERANCE_DIR))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from api_call import generate_response  # noqa: E402
from components.response_parsing import extract_json_from_response  # noqa: E402

DEFAULT_JUDGE_MODEL = None  # None -> generate_response's own default (gpt-4o-mini)

# Distinctive substring, parallel to severance_detection.LLM_JUDGE_PROMPT_MARKER
# and severance_judge_paragraph.LLM_JUDGE_PROMPT_MARKER.
LLM_JUDGE_PROMPT_MARKER = "Reading ONLY the atomized fact triples above"

# Verbatim copy (for the three shared relation types this track uses -- no
# "Exception" category here, matching ../severance_judge_paragraph.py's
# same trim) of ../severance_judge_paragraph.py's _RELATION_DESCRIPTIONS,
# itself a verbatim copy of ../../severance_detection.py's. Kept textually
# identical on purpose -- see module docstring point 3.
_RELATION_DESCRIPTIONS = {
    "Condition": (
        "a Condition relation: the nucleus is asserted to hold ONLY WHEN/IF "
        "the satellite holds -- if the satellite's truth is not knowable or "
        "is false, the nucleus's applicability here is not established."
    ),
    "Concession": (
        "a Concession relation: the nucleus holds EVEN THOUGH/DESPITE the "
        "satellite also being true -- the satellite is acknowledged but "
        "does not defeat the nucleus."
    ),
    "Elaboration": (
        "an Elaboration relation: the satellite is independently-true "
        "supporting detail, example, or restatement about the nucleus. "
        "The satellite does NOT govern, condition, or except the nucleus "
        "-- the nucleus would still be true even if the satellite were "
        "removed. For this relation type, judge whether a reader would "
        "still understand that the satellite's content is additional "
        "detail ABOUT the nucleus (as opposed to being lost, contradicted, "
        "or wrongly attached to something else) -- do NOT judge it against "
        "a governing/conditioning standard that does not apply to "
        "Elaboration."
    ),
    "None": (
        "no specific governing relation -- judge only whether the "
        "atomized fact triples still convey the same overall content as "
        "the nucleus/satellite text."
    ),
}


def _humanize_predicate(predicate):
    """camelCase / snake_case predicate -> lowercase, space-separated
    words. `"chiefExecutiveOfficer"` -> `"chief executive officer"`,
    `"foundedIn"` -> `"founded in"`, `"merged_with"` -> `"merged with"`.
    Best-effort only -- NuggetIndex's own predicate-normalization prompt
    (extractors/prompts/extraction.md) does not guarantee every predicate
    is valid camelCase, so this never raises on unexpected input.
    """
    if not predicate:
        return ""
    s = predicate.replace("_", " ")
    out = []
    for i, ch in enumerate(s):
        if ch.isupper() and i > 0 and not s[i - 1].isspace():
            out.append(" ")
        out.append(ch)
    return "".join(out).lower().strip()


def render_triple(triple):
    """(subject, predicate, object) -> a pseudo-sentence string, e.g.
    `{"subject": "Apple", "predicate": "foundedIn", "object": "1976"}`
    -> `"Apple founded in 1976"`. See module docstring point 1.
    """
    predicate_human = _humanize_predicate(triple.get("predicate", ""))
    subject = (triple.get("subject") or "").strip()
    obj = (triple.get("object") or "").strip()
    return f"{subject} {predicate_human} {obj}".strip()


def build_triple_judge_prompt(paragraph, relation, triples):
    relation_type = relation.get("relation_type", "None")
    nucleus = relation.get("nucleus")
    satellite = relation.get("satellite")
    description = _RELATION_DESCRIPTIONS.get(relation_type, _RELATION_DESCRIPTIONS["None"])

    if triples:
        lines = []
        for t in triples:
            rendered = render_triple(t)
            lines.append(
                f"- {rendered}  "
                f"[raw triple: subject={t.get('subject')!r}, "
                f"predicate={t.get('predicate')!r}, object={t.get('object')!r}]"
            )
        triples_block = "\n".join(lines)
    else:
        triples_block = "(no fact triples were extracted)"

    return f"""
Original paragraph (context ONLY -- do not base your answer on this, only
on the atomized fact triples below): "{paragraph}"

Discourse relation identified in the original paragraph: {relation_type}
Nucleus (the governed/asserted clause): {nucleus!r}
Satellite (the qualifying/supporting clause): {satellite!r}

This is specifically {description}

FORMAT NOTE: the atomized output below is a SET of (subject, predicate,
object) fact triples produced by an automated triple extractor, NOT
natural-language sentences written by a person. Each triple is shown
both as a mechanically-rendered pseudo-sentence (subject + a
lowercased, de-camelCased predicate + object -- e.g. predicate
"foundedIn" renders as "founded in") and as its raw structured fields.
Do NOT treat missing articles ("the"/"a"), missing copulas ("is"/"was"),
or terse camelCase-derived phrasing as evidence the relation is
"garbled" -- that terseness is the normal, expected shape of every
triple you will see in this task, not a defect specific to this case.
Judge ONLY whether the relationship the {relation_type} description
above requires is actually evident from the triples' CONTENT (which
entities/values are connected to which, and how), not from their prose
fluency.

Atomized fact triples (this is what a downstream reader would actually
see, with NO access to the original paragraph and NO access to the
triples' evidence spans / supporting source quotes -- only the
triples themselves):
{triples_block}

{LLM_JUDGE_PROMPT_MARKER}, not the original paragraph, would a reader
correctly understand the relationship between the satellite ({satellite!r})
and the nucleus ({nucleus!r}) DESCRIBED ABOVE for this specific relation
type? Judge Condition/Concession against whether the nucleus's governing
condition/concession is still evident. Judge Elaboration against whether
the satellite's content is still evident as detail about the nucleus (NOT
against a governing standard, since Elaboration never governs). Answer
"false" if the atomized fact triples would lead a reader to a different
understanding of the relationship than the original paragraph conveyed,
or if the relationship is absent, garbled, or split so that the
satellite's qualification no longer attaches to the nucleus's content --
whether because a triple was never extracted, or because the extracted
triples strip the qualification into an unconditional-looking assertion.

Output strict JSON with exactly these keys:
  "preserved": true or false
  "reasoning": one sentence explaining your answer

Return only valid JSON. Do not include Markdown code fences or additional
text.
"""


def llm_judge_triple_severance(paragraph, relation, triples, model=None):
    """Returns {"preserved": bool or None, "reasoning": str}. `preserved`
    is None only on an outright call/parse failure (logged in
    `reasoning`) -- see module docstring's return-contract note.
    """
    model = model or DEFAULT_JUDGE_MODEL
    prompt = build_triple_judge_prompt(paragraph, relation, triples)
    response = generate_response(prompt, model=model)
    if not response or not hasattr(response, "content"):
        return {"preserved": None, "reasoning": "LLM-judge call failed: no model response."}

    data = extract_json_from_response(response.content)
    if not data:
        return {"preserved": None, "reasoning": "LLM-judge call failed: unparseable JSON response."}

    return {
        "preserved": bool(data.get("preserved")),
        "reasoning": data.get("reasoning", ""),
    }


# ---------------------------------------------------------------------------
# ADDED post-hoc, alongside (not replacing) the full-nucleus judge above --
# for the nucleus-bundling (A1) audit, see ../audit_nucleus_bundling.py and
# ./audit_nucleus_bundling.py's module docstring.
#
# WHY THIS FUNCTION HAD TO BE WRITTEN NEW, NOT REUSED: ../../severance_
# detection.py already has a sub-clause-scoped judge
# (`llm_judge_severance_subclause` / `build_llm_judge_prompt_subclause`),
# reused unmodified by ../audit_nucleus_bundling.py (Propositionizer/
# Condition A/B) and by ../../atomicrag_track/audit_nucleus_bundling.py
# (AtomicRAG) -- both of those chunkers produce natural-language claims,
# so that function's `claims_block = "\n".join(f"- {c}" for c in
# atomized_claims)` rendering is a correct fit as-is. NuggetIndex's atomic
# unit is a (subject, predicate, object) triple, not a natural-language
# claim -- exactly the same reason `build_triple_judge_prompt` above had to
# be written new rather than reusing `severance_judge_paragraph.py`'s
# prompt (see this module's docstring, points 1-2): a bare natural-language
# claims-block rendering would silently ask the judge to read raw
# `repr(triple)`-style text with no explanation, or would require throwing
# away the raw structured fields the primary triple judge always shows
# alongside the rendering. So this is a NEW function, not a reimplementation
# of an existing one -- there is no pre-existing triple-aware sub-clause
# judge anywhere in this project to import instead.
#
# What IS reused (not re-derived): `render_triple`, `_humanize_predicate`,
# and `_RELATION_DESCRIPTIONS` from this same module (unchanged, same
# functions `llm_judge_triple_severance` above already uses), and the
# "IMPORTANT SCOPING NOTE" + evidence-requirement paragraph copied
# near-verbatim in substance from `severance_detection.build_llm_judge_
# prompt_subclause` (only the claims-block -> triples-block presentation
# changes, mirroring how `build_triple_judge_prompt` above relates to
# `severance_judge_paragraph.build_paragraph_judge_prompt`). The judge
# QUESTION and relation descriptions stay byte-for-byte identical to the
# full-nucleus triple judge above, for the same comparability reason
# documented in this module's docstring point 3.

LLM_JUDGE_SUBCLAUSE_PROMPT_MARKER = (
    "Reading ONLY the atomized fact triples above, and judging ONLY "
    "against the specific sub-clause"
)


def build_triple_judge_prompt_subclause(paragraph, relation, triples, governed_subclause):
    """Sub-clause-scoped variant of `build_triple_judge_prompt` (A1 audit
    only). `governed_subclause` is the specific coordinated sub-clause of
    the bundled elicited nucleus that the satellite originally modified in
    the source paragraph (determined by the A1 audit's adjacency analysis,
    not by this function -- see ../../audit_severance.py's
    `assign_governed_subclause`).
    """
    relation_type = relation.get("relation_type", "None")
    nucleus = relation.get("nucleus")
    satellite = relation.get("satellite")
    description = _RELATION_DESCRIPTIONS.get(relation_type, _RELATION_DESCRIPTIONS["None"])

    if triples:
        lines = []
        for t in triples:
            rendered = render_triple(t)
            lines.append(
                f"- {rendered}  "
                f"[raw triple: subject={t.get('subject')!r}, "
                f"predicate={t.get('predicate')!r}, object={t.get('object')!r}]"
            )
        triples_block = "\n".join(lines)
    else:
        triples_block = "(no fact triples were extracted)"

    return f"""
Original paragraph (context ONLY -- do not base your answer on this, only
on the atomized fact triples below): "{paragraph}"

Discourse relation identified in the original paragraph: {relation_type}
Full elicited nucleus: {nucleus!r}
Satellite (the qualifying/supporting clause): {satellite!r}

This is specifically {description}

IMPORTANT SCOPING NOTE: the full elicited nucleus above BUNDLES two (or
more) coordinated, independently-governed assertions. In the original
paragraph, the satellite {satellite!r} modified ONLY this specific
sub-clause of the nucleus:

  Governed sub-clause: {governed_subclause!r}

The other coordinated assertion(s) in the nucleus were never governed by
the satellite. Fact triples that connect the satellite's qualification to
the governed sub-clause alone -- narrowing scope to the sub-clause it
always modified -- are CORRECT atomization, not a severed relation. Do
NOT answer "false" merely because no triple links the satellite to the
other, never-governed assertion(s).

This scoping note does NOT relax the basic evidence requirement: your
answer must be based ONLY on what is actually expressed in the triples
below. The satellite's qualifying content must still SURVIVE in some
triple's content, attached to (or clearly qualifying) the governed
sub-clause's content. If the satellite's qualification is missing from
every triple, or appears only as a free-standing, unconditional-looking
fact with no qualifying link to the governed sub-clause's content, the
relation is severed and the answer is "false" -- no matter how obvious
the relationship is in the original paragraph.

FORMAT NOTE: the atomized output below is a SET of (subject, predicate,
object) fact triples produced by an automated triple extractor, NOT
natural-language sentences written by a person. Each triple is shown both
as a mechanically-rendered pseudo-sentence and as its raw structured
fields. Do NOT treat missing articles, missing copulas, or terse
camelCase-derived phrasing as evidence the relation is "garbled" -- that
terseness is the normal, expected shape of every triple you will see in
this task.

Atomized fact triples (this is what a downstream reader would actually
see, with NO access to the original paragraph and NO access to the
triples' evidence spans / supporting source quotes -- only the triples
themselves):
{triples_block}

{LLM_JUDGE_SUBCLAUSE_PROMPT_MARKER} ({governed_subclause!r}), would a
reader correctly understand that the satellite ({satellite!r}) governs
THAT sub-clause, for this specific relation type? First check whether any
triple still expresses the satellite's qualification at all -- if none
does, answer "false". Then answer "true" only if the satellite's
relationship to the governed sub-clause is evident in the triples as
written (whether expressed against the sub-clause alone or against
content that includes it). Answer "false" if the relationship between the
satellite and the governed sub-clause itself is absent, garbled, or would
lead a reader to a different understanding than the original paragraph
conveyed.

Output strict JSON with exactly these keys:
  "preserved": true or false
  "reasoning": one sentence explaining your answer

Return only valid JSON. Do not include Markdown code fences or additional
text.
"""


def llm_judge_triple_severance_subclause(paragraph, relation, triples,
                                          governed_subclause, model=None):
    """Sub-clause-scoped variant of `llm_judge_triple_severance` (A1 audit
    only). Same return contract: {"preserved": bool or None, "reasoning":
    str}; `preserved` is None only on an outright call/parse failure.
    """
    model = model or DEFAULT_JUDGE_MODEL
    prompt = build_triple_judge_prompt_subclause(paragraph, relation, triples, governed_subclause)
    response = generate_response(prompt, model=model)
    if not response or not hasattr(response, "content"):
        return {"preserved": None, "reasoning": "LLM-judge call failed: no model response."}

    data = extract_json_from_response(response.content)
    if not data:
        return {"preserved": None, "reasoning": "LLM-judge call failed: unparseable JSON response."}

    return {
        "preserved": bool(data.get("preserved")),
        "reasoning": data.get("reasoning", ""),
    }


# Clearly-labeled aliases, parity with ../../severance_detection.py's
# judge_prompt_full_nucleus / judge_prompt_subclause aliases.
judge_prompt_full_nucleus = build_triple_judge_prompt
judge_prompt_subclause = build_triple_judge_prompt_subclause


# ---------------------------------------------------------------------------
# Elaboration correction (v2): content-recoverability judge, triple-aware.
#
# Triple-native port of ../severance_detection.py's
# `llm_judge_severance_elaboration_v2` / `build_llm_judge_prompt_elaboration_v2`
# -- see that module's block comment for the full root-cause writeup. A
# direct reading of a stratified sample of 20 of the 77 NuggetIndex cases
# the original triple judge (`llm_judge_triple_severance`, above) scored
# severed=false for Elaboration found roughly half were content genuinely
# present (just split/merged/reworded across triples -- same over-strict
# pattern as the other three chunkers), but a real, elevated minority were
# genuine content loss OR active predicate-level misattribution specific
# to how NuggetIndex's triple extraction degrades free text -- e.g.
# pool_index 2997's diagnosis year mechanically mislabeled with the
# predicate "date of birth" ("Hayworth date of birth 1980" for a sentence
# that says she was DIAGNOSED with Alzheimer's in 1980, not born then), and
# pool_index 3523's later-work publication years misattributed as the
# "founded in" date of the EARLIER work that inspired them (asserting one
# piece was "founded" in four different years). NuggetIndex's genuine
# lossiness is therefore expected to leave this chunker with a materially
# higher corrected severed rate than the other three, not collapse it to
# near zero -- this is the reason a triple-aware variant of this
# correction had to be written at all rather than just reusing the
# paragraph-level version's numbers.
#
# WHY WRITTEN NEW, NOT REUSED: same reasoning as
# `build_triple_judge_prompt_subclause` above relative to
# severance_detection.build_llm_judge_prompt_subclause -- a bare
# natural-language claims-block rendering would silently ask the judge to
# read raw structured fields with no explanation of the triple-extraction
# format convention, or would require discarding the raw
# (subject, predicate, object) fields the primary triple judge always
# shows alongside the rendering (needed here specifically because
# misattribution -- check 3(b) below -- is often only visible in the raw
# fields, e.g. seeing predicate="dateOfBirth" next to a value that is
# obviously a diagnosis year once you know the source paragraph's shape).
# What IS reused, unchanged: `render_triple`, `_humanize_predicate`, the
# FORMAT NOTE paragraph (verbatim, so the judge is told not to penalize
# normal triple terseness the same way here as in the full-nucleus triple
# judge), and the nucleus-recoverable-gate / satellite-content-recoverable
# / genuine-absence / active-misattribution structure from
# severance_detection.py's v2 prompt.
#
# Elaboration-only: Condition/Concession/None's _RELATION_DESCRIPTIONS,
# render_triple, build_triple_judge_prompt, llm_judge_triple_severance,
# and the sub-clause functions above are completely untouched.
LLM_JUDGE_ELABORATION_V2_PROMPT_MARKER = (
    "Reading ONLY the atomized fact triples above, taken together as a whole set"
)


def build_triple_judge_prompt_elaboration_v2(paragraph, relation, triples):
    """Corrected Elaboration-only judge prompt, triple-adapted. Must only
    be used when relation["relation_type"] == "Elaboration".
    """
    nucleus = relation.get("nucleus")
    satellite = relation.get("satellite")

    if triples:
        lines = []
        for t in triples:
            rendered = render_triple(t)
            lines.append(
                f"- {rendered}  "
                f"[raw triple: subject={t.get('subject')!r}, "
                f"predicate={t.get('predicate')!r}, object={t.get('object')!r}]"
            )
        triples_block = "\n".join(lines)
    else:
        triples_block = "(no fact triples were extracted)"

    return f"""
Original paragraph (context ONLY -- do not base your answer on this, only
on the atomized fact triples below): "{paragraph}"

Discourse relation identified in the original paragraph: Elaboration
Nucleus (the general situation being elaborated): {nucleus!r}
Satellite (the additional detail about that situation): {satellite!r}

This is an Elaboration relation: per RST's own definition (Carlson &
Marcu 2001, Elaboration-Additional / Elaboration-General-Specific), the
satellite simply gives additional information, detail, or specific
content about the situation presented in the nucleus. The satellite does
NOT govern, condition, or except the nucleus -- the nucleus would still
be true even if the satellite were removed, and RST does NOT require the
satellite to stay lexically or structurally attached to the nucleus (no
connective, shared triple, or explicit transition word is required by the
relation itself). The only thing that matters is whether the CONTENT is
there, is topically about the nucleus's subject, and is not
misattributed.

FORMAT NOTE: the atomized output below is a SET of (subject, predicate,
object) fact triples produced by an automated triple extractor, NOT
natural-language sentences written by a person. Each triple is shown
both as a mechanically-rendered pseudo-sentence (subject + a
lowercased, de-camelCased predicate + object -- e.g. predicate
"foundedIn" renders as "founded in") and as its raw structured fields.
Do NOT treat missing articles ("the"/"a"), missing copulas ("is"/"was"),
or terse camelCase-derived phrasing as evidence content is "garbled" or
lost -- that terseness is the normal, expected shape of every triple you
will see in this task, not a defect specific to this case.

Atomized fact triples (this is what a downstream reader would actually
see, with NO access to the original paragraph and NO access to the
triples' evidence spans / supporting source quotes -- judge the triples
TOGETHER, as the full set a reader would have, not one at a time in
isolation):
{triples_block}

{LLM_JUDGE_ELABORATION_V2_PROMPT_MARKER}, not the original paragraph,
decide whether the relationship is preserved. Base your answer ONLY on
what is literally stated -- verbatim, closely paraphrased, or clearly
implied by the rendered pseudo-sentence -- in the atomized fact triples
below. Do not use outside/world knowledge or plausible inference to fill
in content the atomized triples do not actually convey; but also do not
demand every last word or secondary nuance of the original phrasing
survive, and do not treat normal triple terseness (no articles, no
copula, camelCase-derived phrasing) as evidence of loss -- minor loss of
secondary wording or emphasis is fine as long as the core content is
genuinely there.

Step 1 (nucleus gate): is the nucleus's situation ({nucleus!r}) stated
anywhere in the atomized triples -- in one triple, or built up from a
combination of triples, in any wording? If it is NOT stated anywhere at
all (including the case where zero triples were extracted), set
"nucleus_recoverable": false and answer "preserved": false immediately --
there is no situation left for the satellite to be detail about, no
matter how well the satellite's own content survived elsewhere.

Step 2 (satellite content check): if the nucleus IS recoverable, set
"nucleus_recoverable": true, then check whether the satellite's SPECIFIC
content ({satellite!r}) is ALSO stated somewhere in the atomized triples
-- in the same triple as the nucleus (perfectly normal if facts were
merged into one triple) or a different one, split apart or merged,
phrased identically or paraphrased. No connective is required. "Specific"
means: if the satellite's original text names a number, date, named
entity, comparison, or reason/cause, that core specific point should be
recoverable somewhere in the atomized triples -- a triple that only
gestures at the general topic while dropping the actual specific point
(replacing a concrete number/name/reason with nothing, with something so
generic the point is lost, or with an unrelated specific from elsewhere
in the source) does not satisfy this.

Step 3 (misattribution check -- run this even when steps 1-2 both look
satisfied): does any atomized triple actively CONTRADICT or MISATTRIBUTE
the nucleus's or satellite's content? Check the RAW subject/predicate/
object fields specifically for this, not just the rendered
pseudo-sentence. Concrete failure patterns seen in this extractor's real
output: a date or value attached to the wrong predicate (e.g. a diagnosis
year rendered as predicate="dateOfBirth"; an inspired-later-work's
publication year rendered as the EARLIER work's "founded in"/"published"
value); a subject/object relationship reversed from what the text
actually says (X did something TO Y rendered as Y did it to X); or a
value that is internally impossible (e.g. one entity with several
different "founding" dates -- itself a red flag worth scanning the whole
triple set for). If yes, answer "preserved": false -- an actively wrong
or misattributed triple is worse than a missing one, even if some other
triple elsewhere also carries correct content.

Answer "preserved": true only if step 1 and step 2 both succeed AND step
3 finds no contradiction/misattribution.

Do NOT answer "false" merely because: the satellite's content ended up in
a separate triple from the nucleus with no connective between them; the
triples split or merged content differently than you might expect; the
extracted wording paraphrases rather than quotes the original; normal
triple terseness makes the phrasing blunt; or some minor secondary detail
(not the core specific point) is missing. None of those are severance for
Elaboration.

Output strict JSON with exactly these keys:
  "preserved": true or false
  "nucleus_recoverable": true or false
  "reasoning": one or two sentences explaining your answer, quoting or
    pointing to the specific atomized triple(s) that drove the verdict
    and naming which step (1/2/3) was decisive

Return only valid JSON. Do not include Markdown code fences or additional
text.
"""


def llm_judge_triple_severance_elaboration_v2(paragraph, relation, triples, model=None):
    """Corrected Elaboration-only severance judge, triple-adapted. Returns
    {"preserved": bool or None, "nucleus_recoverable": bool or None,
    "reasoning": str}. `preserved` is None only on an outright call/parse
    failure -- same contract as llm_judge_triple_severance. `reasoning`
    is logged verbatim for every call so disagreements can be audited
    later.

    See ../severance_detection.py's llm_judge_severance_elaboration_v2
    docstring for the "PROMPT ITERATION NOTE" documenting why an earlier
    separate-evidence-quoting version of this prompt was tried and
    discarded (it over-corrected gpt-4o-mini into fabricating
    deficiencies on straightforward merged cases) -- this triple-level
    prompt is kept in lockstep with that one's final design.

    Callers MUST route Elaboration relations to this function and every
    other relation type to `llm_judge_triple_severance` (the original) --
    this function does not itself branch on relation_type.
    """
    if relation.get("relation_type") != "Elaboration":
        raise ValueError(
            "FATAL: llm_judge_triple_severance_elaboration_v2 is "
            f"Elaboration-only; got relation_type={relation.get('relation_type')!r}. "
            "Use llm_judge_triple_severance (the original judge) for "
            "Condition/Concession/None."
        )
    model = model or DEFAULT_JUDGE_MODEL
    prompt = build_triple_judge_prompt_elaboration_v2(paragraph, relation, triples)
    response = generate_response(prompt, model=model)
    if not response or not hasattr(response, "content"):
        return {
            "preserved": None,
            "nucleus_recoverable": None,
            "reasoning": "LLM-judge call failed: no model response.",
        }

    data = extract_json_from_response(response.content)
    if not data:
        return {
            "preserved": None,
            "nucleus_recoverable": None,
            "reasoning": "LLM-judge call failed: unparseable JSON response.",
        }

    return {
        "preserved": bool(data.get("preserved")),
        "nucleus_recoverable": data.get("nucleus_recoverable"),
        "reasoning": data.get("reasoning", ""),
    }
