"""Thin adapter around NuggetIndex's `LLMExtractor` -- the SECOND external
chunker measured by this comparison (the first is Chen et al.'s real
Propositionizer, in ../ -- see ../README.md).

FRAMING, STATED EXPLICITLY (do not soften or omit this elsewhere in the
project's reporting of these numbers): NuggetIndex, per its own README
and CITATION.cff (SIGIR 2026, DOI 10.1145/3805712.3809687, Zerhoudi/
Granitzer/Mitrovic), self-describes as "a governed, time-aware
fact-retrieval sidecar for RAG" -- its actual design purpose is
validity-interval tracking, staleness detection (Active/Deprecated/
Contested lifecycle states), and cross-source conflict resolution at
QUERY time, over a fact store built at INGEST time. It is NOT designed,
marketed, or evaluated by its own authors as a general-purpose
chunker/atomizer the way Propositionizer or AtomicRAG are.

What this file actually calls is ONE component of that larger system in
isolation: `nuggetindex.extractors.llm.LLMExtractor.aextract`, the piece
of NuggetIndex's ingest-time pipeline that turns a raw text span into a
set of atomic subject-predicate-object fact triples. This is a real,
functioning code path -- confirmed by reading the actual cloned source
(src/nuggetindex/extractors/llm.py, extractors/base.py,
extractors/clients/base.py, extractors/prompts/extraction.md), not
assumed from the README -- but pulling it out and calling it directly,
the way this file does, is a DECOUPLED use of one piece of NuggetIndex's
pipeline, not an invocation of NuggetIndex "as designed". None of
NuggetIndex's actual governance machinery runs here: no ValidityInterval
inference beyond a placeholder `start=now` stamp (the extractor's own
`aextract` leaves real temporal inference as a documented "Phase 4" TODO
-- confirmed by the `# temporal inference: Phase 4` comment sitting right
next to `ValidityInterval(start=now)` in llm.py, and by the fact that the
LLM-emitted `temporal_expression` field on each triple is read from the
response model but never actually used inside `aextract`), no lifecycle
state assignment, no cross-source conflict detection, no NuggetStore
persistence, no `DocumentConstructor` orchestration (canonicalize / dedup
/ conflict stages). We call `LLMExtractor.aextract` and read the raw
triples straight off `ExtractionResult.nugget.fact`, nothing else.

ATOMIC UNIT SHAPE: NuggetIndex's `LLMExtractor` produces a
subject-predicate-object triple (see `_TripleOut` / `ExtractionPayload`
in extractors/llm.py), NOT a natural-language sentence-like proposition
the way Propositionizer's `targets` or the gpt-4o-mini relation-aware
atomizer's `propositions` are. Predicates are normalized to canonical
camelCase strings (extractors/prompts/extraction.md's "Predicate
normalisation (strict)" section -- e.g. "chiefExecutiveOfficer",
"foundedIn"), not natural-language verb phrases. This is why this track
needs its own triple-aware severance judge (../triple_severance_judge.py
in this directory) rather than reusing ../severance_judge_paragraph.py
(the natural-language judge) unmodified -- see that file's docstring for
the judge-design decision and why.

CONTEXT-WINDOW CAVEAT -- CHECKED AGAINST THE REAL CODE, NOT ASSUMED:
`LLMExtractor.aextract(text, *, context="", source_id=None)` accepts an
optional `context` string that gets folded into the prompt as
"Context: {context}" (see llm.py's `_build_messages`), but NOTHING in
NuggetIndex's own code populates this automatically from surrounding
text. Read in full: `extractors/base.py` (the `BaseExtractor` ABC),
`pipeline/constructor.py` (`DocumentConstructor.aprocess`, the only
caller of `aextract` anywhere in the pipeline), and
`extractors/prompts/extraction.md` (the prompt template itself, which
only has `{text}` and `{context_hint}` placeholders). `DocumentConstructor
.aprocess` calls `self.extractor.aextract(doc.text, **extract_kwargs)`
with the WHOLE `Document.text` as `text` and never passes `context` at
all -- there is no sentence-window assembly ("current sentence + one
preceding sentence" or any variant) anywhere in NuggetIndex's own source.
The claim that NuggetIndex's extraction has some built-in sentence-window
context-enrichment is FALSE as confirmed by reading the real code; it was
worth checking (a wrong assumption here would have meant explaining away
a severance-rate difference with a confound that doesn't actually exist),
but it does not apply. This adapter calls `aextract(text=paragraph)` with
`context` left at its default (`""`), so NuggetIndex sees exactly the
same one-paragraph unit of text as Propositionizer and the gpt-4o-mini
atomizer see for the same source record -- no cross-chunker context
asymmetry here.

MODEL CHOICE: `LLMConfig(provider="openai", model="gpt-4o-mini")`, the
exact quick-start usage from NuggetIndex's own README, matching this
project's own default model everywhere else (server/api_call.py's
`generate_response` default, ../condition_b_atomizer.py's
DEFAULT_CONDITION_B_MODEL, ../severance_judge_paragraph.py's judge
default) -- same model as every other chunker/judge in this comparison,
so a model-choice confound is not introduced here.

API KEY: `LLMConfig.api_key` is left `None`. NuggetIndex's
`OpenAIClient.__init__` (extractors/clients/openai.py) passes
`api_key=unwrap_api_key(cfg.api_key)` (i.e. `None`) straight into
`openai.AsyncOpenAI(...)`, and the `openai` SDK itself falls back to
reading `OPENAI_API_KEY` from the process environment when `api_key` is
`None` -- the same variable `server/api_call.py.generate_response` reads
directly. `env_utils.load_server_env()` (called by the orchestration
script before any extraction) loads `server/.env` into `os.environ` the
same way every sibling script in this project does, so both codepaths
pick up the identical key.

CLIENT LIFETIME: a fresh `LLMExtractor` (and therefore a fresh
`AsyncOpenAI`/`instructor` client) is constructed on every call to
`extract_triples`, mirroring `server/api_call.py.generate_response`'s own
convention of constructing a fresh `OpenAI(...)` client per call rather
than sharing one across calls. This also sidesteps a real hazard specific
to this codebase: `AsyncOpenAI`'s underlying `httpx.AsyncClient` is bound
to the asyncio event loop it was created under, and this track's
orchestration script runs extraction calls from a `ThreadPoolExecutor`
(../run_two_stage_pipeline.py's `_parallel_map` pattern, reused here --
see run_nuggetindex_experiment.py), where each worker thread calls
`asyncio.run(...)` and therefore gets its OWN fresh event loop; sharing
one client/loop across threads here would be a genuine bug, not just an
inefficiency.
"""

import asyncio

from nuggetindex.extractors.clients.base import LLMConfig
from nuggetindex.extractors.llm import LLMExtractor

DEFAULT_PROVIDER = "openai"
DEFAULT_MODEL = "gpt-4o-mini"


def extract_triples(text, model=DEFAULT_MODEL, provider=DEFAULT_PROVIDER):
    """Runs NuggetIndex's real `LLMExtractor.aextract` on `text` (a single
    FactoidWiki paragraph -- see env_utils.GOVERN_SOURCE_LOG /
    ELABORATION_SOURCE_LOG for where `text` comes from) and returns:

        {"triples": [ {subject, predicate, object, evidence_span,
                        confidence, subject_type, object_type}, ... ],
         "_error": None or a str describing what went wrong}

    Never raises on a call/parse failure -- returns an empty triple list
    with `_error` set instead, matching this project's established
    fail-loud-but-don't-crash-the-batch convention for atomizer calls
    (see ../condition_b_atomizer.py's `run_condition_b`). A severance
    judge scoring an empty triple list is itself an informative, real
    "nothing usable was extracted" outcome, not a value that should stop
    the batch.
    """
    cfg = LLMConfig(provider=provider, model=model)
    extractor = LLMExtractor(cfg)
    try:
        results = asyncio.run(extractor.aextract(text=text))
    except Exception as exc:  # noqa: BLE001 -- deliberately broad: log any
        # real failure (network, instructor validation, provider error)
        # rather than letting one paragraph crash the whole batch, per
        # this project's atomizer-call convention (see docstring above).
        return {"triples": [], "_error": f"{type(exc).__name__}: {exc}"}

    triples = []
    for r in results:
        fact = r.nugget.fact
        triples.append({
            "subject": fact.subject,
            "predicate": fact.predicate,
            "object": fact.object,
            "evidence_span": fact.text,
            "confidence": r.confidence,
            "subject_type": fact.subject_type,
            "object_type": fact.object_type,
        })
    return {"triples": triples, "_error": None}
