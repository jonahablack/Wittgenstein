"""NuggetIndex Experiment 3, Arm 6: flagged deferral.

Runs server/components/risk_triage.py's `flag_claim` -- imported
UNMODIFIED, the exact same function ../../run_experiment_3.py's own arm 6
uses for the other two chunkers -- against NuggetIndex's (subject,
predicate, object) triples.

WHY render_triple IS USED HERE, AND WHY THIS IS THE ONE, NARROW,
EXPLICITLY-AUTHORIZED EXCEPTION TO THIS TASK'S "no conversion /
naturalization of triples" RULE (stated here, not glossed over, per the
task brief's explicit instruction):

`flag_claim(english, formal, formal_mode="english", segment_text=None)`
structurally requires a TEXT STRING for its `english`/`formal`
arguments -- every one of its rule-based detectors
(detect_negation_scope, detect_condition_satellite, detect_modal_mismatch,
...) does word-boundary regex matching and, for the satellite detectors,
a spaCy subject/finite-verb parse over that string. A bare (subject,
predicate, object) tuple has no surface form for any of that to run
against; flag_claim cannot be called on one directly.

This module does NOT write a new natural-language generation step to
satisfy that requirement -- doing so would be exactly the "naturalize
the triples into prose, then repair/analyze the prose" confound this
task's scope explicitly forbids. Instead it reuses `render_triple` from
../triple_severance_judge.py: a FIXED, DETERMINISTIC, PRE-EXISTING string
template (split a camelCase/snake_case predicate into words, lowercase
it, `f"{subject} {predicate_human} {object}"` -- no LLM call anywhere in
it, no interpretation, no generation) that is already built, already
validated, and already used elsewhere in this project as the primary
NuggetIndex severance judge's pseudo-sentence rendering (see
../triple_severance_judge.py's module docstring, point 1, and its
`render_triple` docstring). It is reused here ONLY because `flag_claim`
structurally requires a text string as input. This is not new
methodology and not a generative rewrite -- it is the reuse of an
existing deterministic template to satisfy one downstream function's
type signature, and it is the ONLY place in this track's Experiment 3
code where a triple is converted to text.

render_triple's output is passed as BOTH the `english` (claim text) and
`formal` arguments flag_claim's signature requires, mirroring exactly how
../../run_experiment_3.py's own arm 6 calls `flag_claim(prop, prop,
...)` for FactoidWiki -- passing the same string as both claim and
"formal" because this experiment has no separate formalization step
either (see that module's `flags_for_case` docstring: "No formalization
exists in this experiment, so formal=proposition (self-identical), which
makes detect_modal_mismatch a structural no-op"). The identical reasoning
applies here, with render_triple(triple) standing in for
`prop`/`proposition`. `segment_text` is the case's source PARAGRAPH
(`case["content"]`), the same role FactoidWiki's arm 6 gives it.

ONE DELIBERATE DEVIATION from ../../run_experiment_3.py's flags_for_case,
NOT a mirroring oversight: that function classifies segment-level flags
via `t in ("segment_nested_conditional", "segment_negation_scope")`.
`segment_nested_conditional` is a RETIRED flag type in the current
server/components/risk_triage.py (see that file's own comments: it was
replaced by `segment_condition_satellite` / `segment_concession_satellite`
when the satellite detectors were added) -- no detector in the current
file ever produces it, so FactoidWiki's own arm 6 silently
misclassifies `segment_condition_satellite` / `segment_concession_satellite`
flags as claim-level instead of segment-level. Since risk_triage.py is
imported UNMODIFIED and read directly here (not assumed from memory),
this module uses the CURRENT, correct segment-level type set instead of
reproducing that stale name -- reproducing a known-stale name here would
misclassify this track's own segment_flag statistics for no reason. This
is the only place this module's logic differs from
../../run_experiment_3.py's; everything else mirrors it exactly
(renamed proposition->triple).
"""

import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
NUGGETINDEX_TRACK_DIR = os.path.dirname(SCRIPT_DIR)
FACTOIDWIKI_TRACK_DIR = os.path.dirname(NUGGETINDEX_TRACK_DIR)
DISCOURSE_SEVERANCE_DIR = os.path.dirname(FACTOIDWIKI_TRACK_DIR)
SCRIPTS_DIR = os.path.dirname(DISCOURSE_SEVERANCE_DIR)
SERVER_DIR = os.path.dirname(SCRIPTS_DIR)

for _p in (NUGGETINDEX_TRACK_DIR, SERVER_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from components.risk_triage import flag_claim  # noqa: E402  (UNMODIFIED import, read-only)
from triple_severance_judge import render_triple  # noqa: E402  (existing, deterministic; see module docstring)

# Current (non-retired) segment-level flag types produced by
# server/components/risk_triage.py -- see module docstring's "ONE
# DELIBERATE DEVIATION" note for why this is NOT
# ("segment_nested_conditional", "segment_negation_scope").
_SEGMENT_FLAG_TYPES = ("segment_condition_satellite", "segment_concession_satellite",
                       "segment_negation_scope")


def flags_for_case(case):
    """Arm 6 for one eval-set case: run flag_claim against every triple
    in case["nuggetindex_triples"], rendered via render_triple. Mirrors
    ../../run_experiment_3.py's flags_for_case (renamed
    proposition->triple; see module docstring for the one deliberate
    deviation).
    """
    per_triple = []
    for triple in case["nuggetindex_triples"]:
        rendered = render_triple(triple)
        flags = flag_claim(rendered, rendered, formal_mode="english", segment_text=case["content"])
        per_triple.append({"triple": triple, "rendered": rendered, "flags": flags})

    all_types = sorted({f["type"] for pt in per_triple for f in pt["flags"]})
    segment_types = [t for t in all_types if t in _SEGMENT_FLAG_TYPES]
    claim_level_types = [t for t in all_types if t not in segment_types]

    return {
        "per_triple_flags": per_triple,
        "n_triples_checked": len(case["nuggetindex_triples"]),
        "flag_types_fired": all_types,
        "segment_flag_fired": bool(segment_types),
        "segment_flag_types": segment_types,
        "claim_level_flag_fired": bool(claim_level_types),
        "claim_level_flag_types": claim_level_types,
        "any_flag_fired": bool(all_types),
    }
