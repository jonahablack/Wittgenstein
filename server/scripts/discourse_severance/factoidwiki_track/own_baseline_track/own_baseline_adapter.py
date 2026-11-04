"""Adapter: run THIS PROJECT'S OWN minimal prompted baseline splitter
(server/scripts/discourse_severance/atomization_conditions.py's
`run_condition_a` / `run_condition_b`, which themselves call
server/components/response_parsing.py's `process_single_segment` -- the
shipped production claim-extraction logic, unmodified) over FactoidWiki
paragraphs, so its output can be scored with this track's existing
paragraph-level severance-detection infrastructure alongside the
Propositionizer, AtomicRAG, and NuggetIndex.

FRAMING (established this session, must be preserved everywhere this
baseline is described): this is "a minimal prompted baseline, included as
one additional tested system for the generality claim, not itself a
claimed contribution." It is one of four data points in a controlled
comparison -- never call it "the [SYSTEM NAME] pipeline" or otherwise imply
it is this project's own showcased contribution.
FRAMING_STATEMENT (verbatim; reuse this string in reports/docstrings that
cite own_baseline_track output) is defined below.

WHAT RUNS REAL, UNMODIFIED (imported directly from
../../atomization_conditions.py, NOT reimplemented -- this is a deliberate,
explicit instruction for this integration specifically, and it is a
departure from ../env_utils.py's/../nuggetindex_track/env_utils.py's own
stated "this track's scripts should not import from its siblings outside
factoidwiki_track/" convention. That convention exists so a track stays
"self-contained and safely deletable/movable as a unit" when there's a
choice; here there is deliberately NO choice, because the entire point of
this track is to measure atomization_conditions.py's `run_condition_a` /
`run_condition_b` AS ALREADY WRITTEN AND ALREADY USED ELSEWHERE IN THIS
PROJECT (see ../../run_experiments.py's Experiment 1, which calls these
same two functions on CFR sentences) -- reimplementing a paragraph-flavored
copy of them, the way ../condition_b_atomizer.py did for the
Propositionizer track's own from-scratch Condition B, would stop this from
being "our own baseline, run unmodified" and turn it into a fifth,
never-before-tested variant. So: a real cross-boundary import, done once,
here, and documented, exactly as ../atomicrag_track/run_atomicrag_experiment
.py already did for reusing ../severance_judge_paragraph.py's judge (see
that script's "REUSE, NOT REIMPLEMENTATION" docstring section) -- same
justification, opposite direction (this file reaches UP into
discourse_severance/ instead of sideways into factoidwiki_track/):
  - `atomization_conditions.run_condition_a(sentence)` -- calls
    `process_single_segment((0, sentence))` directly, today's production
    default, no code changed.
  - `atomization_conditions.run_condition_b(sentence, relation, model=None)`
    -- a NEW prompt (defined in atomization_conditions.py only) that gives
    the model the text plus its already-elicited relation type/nucleus/
    satellite/connective and instructs it to atomize while explicitly
    preserving that relation. This is what makes Condition B available for
    this chunker at all, unlike AtomicRAG/NuggetIndex (see those tracks'
    own adapters for why no relation-hint input slot exists in either
    external system's prompts).

INPUT-GRANULARITY DECISION (read this before trusting any number this
track produces -- the task that created this track required this decision
be made explicitly, not silently assumed):

`process_single_segment`'s prompt (response_parsing.py's
`_build_claim_extraction_prompt`) was built and tested on CFR's
SINGLE-SENTENCE inputs. It says, verbatim, "This segment is exactly one
sentence" and instructs pronoun resolution "Where THIS SENTENCE itself
provides the antecedent." FactoidWiki's governing-relation sample (this
track's own `content` field, read from
../logs/task7_experiment_govern_log.jsonl /
task7_experiment_elaboration_log.jsonl) is drawn from Wikipedia PARAGRAPHS
-- typically 3-6 sentences, not one. `atomization_conditions.py`'s Condition
B prompt makes the identical single-sentence assumption ("You are
decomposing a single sentence of source text").

Two options were on the table:
  (a) Run `run_condition_a`/`run_condition_b` on the paragraph AS-IS,
      passing the whole multi-sentence `content` string as the `sentence`
      argument, unmodified -- i.e. exactly what a real deployment of this
      project's shipped baseline would do if pointed at Wikipedia
      paragraphs without adapting it first.
  (b) Reimplement a paragraph-flavored prompt, the way
      ../condition_b_atomizer.py did for the Propositionizer track's own
      Condition B (renaming "sentence" to "paragraph" throughout, adding
      cross-sentence pronoun-resolution guidance, etc).

**Decision: (a).** Rationale:
  1. The task instruction for this integration is explicit and specific:
     read atomization_conditions.py and "call it the same way it's invoked
     elsewhere in this project... not a reinvented variant." Option (b)
     would BE a reinvented variant -- a fifth atomizer, never validated on
     CFR, competing for credit as "our baseline" without ever having been
     "our baseline" in production. Option (a) is the only choice under
     which this track's numbers describe the actual shipped function.
  2. This project's baseline is framed as "a minimal prompted baseline...
     not itself a claimed contribution" (see FRAMING_STATEMENT). Part of
     what makes it informative for a generality claim is precisely
     whether/how it degrades outside the input shape it was designed and
     tuned for -- that is a real, reportable finding, not a confound to be
     engineered away by silently upgrading the prompt for this one
     dataset.
  3. Empirically (see run_own_baseline_experiment.py's pilot output and
     this module's own smoke test, both hand-inspected before the full
     run): the model does not collapse or refuse on multi-sentence input
     despite the prompt's false "this segment is exactly one sentence"
     framing -- it treats the whole paragraph as one decomposition unit
     and produces sane, verbatim-leaning claims. What it does NOT do
     (predictably, per the prompt's own stated criterion 2) is resolve
     pronouns whose antecedent sits in text outside the paragraph (e.g. a
     bare "he"/"his" when the referent was only named in the FactoidWiki
     record's `title`, which is never passed in here) -- that limitation
     is a consequence of the input-granularity decision above and is
     surfaced in the pilot report, not hidden.

This decision applies identically to Condition A and Condition B (both
share the single-sentence assumption; both are run on the bare `content`
paragraph string, matching the same "bare content, no title/section
metadata" input-shape choice ../condition_b_atomizer.py made for its own
Condition B, for the same within-track-consistency reason given there).

WHAT IS NOT EXPOSED BY THE UNDERLYING FUNCTIONS, AND WHY THIS ADAPTER DOES
NOT PATCH IT IN: `run_condition_a` returns `[]` on BOTH a genuine
zero-claim result AND an outright call/parse failure (process_single_segment
prints a warning and returns `_empty_result` in the failure case, which
`run_condition_a` then reduces to the same empty list) -- there is no
distinguishing signal in the return value. `run_condition_b` behaves
identically (silently returns `[]` on a failed/unparseable call, no error
flag), unlike ../condition_b_atomizer.py's own from-scratch Condition B
(which DOES return an `_error` string) -- but that richer error signal is
exactly the kind of improvement that would make this "a reinvented variant"
rather than "the same function called the same way." This adapter reports
only a mechanical `n_*_empty` count (paragraphs where the returned claim
list is empty) as a diagnostic, without claiming to know whether each empty
result was a genuine zero-claim decomposition or a swallowed failure --
that ambiguity is an honest property of running this function unmodified,
not something to paper over here.
"""

import os
import sys

TRACK_DIR = os.path.dirname(os.path.abspath(__file__))
FACTOIDWIKI_TRACK_DIR = os.path.dirname(TRACK_DIR)
DISCOURSE_SEVERANCE_DIR = os.path.dirname(FACTOIDWIKI_TRACK_DIR)
if DISCOURSE_SEVERANCE_DIR not in sys.path:
    sys.path.insert(0, DISCOURSE_SEVERANCE_DIR)

import atomization_conditions as ac  # noqa: E402  (deliberate cross-boundary import, see module docstring)

FRAMING_STATEMENT = (
    "A minimal prompted baseline, included as one additional tested "
    "system for the generality claim, not itself a claimed contribution."
)

DEFAULT_CONDITION_B_MODEL = None  # None -> atomization_conditions.run_condition_b's own default (generate_response's gpt-4o-mini)


def run_condition_a(paragraph):
    """Condition A: today's production propositional-extraction path
    (atomization_conditions.run_condition_a -> process_single_segment),
    called on the bare paragraph `content` string -- see INPUT-GRANULARITY
    DECISION above. Never raises: returns a possibly-empty list of claim
    strings (see module docstring's note on the genuine-zero-vs-failure
    ambiguity this inherits from the underlying function).
    """
    return ac.run_condition_a(paragraph)


def run_condition_b(paragraph, relation, model=None):
    """Condition B: relation-aware atomization
    (atomization_conditions.run_condition_b), called on the bare paragraph
    `content` string plus the already-elicited relation dict (relation_type/
    nucleus/satellite/connective -- same keys ../run_experiment_1_2.py's
    own records already carry). Never raises: returns a possibly-empty
    list of claim strings.
    """
    model = model or DEFAULT_CONDITION_B_MODEL
    return ac.run_condition_b(paragraph, relation, model=model)
