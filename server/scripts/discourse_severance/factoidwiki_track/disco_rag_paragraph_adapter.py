"""Task 8 (Experiment 3), arm 2: Disco-RAG adapted for paragraph-level
proposition recovery, re-implemented self-contained in this track (per
env_utils.py's established convention: factoidwiki_track/ does not import
its siblings outside the directory) from
../exp3_recovery_comparison/disco_rag_adapter.py's already-completed
adaptation -- same relationship severance_judge_paragraph.py already has
to ../severance_detection.py.

ATTRIBUTION (read this before quoting any arm-2 number): the pipeline
logic exercised here -- zero-shot RST-tree construction, discourse-aware
planning, and plan-conditioned generation -- is Disco-RAG's released
code, an EXTERNAL system's method, not this project's own.

  "Disco-RAG released code (commit 0755104) with gpt-4o-mini substituted
  for the published Llama-3.3-70B backbone; NOT an evaluation of Disco-RAG
  as published."

This exact statement (BACKBONE_SUBSTITUTION_STATEMENT below) must
accompany every report that cites arm-2 output, matching the CFR track's
own language.

VENDOR CODE LOCATION -- a deliberate, narrow, READ-ONLY exception to this
track's self-contained-scripts convention: the actual Disco-RAG released
code is not re-vendored a second time into factoidwiki_track/. It is read
directly from ../exp3_recovery_comparison/vendor/Disco-RAG (pinned at
commit 0755104beb39f877282808fee0dfe7905478adbb, an external third-party
repo, not the parallel CFR-track agent's own analysis code). Re-vendoring
a second full copy of an external repo pinned at the same commit would
duplicate ~1000s of lines for no benefit and risk two copies of "the same
commit" silently drifting apart. Nothing in ../exp3_recovery_comparison/
is written to or modified by this module -- only `vendor/Disco-RAG/src`
(the released code itself) is imported, exactly as
../exp3_recovery_comparison/disco_rag_adapter.py already does.

What runs REAL (imported unmodified from vendor/Disco-RAG/src) -- same
three stages as the CFR-track adaptation:
  - `RstParser.parse_chunks` (src/rst_tree/parser.py) with the released
    `RST_TREE_PROMPT`: zero-shot RST-tree construction over the source
    text.
  - `Planner.plan` (src/planning/planner.py) with the released
    `PLANNING_PROMPT`: the discourse-aware planning blueprint.
  - `DiscoRagGenerator.generate` (src/generation/disco_rag.py) with the
    released `DISCO_RAG_PROMPT`: generation conditioned on the query, the
    chunk, the RST tree serialization, and the plan.
No vendor file is modified or patched; this module only composes those
classes, exactly mirroring the CFR-track adapter's composition.

What is BYPASSED, explicitly (identical rationale to the CFR-track
adapter, restated for paragraph input):
  1. Retrieval + embedding (Qwen3-Embedding-8B). This experiment recovers
     a relation from ONE known source PARAGRAPH; there is no corpus to
     query, so the single "retrieved chunk" is constructed directly as a
     `langchain_core` Document with the shape `Retriever.retrieve` returns.
  2. The inter-chunk rhetorical graph. Defined over ordered pairs of
     DISTINCT chunks; empty by construction with exactly one chunk. Uses
     the released pipeline's own supported `use_graph=False`/`graph=None`
     code path.

What is SUBSTITUTED:
  - The published backbone (Llama-3.3-70B, local vLLM, beam search) cannot
    run on this machine. `ChatOpenAIBackbone` is a minimal `langchain_core`
    `BaseChatModel` satisfying the same chain interface
    (`prompt | llm | StrOutputParser()`) using the OpenAI API with
    gpt-4o-mini, temperature=0, seed=13 -- the same
    model/temperature/seed as every other LLM call in this project
    (server/api_call.py) -- and a single sampled completion instead of
    beam search. Duplicated here (not imported) from the CFR-track
    adapter's identical class, per this track's self-contained convention.

Input-shape adaptation (the actual point of this module, vs. just
importing the CFR-track adapter): the CFR track's chunk is one REGULATORY
SENTENCE and its RECOVERY_QUERY asks for a "claim" decomposition. Here the
chunk is one Wikipedia PARAGRAPH (this track's Propositionizer input unit)
and RECOVERY_QUERY asks for this track's own "proposition" vocabulary
(matching train.jsonl's `targets` field and every other module in this
track). The saved Condition-A propositions are NOT fed to the pipeline --
same design decision as the CFR-track adapter: Disco-RAG's design has no
input slot for a prior (faulty) decomposition, so feeding it one would
construct a hybrid corrector the released design does not describe.
"""

import os
import re
import sys
from typing import Any, Dict, List

TRACK_DIR = os.path.dirname(os.path.abspath(__file__))
DISCOURSE_SEVERANCE_DIR = os.path.dirname(TRACK_DIR)
SERVER_DIR = os.path.dirname(os.path.dirname(DISCOURSE_SEVERANCE_DIR))
# Read-only reference to the EXTERNAL vendored repo already checked into
# the sibling CFR-track experiment directory -- see module docstring.
VENDOR_DIR = os.path.join(DISCOURSE_SEVERANCE_DIR, "exp3_recovery_comparison", "vendor", "Disco-RAG")

for _p in (SERVER_DIR, VENDOR_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

if not os.path.isdir(os.path.join(VENDOR_DIR, "src")):
    raise RuntimeError(
        f"FATAL: vendored Disco-RAG repo not found at {VENDOR_DIR} -- "
        "arm 2 cannot run without the released code. (This track reads it "
        "read-only from ../exp3_recovery_comparison/vendor/Disco-RAG; it "
        "does not re-vendor a second copy.)"
    )

from langchain_core.documents import Document  # noqa: E402
from langchain_core.language_models.chat_models import BaseChatModel  # noqa: E402
from langchain_core.messages import AIMessage, BaseMessage  # noqa: E402
from langchain_core.messages.utils import convert_to_openai_messages  # noqa: E402
from langchain_core.outputs import ChatGeneration, ChatResult  # noqa: E402
from pydantic import PrivateAttr  # noqa: E402

# REAL vendor pipeline stages, imported unmodified. These imports pull in
# no vLLM/torch code: src/models/llm.py (the vLLM backbone) is only ever
# imported lazily / under TYPE_CHECKING by these modules.
from src.generation.disco_rag import DiscoRagGenerator  # noqa: E402
from src.planning.planner import Planner  # noqa: E402
from src.rst_tree.parser import RstParser  # noqa: E402

DISCO_RAG_COMMIT = "0755104beb39f877282808fee0dfe7905478adbb"
DISCO_RAG_COMMIT_SHORT = "0755104"

# This exact sentence must appear in every report that cites arm-2 output
# (task instruction, matching the CFR track's own language verbatim).
BACKBONE_SUBSTITUTION_STATEMENT = (
    "Disco-RAG released code (commit 0755104) with gpt-4o-mini substituted "
    "for the published Llama-3.3-70B backbone; NOT an evaluation of "
    "Disco-RAG as published."
)

BYPASS_NOTES = [
    "Retrieval/embedding stage (Retriever + Qwen3-Embedding-8B) bypassed: "
    "single-paragraph recovery has no corpus to query; the one chunk is "
    "constructed directly as a langchain Document in the same shape "
    "Retriever.retrieve returns.",
    "Inter-chunk rhetorical graph (GraphBuilder) bypassed via the released "
    "pipeline's own supported configuration (PipelineModules(use_graph="
    "False) / graph=None code path): the graph is defined over ordered "
    "pairs of distinct chunks and is empty by construction with one chunk.",
    "Backbone substituted: vLLM beam search (beam_width 3) over local "
    "Llama-3.3-70B replaced by a single OpenAI chat completion "
    "(gpt-4o-mini, temperature=0, seed=13).",
    "Vendor code read directly from "
    "../exp3_recovery_comparison/vendor/Disco-RAG (read-only, not "
    "re-vendored a second time) -- same commit, same released files.",
]

# The fixed recovery query given to the pipeline for every case, retargeted
# from the CFR-track adapter's "claim"/"regulatory source text" vocabulary
# to this track's "proposition"/"paragraph" vocabulary (matches
# train.jsonl's `targets` field and this track's Propositionizer/
# condition_b_atomizer.py nomenclature).
RECOVERY_QUERY = (
    "Decompose the source paragraph in the retrieved chunk into a set of "
    "atomic, self-contained propositions suitable for a downstream reader "
    "with no access to the original paragraph. Each proposition must "
    "express exactly one assertion, and every condition or concession that "
    "governs a claim in the source paragraph must remain attached to the "
    "claim it governs -- no proposition may assert a governed claim "
    "unconditionally or without its concession. Output each proposition on "
    "its own line, starting with '- '."
)


class ChatOpenAIBackbone(BaseChatModel):
    """Minimal langchain BaseChatModel over the OpenAI chat API, standing
    in for the published ChatVllmBeamSearch backbone (see module
    docstring). Duplicated (not imported) from
    ../exp3_recovery_comparison/disco_rag_adapter.py's identical class,
    per this track's self-contained-scripts convention. Exposes
    `model_name` because the released RstParser reads it for its
    per-model output cache.
    """

    model_name: str = "gpt-4o-mini"
    temperature: float = 0.0
    seed: int = 13
    max_retries: int = 3

    _client: Any = PrivateAttr(default=None)

    @property
    def _llm_type(self) -> str:
        return "openai-chat-substituted-disco-rag-backbone"

    @property
    def _identifying_params(self) -> Dict[str, Any]:
        return {"model_name": self.model_name, "seed": self.seed,
                "temperature": self.temperature}

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI

            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                raise ValueError(
                    "FATAL: OPENAI_API_KEY environment variable is not set "
                    "-- arm 2 cannot run (and will not silently no-op)."
                )
            self._client = OpenAI(api_key=api_key, max_retries=self.max_retries)
        return self._client

    def _generate(self, messages: List[BaseMessage], stop=None,
                  run_manager=None, **kwargs) -> ChatResult:
        completion = self._get_client().chat.completions.create(
            model=self.model_name,
            messages=convert_to_openai_messages(messages),
            temperature=self.temperature,
            seed=self.seed,
        )
        text = completion.choices[0].message.content or ""
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=text))]
        )


_PROPOSITION_LINE_RE = re.compile(r"^(?:[-*•]|\d+[.)])\s+(.*)$")


def parse_answer_propositions(answer_text):
    """Parse the generator's free-text ANSWER into a proposition list: one
    proposition per '- ' / numbered line. If the model returned prose with
    no list structure, the whole answer is kept as ONE proposition -- that
    is what a downstream reader would see, so it is what gets judged.
    Returns (propositions, parse_mode) where parse_mode is 'lines' or
    'whole_answer'. Same parsing logic as the CFR-track adapter's
    parse_answer_claims, renamed to this track's vocabulary.
    """
    propositions = []
    for line in (answer_text or "").splitlines():
        m = _PROPOSITION_LINE_RE.match(line.strip())
        if m and m.group(1).strip():
            propositions.append(m.group(1).strip())
    if propositions:
        return propositions, "lines"
    if (answer_text or "").strip():
        return [answer_text.strip()], "whole_answer"
    return [], "empty"


class DiscoRagParagraphRecovery:
    """Composes the released Disco-RAG stages for one-paragraph recovery,
    mirroring DiscoRagPipeline.build_structures/run (src/pipeline.py) with
    retrieval bypassed and use_graph=False (see module docstring) -- same
    composition as the CFR-track adapter's DiscoRagSingleSentenceRecovery,
    retargeted to paragraph input.
    """

    def __init__(self, backbone=None):
        self.backbone = backbone or ChatOpenAIBackbone()
        # REAL vendor classes; the substituted backbone only changes what
        # `prompt | llm | StrOutputParser()` calls under the hood.
        self.parser = RstParser(self.backbone)
        self.planner = Planner(self.backbone)
        self.generator = DiscoRagGenerator(self.backbone)

    def recover(self, paragraph):
        """Runs RST parse -> plan -> generate on one source paragraph.
        Returns a dict with the raw intermediates (for audit) and the
        parsed recovered proposition list. Raises on LLM failure --
        callers must record the error loudly, not swallow it.
        """
        doc = Document(page_content=paragraph, metadata={"chunk_id": 0})
        # Stage 1 (REAL vendor code): zero-shot RST-tree construction
        # over the source text.
        trees = self.parser.parse_chunks([doc])
        # Stage 2 (REAL vendor code): discourse-aware planning blueprint.
        # graph=None is the released pipeline's own use_graph=False path.
        plan = self.planner.plan(RECOVERY_QUERY, [doc], trees, None)
        # Stage 3 (REAL vendor code): plan-conditioned generation.
        answer = self.generator.generate(RECOVERY_QUERY, [doc], trees, None, plan)
        propositions, parse_mode = parse_answer_propositions(answer)
        tree = trees[0] if trees else None
        return {
            "rst_tree_serialized": tree.serialize() if tree else None,
            "rst_tree_raw": tree.raw if tree else None,
            "rst_edu_count": len(tree.edus) if tree else 0,
            "rst_relation_count": len(tree.relations) if tree else 0,
            "plan_text": plan.text,
            "answer_raw": answer,
            "propositions": propositions,
            "answer_parse_mode": parse_mode,
        }
