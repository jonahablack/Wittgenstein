"""Arm-1 adapter: run the released Disco-RAG pipeline's own code for
single-sentence discourse-relation recovery, with a substituted LLM
backbone.

ATTRIBUTION (read this before quoting any arm-1 number): the pipeline
logic exercised here -- zero-shot RST-tree construction, discourse-aware
planning, and plan-conditioned generation -- is Disco-RAG's released
code (vendor/Disco-RAG, pinned at commit
0755104beb39f877282808fee0dfe7905478adbb, 2026-07-12), an EXTERNAL
system's method, not this project's. Every report that cites arm-1
output must carry the statement in BACKBONE_SUBSTITUTION_STATEMENT
below.

What runs REAL (imported unmodified from vendor/Disco-RAG/src):
  - `RstParser.parse_chunks` (src/rst_tree/parser.py) with the released
    `RST_TREE_PROMPT` (src/prompts/templates.py): zero-shot RST-tree
    construction over the source text, including the released output
    parser into `RstTree`/`EDU`/`RstRelation` structures.
  - `Planner.plan` (src/planning/planner.py) with the released
    `PLANNING_PROMPT`: the discourse-aware planning blueprint.
  - `DiscoRagGenerator.generate` (src/generation/disco_rag.py) with the
    released `DISCO_RAG_PROMPT`: generation conditioned on the query,
    the chunk, the RST tree serialization, and the plan, including the
    released `extract_answer` post-processing.
No vendor file is modified or patched; this module only composes those
classes, mirroring `DiscoRagPipeline.build_structures`/`run`
(src/pipeline.py lines 58-82) minus the two bypassed stages below.

What is BYPASSED, explicitly:
  1. Retrieval + embedding (src/retrieval/retriever.py,
     src/models/embedder.py -- Qwen3-Embedding-8B). This experiment
     recovers a relation from ONE known source sentence; there is no
     corpus to query, so the single "retrieved chunk" is constructed
     directly as a `langchain_core` `Document` with the same
     shape (`page_content` + `metadata["chunk_id"]`) that
     `Retriever.retrieve` returns. Nothing is retrieved because there
     is nothing to retrieve from.
  2. The inter-chunk rhetorical graph (src/rhetorical_graph/graph.py).
     The graph is defined over ordered pairs of DISTINCT chunks; with
     exactly one chunk it is empty by construction. The released
     pipeline itself exposes this as a supported configuration
     (`PipelineModules(use_graph=False)`, src/pipeline.py lines 18-23),
     and `Planner.plan`/`DiscoRagGenerator.generate` both accept
     `graph=None` and serialize it as "None" -- that released code path
     is the one used here.

What is SUBSTITUTED:
  - The published backbone is Llama-3.3-70B served by local vLLM with
    beam search (beam_width 3, tensor_parallel_size 4 -- see
    vendor/Disco-RAG/configs/default.yaml and src/models/llm.py). That
    cannot run on this machine. `ChatOpenAIBackbone` below is a
    minimal `langchain_core` `BaseChatModel` that satisfies the same
    chain interface (`prompt | llm | StrOutputParser()`) using the
    OpenAI API with gpt-4o-mini, temperature=0, seed=13 -- the same
    model/temperature/seed as every other LLM call in this project
    (server/api_call.py) -- and a single sampled completion instead of
    beam search.

Input design decision (documented, not hidden): Disco-RAG's inputs are
a user query + retrieved chunks + discourse structures; its design has
no input slot for a prior (faulty) decomposition. The chunk input the
pipeline design calls for is therefore the ORIGINAL SOURCE SENTENCE,
and the fixed RECOVERY_QUERY below asks the pipeline to produce the
atomic-claim decomposition. The saved Condition-A claims are NOT fed to
the pipeline -- feeding them would construct a hybrid corrector that
the released design does not describe.
"""

import os
import re
import sys
from typing import Any, Dict, List, Optional

EXP3_DIR = os.path.dirname(os.path.abspath(__file__))
VENDOR_DIR = os.path.join(EXP3_DIR, "vendor", "Disco-RAG")
SCRIPT_DIR = os.path.dirname(EXP3_DIR)  # .../discourse_severance
SERVER_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
for _p in (SERVER_DIR, VENDOR_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

if not os.path.isdir(os.path.join(VENDOR_DIR, "src")):
    raise RuntimeError(
        f"FATAL: vendored Disco-RAG repo not found at {VENDOR_DIR} -- "
        "arm 1 cannot run without the released code."
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

# This exact sentence must appear in every report that cites arm-1 output.
BACKBONE_SUBSTITUTION_STATEMENT = (
    "Disco-RAG released code (commit 0755104) with gpt-4o-mini substituted "
    "for the published Llama-3.3-70B backbone and the retrieval stage "
    "bypassed; NOT the paper's exact configuration."
)

BYPASS_NOTES = [
    "Retrieval/embedding stage (Retriever + Qwen3-Embedding-8B) bypassed: "
    "single-sentence recovery has no corpus to query; the one chunk is "
    "constructed directly as a langchain Document in the same shape "
    "Retriever.retrieve returns.",
    "Inter-chunk rhetorical graph (GraphBuilder) bypassed via the released "
    "pipeline's own supported configuration (PipelineModules(use_graph="
    "False) / graph=None code path): the graph is defined over ordered "
    "pairs of distinct chunks and is empty by construction with one chunk.",
    "Backbone substituted: vLLM beam search (beam_width 3) over local "
    "Llama-3.3-70B replaced by a single OpenAI chat completion "
    "(gpt-4o-mini, temperature=0, seed=13).",
]

# The fixed recovery query given to the pipeline for every case.
# Disco-RAG is query-conditioned generation; this query states the
# recovery task once, identically for all 38 cases.
RECOVERY_QUERY = (
    "Decompose the regulatory source text in the retrieved chunk into a "
    "set of atomic, self-contained claims suitable for downstream "
    "formalization into logic. Each claim must express exactly one "
    "assertion, and every condition, exception, or concession that "
    "governs a requirement in the source text must remain attached to "
    "the requirement it governs -- no claim may assert a governed "
    "requirement unconditionally. Output each claim on its own line, "
    "starting with '- '."
)


class ChatOpenAIBackbone(BaseChatModel):
    """Minimal langchain BaseChatModel over the OpenAI chat API, standing
    in for the published ChatVllmBeamSearch backbone (see module
    docstring). Exposes `model_name` because the released RstParser
    reads it for its per-model output cache.
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
                    "-- arm 1 cannot run (and will not silently no-op)."
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


_CLAIM_LINE_RE = re.compile(r"^(?:[-*•]|\d+[.)])\s+(.*)$")


def parse_answer_claims(answer_text):
    """Parse the generator's free-text ANSWER into a claim list: one claim
    per '- ' / numbered line. If the model returned prose with no list
    structure, the whole answer is kept as ONE claim -- that is what a
    downstream reader would see, so it is what gets judged. Returns
    (claims, parse_mode) where parse_mode is 'lines' or 'whole_answer'.
    """
    claims = []
    for line in (answer_text or "").splitlines():
        m = _CLAIM_LINE_RE.match(line.strip())
        if m and m.group(1).strip():
            claims.append(m.group(1).strip())
    if claims:
        return claims, "lines"
    if (answer_text or "").strip():
        return [answer_text.strip()], "whole_answer"
    return [], "empty"


class DiscoRagSingleSentenceRecovery:
    """Composes the released Disco-RAG stages for one-sentence recovery,
    mirroring DiscoRagPipeline.build_structures/run (src/pipeline.py)
    with retrieval bypassed and use_graph=False (see module docstring).
    """

    def __init__(self, backbone=None):
        self.backbone = backbone or ChatOpenAIBackbone()
        # REAL vendor classes; the substituted backbone only changes what
        # `prompt | llm | StrOutputParser()` calls under the hood.
        self.parser = RstParser(self.backbone)
        self.planner = Planner(self.backbone)
        self.generator = DiscoRagGenerator(self.backbone)

    def recover(self, sentence):
        """Runs RST parse -> plan -> generate on one source sentence.
        Returns a dict with the raw intermediates (for audit) and the
        parsed recovered claim list. Raises on LLM failure -- callers
        must record the error loudly, not swallow it.
        """
        doc = Document(page_content=sentence, metadata={"chunk_id": 0})
        # Stage 1 (REAL vendor code): zero-shot RST-tree construction
        # over the source text.
        trees = self.parser.parse_chunks([doc])
        # Stage 2 (REAL vendor code): discourse-aware planning blueprint.
        # graph=None is the released pipeline's own use_graph=False path.
        plan = self.planner.plan(RECOVERY_QUERY, [doc], trees, None)
        # Stage 3 (REAL vendor code): plan-conditioned generation.
        answer = self.generator.generate(RECOVERY_QUERY, [doc], trees, None, plan)
        claims, parse_mode = parse_answer_claims(answer)
        tree = trees[0] if trees else None
        return {
            "rst_tree_serialized": tree.serialize() if tree else None,
            "rst_tree_raw": tree.raw if tree else None,
            "rst_edu_count": len(tree.edus) if tree else 0,
            "rst_relation_count": len(tree.relations) if tree else 0,
            "plan_text": plan.text,
            "answer_raw": answer,
            "claims": claims,
            "answer_parse_mode": parse_mode,
        }
