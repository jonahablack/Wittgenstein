"""Adapter: run AtomicRAG's own OpenIE atomization step (and ONLY that
step) over FactoidWiki paragraphs, so its atomic-unit output ("knowledge
fragments") can be scored with this project's existing severance-detection
infrastructure alongside Chen et al.'s Propositionizer (see
../severance_judge_paragraph.py, ../condition_b_atomizer.py,
../run_experiment_1_2.py).

ATTRIBUTION (read this before quoting any atomicrag_track number): the
atomization logic exercised here -- NER, then unified
triple+knowledge-fragment extraction, both via LLM prompts -- is
AtomicRAG's released code (vendor/AtomicRAG, pinned at commit
4e6f0ed485c7839dae200d112f89efde2d51b41b, cloned 2026-08-14), an EXTERNAL,
published system

    Hou, Y., Yuan, D., Zhou, S., Chen, X., Liang, K., Wang, S., Liu, X.,
    Huang, J. "AtomicRAG: Atom-Entity Graphs for Retrieval-Augmented
    Generation." arXiv:2604.20844. https://github.com/7HHHHH/AtomicRAG

Every report that cites atomicrag_track output must carry the statement in
ATTRIBUTION_STATEMENT below.

What runs REAL (imported unmodified from vendor/AtomicRAG/atomicrag):
  - `OpenIE.batch_unified_openie` (information_extraction/openie_openai.py)
    -- the released NER -> unified-triple-and-fragment-extraction pipeline,
    including its own released prompts (prompts/templates/ner.py,
    prompts/templates/unified_triple_knowledge_fragment_extraction.py) and
    its own released JSON-response parsing.
  - `CacheOpenAI` (llm/openai_gpt.py) -- the released OpenAI chat-completion
    wrapper, including its own sqlite response cache, retry policy
    (tenacity, max_retry_attempts), and async semaphore-bounded
    concurrency (`max_concurrency`) -- this IS the "batched/parallel path"
    the task brief asks to use instead of hammering the API one-by-one:
    `batch_unified_openie` schedules NER for every paragraph concurrently,
    then unified extraction for every paragraph concurrently, bounded by
    `BaseConfig.max_concurrency`.
  - `BaseConfig` (utils/config_utils.py) -- the released config dataclass,
    used with its own defaults (llm_name="gpt-4o-mini", temperature=0,
    unified_extraction=True) plus one project-convention override (seed=13,
    see SUBSTITUTED below) and one required override (save_dir, which
    BaseConfig normally defaults from AtomicRAG's own dataset-runner
    scaffolding that this adapter never touches -- see BYPASSED below).
  - `compute_mdhash_id` (utils/misc_utils.py) and the ChunkInfo *shape*
    actually consumed by `batch_unified_openie` -- see CHUNKINFO NOTE below.

What is BYPASSED, explicitly (per the task: "Instantiate ONLY the OpenIE
component... not the full AtomicRAG class. Skip embedding stores,
igraph/AEG construction, PPR, and fragment-entity connections entirely"):
  1. The `AtomicRAG` class itself (atomicrag/atomicrag.py) and everything
     downstream of OpenIE in its `index()` method: entity/fragment
     embedding (`EmbeddingStore`), the Atom-Entity Graph (`igraph`),
     Personalized PageRank retrieval, and `FragmentFilter`. This adapter
     calls `OpenIE.batch_unified_openie` directly, the exact call
     `AtomicRAG.index()` itself makes at atomicrag.py's
     `if self.global_config.unified_extraction: ... =
     self.openie.batch_unified_openie(new_openie_rows)` -- never
     `AtomicRAG.index()` itself.
  2. A real, confirmed import-time problem this bypass also had to solve:
     `atomicrag/__init__.py` unconditionally does `from .atomicrag import
     AtomicRAG`, and `atomicrag/atomicrag.py` unconditionally does
     `import igraph as ig` and `from .embedding_model import
     _get_embedding_model_class, BaseEmbeddingModel`.
     `atomicrag/embedding_model/__init__.py` in turn unconditionally
     imports GritLM/NVEmbedV2/Contriever/BGE/OpenAI embedding classes,
     EVERY one of which does an unguarded top-level `import torch` and/or
     `from transformers import AutoModel` (verified by reading all six
     files in atomicrag/embedding_model/*.py -- none of it is lazy or
     try/except-guarded). So a plain `import atomicrag...` statement pulls
     in torch/transformers/gritlm/igraph/boto3 just to reach OpenIE, none
     of which OpenIE itself (information_extraction/openie_openai.py)
     needs. To honor "skip embeddings/graph/PPR" at the (real,
     expensive-to-install) import level and not just the object-instantiation
     level, this module pre-registers an empty namespace module as
     `sys.modules["atomicrag"]` (with `__path__` pointed at the real
     vendored `atomicrag/` directory) BEFORE importing the specific
     submodules it needs. This does not modify any vendored file on disk;
     it only prevents Python's package-import machinery from executing
     `atomicrag/__init__.py`'s eager `from .atomicrag import AtomicRAG`
     line. `atomicrag.llm`, `atomicrag.information_extraction`,
     `atomicrag.prompts`, and `atomicrag.utils` still execute their OWN
     real, unmodified `__init__.py` files (see IMPORT-TIME DEPENDENCY
     NOTE below -- one of those, `atomicrag/llm/__init__.py`, still
     requires installing the real `litellm` package, unconditionally
     imported there for a Bedrock backend branch this adapter never
     reaches). Verified empirically (test import + `assert
     "atomicrag.atomicrag" not in sys.modules` etc. all passed) before
     this file was written.

What is SUBSTITUTED: nothing at the model level -- unlike the
exp3_recovery_comparison/disco_rag_adapter.py case (whose published
backbone, local vLLM Llama-3.3-70B, cannot run on this machine), AtomicRAG's
own README already uses gpt-4o-mini as its example/default model throughout
(`--model_name gpt-4o-mini` / `--model gpt-4o-mini` in the installation and
quick-start commands, confirmed by grepping README.md), matching this
project's own default LLM call (server/api_call.py: gpt-4o-mini,
temperature=0, seed=13). The ONE parameter this adapter overrides from
AtomicRAG's own BaseConfig default is `seed`: BaseConfig defaults to
`seed=None` (AtomicRAG's own runs are not seeded), and this adapter sets
`seed=13` purely to match this project's own convention for every other
LLM call in discourse_severance/, not because AtomicRAG's design needs it.
`temperature=0` is already BaseConfig's own default, not a project override.

NER and triple outputs are DISCARDED, not a bug: `batch_unified_openie`
(and `batch_openie`) always returns all three
(`Dict[str, NerRawOutput], Dict[str, TripleRawOutput],
Dict[str, KnowledgeFragmentRawOutput]`) -- there is no released call that
returns knowledge fragments alone. This adapter keeps only lightweight,
non-content diagnostics from the NER/triple outputs (entity count, triple
count, per-chunk error string) for cost/sanity accounting and discards the
actual entity/triple text, since only `KnowledgeFragmentRawOutput
.knowledge_fragments` (atomicrag.py's own access pattern, e.g.
`fragment_results_dict[doc_id].knowledge_fragments` at its merge step) is
the atomic unit this experiment measures severance against.

CONDITION B / RELATION-AWARE ELICITATION IS NOT POSSIBLE FOR THIS CHUNKER,
AND THIS IS A DESIGN LIMITATION, NOT AN OVERSIGHT: this project's own
Condition B (../condition_b_atomizer.py) works by putting the
already-elicited relation type/nucleus/satellite/connective directly into
the atomization PROMPT and instructing the model to preserve it.
AtomicRAG's OpenIE prompts have no such input slot: the unified-extraction
prompt template (prompts/templates/unified_triple_knowledge_fragment_extraction.py,
`unified_extraction_frame`) is parameterized ONLY by `{passage}` and
`{named_entity_json}`; the non-unified knowledge-fragment-extraction
prompt (prompts/templates/knowledge_fragment_extraction.py,
`knowledge_fragment_extraction_frame`) is parameterized ONLY by
`{passage}` and `{candidate_entities}`. Neither `OpenIE`'s public methods
(`batch_openie`, `batch_unified_openie`, and their `_async`/per-chunk
counterparts) nor `ChunkInfo` accept a relation hint of any kind. Adding
one would mean editing the vendored prompt template file, which would
violate "runs unmodified" above and this project's own precedent
(disco_rag_adapter.py composes released classes but never patches
released prompts). So this track reports ONLY the standard-atomization
condition for AtomicRAG (an analog of this project's "Condition A"); there
is no AtomicRAG analog of "Condition B" / Experiment 1's
capacity-vs-elicitation ablation, and that is reported as a stated
limitation, not papered over.

CHUNKINFO NOTE: `openie_openai.py` declares a `ChunkInfo` TypedDict with
four fields (`num_tokens`, `content`, `chunk_order`, `full_doc_ids`), but
grepping the ENTIRE vendored repo shows no call site ever constructs one
with all four fields populated. The one real call site,
`AtomicRAG.index()` (atomicrag.py), builds
`doc_to_rows = {doc_id: {'hash_id': doc_id, 'content': doc} ...}` -- just
`hash_id` and `content` -- and passes that straight to
`batch_unified_openie`/`batch_openie`. Reading `batch_unified_openie_async`
confirms only `chunk["content"]` is ever read
(`chunk_passages = {chunk_key: chunk["content"] for chunk_key, chunk in
chunks.items()}`); `chunk_key` (the dict key, not a ChunkInfo field) is
what becomes each output's `chunk_id`. So the "minimal correct way to
construct one" is the same shape AtomicRAG's own real call site uses --
`build_chunk_info` below mirrors it exactly, keyed by
`compute_mdhash_id(content, "doc-")` (AtomicRAG's own doc_id scheme).

IMPORT-TIME DEPENDENCY NOTE: importing this module requires `litellm`
installed in the active environment (see ../requirements.txt in this
directory for the one addition this track needed beyond what the shared
project venv already had: openai, numpy, tenacity, tqdm, httpx, filelock,
packaging were all already present).
"""

import os
import sys
import types
from typing import Dict, List, Optional

ATOMICRAG_TRACK_DIR = os.path.dirname(os.path.abspath(__file__))
FACTOIDWIKI_TRACK_DIR = os.path.dirname(ATOMICRAG_TRACK_DIR)
DISCOURSE_SEVERANCE_DIR = os.path.dirname(FACTOIDWIKI_TRACK_DIR)
SERVER_DIR = os.path.dirname(os.path.dirname(DISCOURSE_SEVERANCE_DIR))
VENDOR_DIR = os.path.join(ATOMICRAG_TRACK_DIR, "vendor", "AtomicRAG")

if not os.path.isdir(os.path.join(VENDOR_DIR, "atomicrag")):
    raise RuntimeError(
        f"FATAL: vendored AtomicRAG repo not found at {VENDOR_DIR} -- "
        "atomicrag_track cannot run without the released code."
    )

if VENDOR_DIR not in sys.path:
    sys.path.insert(0, VENDOR_DIR)

# --- Stub the top-level `atomicrag` package (see BYPASSED section above) --
# Must happen BEFORE any `atomicrag.*` import, and only once per process.
if "atomicrag" not in sys.modules:
    _atomicrag_stub = types.ModuleType("atomicrag")
    _atomicrag_stub.__path__ = [os.path.join(VENDOR_DIR, "atomicrag")]
    sys.modules["atomicrag"] = _atomicrag_stub
elif not hasattr(sys.modules["atomicrag"], "__path__"):
    raise RuntimeError(
        "FATAL: something other than this adapter's stub already occupies "
        "sys.modules['atomicrag'] -- refusing to guess which one is real."
    )

from atomicrag.information_extraction.openie_openai import OpenIE  # noqa: E402
from atomicrag.llm.openai_gpt import CacheOpenAI  # noqa: E402
from atomicrag.utils.config_utils import BaseConfig  # noqa: E402
from atomicrag.utils.misc_utils import compute_mdhash_id  # noqa: E402

ATOMICRAG_COMMIT = "4e6f0ed485c7839dae200d112f89efde2d51b41b"
ATOMICRAG_COMMIT_SHORT = "4e6f0ed"
ATOMICRAG_CLONE_DATE = "2026-08-14"
ATOMICRAG_REPO_URL = "https://github.com/7HHHHH/AtomicRAG.git"

# This exact statement must appear in every report that cites
# atomicrag_track output.
ATTRIBUTION_STATEMENT = (
    "AtomicRAG (Hou et al., arXiv:2604.20844, "
    "https://github.com/7HHHHH/AtomicRAG) released OpenIE code (commit "
    f"{ATOMICRAG_COMMIT_SHORT}), OpenIE.batch_unified_openie only "
    "(NER + unified triple/knowledge-fragment extraction) -- the "
    "embedding store, Atom-Entity Graph, PPR retrieval, and fragment "
    "filter stages were never run. gpt-4o-mini, temperature=0 are "
    "AtomicRAG's own published defaults; seed=13 is this project's "
    "convention override, not AtomicRAG's design. Condition-B / "
    "relation-aware elicitation is NOT supported by this chunker's "
    "prompts (no relation-hint input slot exists) and was not attempted."
)

DEFAULT_MODEL = "gpt-4o-mini"  # AtomicRAG's own BaseConfig default too
DEFAULT_TEMPERATURE = 0  # AtomicRAG's own BaseConfig default
DEFAULT_SEED = 13  # project-convention override; AtomicRAG's own default is None
DEFAULT_MAX_CONCURRENCY = 20  # see docstring note in run_atomicrag_atomization


def make_config(save_dir, max_concurrency=DEFAULT_MAX_CONCURRENCY):
    """Real, unmodified `BaseConfig` (utils/config_utils.py), just with the
    fields this adapter needs set explicitly (fail-fast: `save_dir` is
    required by `CacheOpenAI.from_experiment_config` for its on-disk
    response cache and has no sane silent default here, since this adapter
    never runs AtomicRAG's own dataset-runner scaffolding that would
    normally set it).
    """
    return BaseConfig(
        llm_name=DEFAULT_MODEL,
        temperature=DEFAULT_TEMPERATURE,
        seed=DEFAULT_SEED,
        save_dir=save_dir,
        max_concurrency=max_concurrency,
        unified_extraction=True,  # AtomicRAG's own default; explicit here since it selects batch_unified_openie's 2-call-per-chunk path over batch_openie's 3-call-per-chunk path
    )


def make_openie(config):
    """Real, unmodified `CacheOpenAI` + `OpenIE` (llm/openai_gpt.py,
    information_extraction/openie_openai.py). `CacheOpenAI` reads
    OPENAI_API_KEY from the process environment via the `openai` SDK's own
    default client behavior (no key is passed explicitly here or by
    AtomicRAG's own code) -- callers must load server/.env first (see
    run_pilot.py / run_atomicrag_experiment.py's `_load_server_env`).
    """
    llm = CacheOpenAI.from_experiment_config(config)
    return OpenIE(llm_model=llm, global_config=config)


def build_chunk_info(id_to_content: Dict[str, str]) -> Dict[str, dict]:
    """Mirrors AtomicRAG.index()'s own `doc_to_rows` construction exactly
    (see CHUNKINFO NOTE in the module docstring): `{key: {"hash_id": key,
    "content": text}}`. `id_to_content` keys are THIS project's own ids
    (pool_index-derived, so results join back to the FactoidWiki logs
    unambiguously) -- not `compute_mdhash_id`, which is only AtomicRAG's
    own doc-identity scheme and is not needed here since we never call
    AtomicRAG's disk-based OpenIE cache/merge machinery (bypassed, see
    module docstring).
    """
    return {key: {"hash_id": key, "content": content} for key, content in id_to_content.items()}


def run_atomicrag_atomization(id_to_content: Dict[str, str], save_dir: str,
                               max_concurrency: int = DEFAULT_MAX_CONCURRENCY) -> Dict[str, dict]:
    """Runs AtomicRAG's real `OpenIE.batch_unified_openie` ONCE over every
    paragraph in `id_to_content` (the batched/parallel path, per the task
    brief -- NOT a Python-level loop of one-by-one calls; concurrency is
    AtomicRAG's own async semaphore, bounded by `max_concurrency`).

    Raises on any top-level failure (e.g. missing/invalid OPENAI_API_KEY,
    a billing/quota error that blocks the whole batch) -- this project's
    fail-fast convention: a real error must stop the run and be reported
    exactly, never be silently swallowed into a partial/fabricated result.
    A PER-CHUNK failure (one paragraph's call erroring while others
    succeed) is AtomicRAG's own released fail-safe behavior in
    `unified_triple_knowledge_fragment_extraction_async`'s try/except --
    surfaced here via `metadata.get("error")` -> `atomicrag_error`, never
    hidden.

    Returns {id: {
        "atomicrag_propositions": List[str],   # = KnowledgeFragmentRawOutput.knowledge_fragments, renamed to match this track's proposition/claim vocabulary (see severance_judge_paragraph.py's docstring) -- NOT a reworded/altered value, same strings AtomicRAG itself produced
        "n_atomicrag_propositions": int,
        "atomicrag_error": str or None,        # from the unified-extraction call's own metadata, if any
        "atomicrag_n_ner_entities": int,        # count only -- NER text itself discarded, see module docstring
        "atomicrag_n_triples": int,             # count only -- triple text itself discarded, see module docstring
        "atomicrag_prompt_tokens": int,         # NER call + unified-extraction call combined
        "atomicrag_completion_tokens": int,
    }}
    """
    config = make_config(save_dir=save_dir, max_concurrency=max_concurrency)
    openie = make_openie(config)
    chunks = build_chunk_info(id_to_content)

    openie.metadata_list = []  # reset, mirrors AtomicRAG.index()'s own reset before batch calls
    ner_results, triple_results, fragment_results = openie.batch_unified_openie(chunks)

    out = {}
    for key in id_to_content:
        ner = ner_results[key]
        triples = triple_results[key]
        fragments = fragment_results[key]
        ner_error = (ner.metadata or {}).get("error")
        frag_error = (fragments.metadata or {}).get("error")
        prompt_tokens = (ner.metadata or {}).get("prompt_tokens", 0) + (fragments.metadata or {}).get("prompt_tokens", 0)
        completion_tokens = (ner.metadata or {}).get("completion_tokens", 0) + (fragments.metadata or {}).get("completion_tokens", 0)
        out[key] = {
            "atomicrag_propositions": list(fragments.knowledge_fragments),
            "n_atomicrag_propositions": len(fragments.knowledge_fragments),
            "atomicrag_error": frag_error or ner_error,
            "atomicrag_n_ner_entities": len(ner.unique_entities),
            "atomicrag_n_triples": len(triples.triples),
            "atomicrag_prompt_tokens": prompt_tokens,
            "atomicrag_completion_tokens": completion_tokens,
        }
    return out
