"""Task 8 (Experiment 3), arm 4: Contextual Retrieval context injection,
adapted to single-proposition discourse-relation recovery.

ATTRIBUTION: the technique is Anthropic's published "Contextual
Retrieval" method (Anthropic, "Introducing Contextual Retrieval", 2024) --
prepend a short, LLM-generated situating sentence to a chunk before it is
used downstream, so the chunk carries some of the context it lost when it
was separated from its source document. This module reuses that
technique's PROMPT FRAMING verbatim in spirit (the task brief's own
quoted instruction: "generate a short, succinct context to situate this
proposition within its source paragraph"), retargeted from Anthropic's
original chunk/document retrieval framing to this track's
proposition/paragraph vocabulary, and applied here to test whether it
recovers a SEVERED DISCOURSE RELATION rather than improving retrieval
recall (Anthropic's original purpose). This is NOT a claim that
Contextual Retrieval was designed or published for discourse-relation
recovery -- it is being adapted here as an off-the-shelf, general-purpose
repair strategy, exactly as arm 2 (Disco-RAG) and arm 3 (custom fallback)
are.

WHY ONE PROPOSITION, NOT ALL OF THEM (a design decision, documented, not
hidden): Chen et al.'s Propositionizer atomizes one paragraph into MANY
propositions (9.06 on average per README.md's Task 7 structural
comparison) -- Contextual Retrieval, applied faithfully to every single
one of them per case, would require ~9x the generation calls of every
other arm in this experiment for no proportionate benefit: the severance
verdict is about whether the relation survives ANYWHERE in the atomized
output, and the specific locus of the failure is always the proposition
whose content corresponds to the NUCLEUS (the governed clause) -- that is
the one proposition that, read alone, now asserts something
unconditionally/unexceptionally that the source paragraph did not assert
unconditionally. `select_target_proposition` below deterministically
identifies that proposition (by token overlap against the elicited
`nucleus` text -- Condition A frequently paraphrases rather than copying
verbatim, so exact substring matching would miss real matches; overlap is
a robust, fully auditable, zero-LLM-cost proxy) and Contextual Retrieval's
context sentence is generated for, and prepended to, THAT ONE proposition
only. This is what "operates at the single-proposition level, matching
the input shape here" means in the task brief: the repair granularity is
one proposition, not the whole paragraph (contrast arm 5, which abandons
the split entirely) and not the whole 9-proposition set (which would not
be testing single-proposition context injection at all, just re-deriving
something closer to arm 5 nine times over).

THE "CHECK" the task brief asks for ("check whether the generated context
states the missing relation") is the same severance-judge call every
other arm is scored with (severance_judge_paragraph.llm_judge_paragraph_severance),
run on the FULL proposition list with the target proposition's
context-prepended version substituted in and every other proposition
left untouched -- exactly what a downstream reader would actually see.
No separate ad hoc check is introduced; scoring stays commensurable with
arms 2/3/5, per the task brief's instruction to keep Experiment 3 scoring
consistent across arms.
"""

import os
import re
import sys

TRACK_DIR = os.path.dirname(os.path.abspath(__file__))
DISCOURSE_SEVERANCE_DIR = os.path.dirname(TRACK_DIR)
SERVER_DIR = os.path.dirname(os.path.dirname(DISCOURSE_SEVERANCE_DIR))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)
if TRACK_DIR not in sys.path:
    sys.path.insert(0, TRACK_DIR)

from api_call import generate_response  # noqa: E402
from candidate_prefilter import normalize_text  # noqa: E402  (intra-track import, allowed)

DEFAULT_CONTEXTUAL_MODEL = "gpt-4o-mini"

CONTEXTUAL_RETRIEVAL_STATEMENT = (
    "Contextual Retrieval context injection (arm 4) adapts Anthropic's "
    "published technique (\"Introducing Contextual Retrieval\", 2024): an "
    "LLM generates a short, succinct context sentence situating one "
    "proposition within its source paragraph, prepended to that "
    "proposition. Applied here to test discourse-relation recovery, not "
    "retrieval recall (Anthropic's original purpose)."
)

# Distinctive substring, mirrors the marker convention used by every other
# prompt-bearing module in this track/experiment (e.g.
# ../exp3_recovery_comparison/custom_fallback.CUSTOM_FALLBACK_PROMPT_MARKER).
CONTEXTUAL_RETRIEVAL_PROMPT_MARKER = "situate this proposition within its source paragraph"

_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text):
    return set(_WORD_RE.findall(normalize_text(text)))


def select_target_proposition(nucleus, propositions):
    """Deterministic, zero-LLM-cost selection of which Condition-A
    proposition Contextual Retrieval's context sentence will be prepended
    to -- see module docstring for why one proposition, and why token
    overlap rather than substring matching. Ties broken by earliest
    position in `propositions` (stable, no randomness). Falls back to
    index 0 if `propositions` is empty or the nucleus has no tokens at all
    (should not happen given relation_classifier.py's schema, but this is
    a fail-safe default position, never a raised error, since a downstream
    judge call can still meaningfully score an empty/degenerate case).

    Returns (target_index, overlap_score) where overlap_score is the
    Jaccard similarity (0.0-1.0) between the nucleus's normalized word set
    and the chosen proposition's -- logged per case so the selection is
    auditable, not just asserted.
    """
    if not propositions:
        return None, 0.0
    nucleus_tokens = _tokenize(nucleus)
    if not nucleus_tokens:
        return 0, 0.0
    best_idx, best_score = 0, -1.0
    for i, prop in enumerate(propositions):
        prop_tokens = _tokenize(prop)
        if prop_tokens:
            score = len(nucleus_tokens & prop_tokens) / len(nucleus_tokens | prop_tokens)
        else:
            score = 0.0
        if score > best_score:
            best_idx, best_score = i, score
    return best_idx, best_score


def build_contextual_retrieval_prompt(paragraph, proposition):
    """Anthropic's published Contextual Retrieval prompt framing (document/
    chunk XML-style scaffold, plain-text-only answer instruction),
    retargeted to paragraph/proposition vocabulary. Per the task brief's
    own quoted instruction, this asks the model to
    "{CONTEXTUAL_RETRIEVAL_PROMPT_MARKER}" -- note the answer is PLAIN
    TEXT, not JSON, matching Anthropic's own published prompt (which asks
    for the succinct context and nothing else, no structured wrapper).
    """
    return f"""<paragraph>
{paragraph}
</paragraph>
Here is the proposition we want to situate within the whole paragraph
<proposition>
{proposition}
</proposition>
Please generate a short, succinct context to {CONTEXTUAL_RETRIEVAL_PROMPT_MARKER}. Answer only with the succinct context and nothing else."""


def run_contextual_retrieval(paragraph, relation, propositions, model=None):
    """Full arm-4 pipeline for one case:
      1. select_target_proposition (deterministic, zero cost).
      2. one LLM call: generate the situating context for that proposition.
      3. prepend the generated context to the target proposition; every
         other proposition is left untouched.

    Returns a dict: target_index, target_proposition, overlap_score,
    generated_context, contextualized_propositions (the full list, target
    replaced -- this is the "arm output" a downstream reader would see,
    and what gets fed to the severance judge), and error (None on
    success). On any call failure, contextualized_propositions is None
    (never silently falls back to the un-contextualized propositions --
    that would misrepresent a failed repair as a no-op one).
    """
    model = model or DEFAULT_CONTEXTUAL_MODEL
    target_idx, overlap_score = select_target_proposition(relation.get("nucleus"), propositions)
    if target_idx is None:
        return {
            "target_index": None, "target_proposition": None, "overlap_score": 0.0,
            "generated_context": None, "contextualized_propositions": None,
            "error": "no_propositions_to_target",
        }
    target_proposition = propositions[target_idx]
    prompt = build_contextual_retrieval_prompt(paragraph, target_proposition)
    response = generate_response(prompt, model=model)
    if not response or not hasattr(response, "content") or not (response.content or "").strip():
        return {
            "target_index": target_idx, "target_proposition": target_proposition,
            "overlap_score": overlap_score, "generated_context": None,
            "contextualized_propositions": None, "error": "no_response",
        }
    generated_context = response.content.strip()
    contextualized = list(propositions)
    contextualized[target_idx] = f"{generated_context} {target_proposition}"
    return {
        "target_index": target_idx,
        "target_proposition": target_proposition,
        "overlap_score": overlap_score,
        "generated_context": generated_context,
        "contextualized_propositions": contextualized,
        "error": None,
    }
