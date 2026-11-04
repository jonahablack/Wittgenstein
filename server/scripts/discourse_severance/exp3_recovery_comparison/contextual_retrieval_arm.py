"""Arm 5 (new, added post-hoc to Experiment 3): Anthropic's published
Contextual Retrieval context-injection method, applied to single-
sentence discourse-relation recovery.

ATTRIBUTION (read before quoting any arm-5 number): the prompt used
below is Anthropic's own published Contextual Retrieval template,
quoted verbatim from https://www.anthropic.com/news/contextual-retrieval
(also mirrored in anthropic-cookbook/skills/contextual-embeddings):

    <document>
    {{WHOLE_DOCUMENT}}
    </document>
    Here is the chunk we want to situate within the whole document
    <chunk>
    {{CHUNK_CONTENT}}
    </chunk>
    Please give a short succinct context to situate this chunk within
    the overall document for the purposes of improving search
    retrieval of the chunk. Answer only with the succinct context and
    nothing else.

This experiment only borrows the CONTEXT-GENERATION half of Contextual
Retrieval (the LLM call that produces the situating sentence). The
retrieval-ranking half (embedding/BM25 the contextualized chunk and
measuring retrieval quality) is NOT exercised -- there is nothing to
retrieve in a single fixed-sentence recovery task. What this arm
measures is narrower and specific to this experiment: does the
generated situating sentence, prepended to the atomized claims, restore
the severed Condition/Exception/Concession relation for a reader who
sees only [context] + [claims]?

Backbone: gpt-4o-mini, temperature=0, seed=13 -- this project's
standard model for every other LLM call (server/api_call.py), NOT one
of Anthropic's own Claude models. The PROMPT is Anthropic's published
method; the model executing it is this project's standard backbone --
the same kind of substitution disco_rag_adapter.py documents for arm 1
(published method, substituted backbone), stated explicitly here so
arm-5 numbers are never mistaken for a Claude-backboned reproduction.

Output format is a deliberate, documented exception to this project's
usual "return strict JSON" convention: Anthropic's template itself ends
with "Answer only with the succinct context and nothing else", i.e. it
specifies plain text, not JSON. Following the published prompt
VERBATIM (per this task's instruction) means keeping that plain-text
contract rather than bolting on a JSON wrapper the published method
does not use.

--- Document-context resolution (part vs section) ------------------

"The full source document context you have available" is resolved at
CFR SECTION granularity (an eCFR <DIV8 TYPE="SECTION"> element), not
whole-PART granularity. This is a documented design decision, not a
silent shortcut: 29 CFR Part 1910's raw XML is 6.7MB (~1.6M
characters, comfortably over 128K gpt-4o-mini context tokens even
before accounting for the prompt/chunk/response) -- there is no way to
hand the model "the whole part" as one document for the OSHA cases.
Section is the finest granularity eCFR's own hierarchy exposes and the
one CFR sentences themselves cite internally (e.g. "paragraph (a) of
this section", "§ 208.20 of this chapter"), so it is the natural
reading of "part/section" that is actually usable as an LLM context
window.

Section resolution method: for each of the 38 eval sentences, the
verbatim `sentence` field is located by exact substring search (offset
`full_text.find(sentence)`) inside an INDEPENDENTLY reconstructed
version of the part's full prose text -- same prose-extraction rule as
corpus.strip_xml_to_text (concatenate every HEAD/HED/P/PSPACE element's
text, in document order, "\n"-joined) but additionally tagging each
extracted line with its enclosing DIV8 SECTION as it walks the tree.
Lines with no DIV8 ancestor (subpart/part headings that fall between
sections) are forward-filled to the NEXT section they introduce. The
offset is then mapped back to the line (and hence the section) it
falls in.

This resolves uniquely for all 38 cases (verified before this arm was
run against the real API). Two structural edge cases came up and are
resolved -- not silently guessed -- by that same mechanical rule:

  1. cfr21p201:1091's saved `sentence` field is itself a two-line
     structural transition ("Subpart D—Exemptions From Adequate
     Directions for Use\n§ 201.100 Prescription drugs for human
     use.") with no DIV8 ancestor of its own -- the forward-fill rule
     attributes it to 201.100, the section it introduces, which is
     also the only sensible reading of "what section is this about".
  2. cfr21p201:500's saved `sentence` field is a verbatim boilerplate
     line ("No overall differences in safety or effectiveness were
     observed between these subjects and younger subjects...") that
     recurs verbatim in TWO sections (201.57 and 201.80). `str.find`
     returns the FIRST occurrence, i.e. 201.57 -- which is also
     provably the occurrence the original experiment's sentence_index
     refers to: corpus.segment_and_filter dedupes exact-duplicate
     sentence strings by keeping only the first-seen (idx, sentence)
     pair when iterating sentences in document order, so any surviving
     duplicate sentence in the eval set MUST be its earliest occurrence
     in the part. Section resolution here is therefore not an
     arbitrary tie-break; it matches the original pipeline's own
     indexing rule.

Raises RuntimeError (fail loud, no silent fallback -- repo convention)
if a sentence cannot be found verbatim in the reconstructed part text,
or resolves to no enclosing section at all.
"""

import os
import re
import sys
import threading
import xml.etree.ElementTree as ET

EXP3_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPT_DIR = os.path.dirname(EXP3_DIR)
SERVER_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from api_call import generate_response  # noqa: E402
from scripts.discourse_severance import corpus  # noqa: E402

# Same prose-bearing tag set as corpus.strip_xml_to_text -- reused by
# name (not re-derived) so this module's independent reconstruction of
# the part text stays byte-for-byte aligned with corpus.py's, which is
# what makes offset-based section lookup valid.
_PROSE_TAGS = {"HEAD", "HED", "P", "PSPACE"}

CONTEXTUAL_RETRIEVAL_SOURCE_URL = "https://www.anthropic.com/news/contextual-retrieval"

# Verbatim, for display/reproducibility logging only (the real prompt is
# assembled by build_context_prompt below via an f-string, not by
# .format()-ing this template, so stray braces in CFR text can never
# raise a KeyError).
CONTEXT_PROMPT_TEMPLATE_DISPLAY = (
    "<document>\n{{WHOLE_DOCUMENT}}\n</document>\n"
    "Here is the chunk we want to situate within the whole document\n"
    "<chunk>\n{{CHUNK_CONTENT}}\n</chunk>\n"
    "Please give a short succinct context to situate this chunk within "
    "the overall document for the purposes of improving search "
    "retrieval of the chunk. Answer only with the succinct context and "
    "nothing else."
)

CONTEXTUAL_RETRIEVAL_STATEMENT = (
    "Arm 5 uses Anthropic's published Contextual Retrieval prompt "
    "template verbatim (\"Please give a short succinct context to "
    "situate this chunk within the overall document for the purposes "
    "of improving search retrieval of the chunk. Answer only with the "
    f"succinct context and nothing else.\", {CONTEXTUAL_RETRIEVAL_SOURCE_URL}), "
    "called once per case with gpt-4o-mini (this project's standard "
    "model/temperature/seed -- NOT one of Anthropic's own Claude "
    "models; the PROMPT is Anthropic's published method, the backbone "
    "executing it is this project's standard backbone, the same kind "
    "of substitution disco_rag_adapter.py documents for arm 1). Only "
    "the context-GENERATION half of Contextual Retrieval is exercised; "
    "the retrieval-ranking half (embedding/BM25 the contextualized "
    "chunk) is not, since there is nothing to retrieve in a "
    "single-sentence recovery task."
)

SECTION_RESOLUTION_STATEMENT = (
    "\"Document\" = the single CFR SECTION (eCFR <DIV8 TYPE=\"SECTION\">) "
    "the sentence is drawn from, not the whole CFR PART: 29 CFR Part "
    "1910's raw XML is 6.7MB (~1.6M characters), far beyond gpt-4o-mini's "
    "128K-token context window, so \"the full source document context\" "
    "is resolved at section granularity -- the finest level eCFR's own "
    "XML hierarchy exposes and the level CFR sentences cite internally "
    "(e.g. \"paragraph (a) of this section\"). Each of the 38 sentences "
    "was mapped to its enclosing section by finding the verbatim "
    "sentence text's character offset in an independently reconstructed "
    "full-part text (document order, same prose extraction rule as "
    "corpus.strip_xml_to_text) and reading off which section that "
    "offset falls under; this resolved uniquely for all 38 cases. See "
    "this module's docstring for the two structural edge cases "
    "encountered (a heading-transition sentence; one exact-duplicate "
    "boilerplate sentence) and how each was resolved by the same "
    "mechanical rule, not a guess."
)


def _norm_ws(text):
    return re.sub(r"\s+", " ", text).strip()


_PART_INDEX_CACHE = {}
_PART_INDEX_LOCK = threading.Lock()


def _build_part_index(title, part):
    """Reconstructs one CFR part's full prose text plus, for every
    extracted line, its enclosing DIV8 SECTION citation (forward-filled
    across orphan heading lines -- see module docstring) and its
    character-offset span within the joined text.

    Returns (full_text, lines, line_sections, offsets).
    """
    xml_text, _ = corpus.fetch_cfr_part_xml(title, part)
    root = ET.fromstring(xml_text)
    parent = {child: p for p in root.iter() for child in p}

    def _enclosing_section(elem):
        cur = elem
        while cur in parent:
            cur = parent[cur]
            if cur.tag == "DIV8" and cur.get("TYPE") == "SECTION":
                return f"{title} CFR {cur.get('N')}"
        return None

    lines = []
    line_sections = []
    for elem in root.iter():
        if elem.tag in _PROSE_TAGS:
            text = _norm_ws("".join(elem.itertext()))
            if text:
                lines.append(text)
                line_sections.append(_enclosing_section(elem))

    # Forward-fill orphan (no-DIV8-ancestor) lines to the NEXT known
    # section -- a subpart/part heading transitionally "belongs" to the
    # section it introduces.
    last = None
    for i in range(len(line_sections) - 1, -1, -1):
        if line_sections[i] is None:
            line_sections[i] = last
        else:
            last = line_sections[i]

    offsets = []
    pos = 0
    for line in lines:
        offsets.append((pos, pos + len(line)))
        pos += len(line) + 1  # +1 for the "\n" joiner, matching corpus.py exactly
    full_text = "\n".join(lines)
    return full_text, lines, line_sections, offsets


def _get_part_index(title, part):
    key = (title, part)
    with _PART_INDEX_LOCK:
        if key not in _PART_INDEX_CACHE:
            _PART_INDEX_CACHE[key] = _build_part_index(title, part)
        return _PART_INDEX_CACHE[key]


def prewarm_part_indexes():
    """Builds and caches both parts' indexes up front (a couple of
    seconds, pure local XML parsing) so the parallel per-case map below
    only ever hits a populated cache -- avoids redundant re-parsing of
    the 6.7MB Part 1910 XML across worker threads."""
    for spec in corpus.CFR_PARTS:
        _get_part_index(spec["title"], spec["part"])


def resolve_section_context(part_label, sentence):
    """Returns {"citation": str, "section_text": str, "char_len": int}
    for the CFR section `sentence` (verbatim) is drawn from within
    `part_label`. Raises RuntimeError -- never returns a guessed or
    partial result -- if the sentence cannot be found verbatim in the
    reconstructed part text, or resolves to no section at all.
    """
    spec = next((p for p in corpus.CFR_PARTS if p["label"] == part_label), None)
    if spec is None:
        raise RuntimeError(
            f"FATAL: part_label {part_label!r} is not one of corpus.CFR_PARTS "
            "-- cannot resolve a document context for the Contextual "
            "Retrieval arm."
        )
    full_text, lines, line_sections, offsets = _get_part_index(spec["title"], spec["part"])
    idx = full_text.find(sentence)
    if idx == -1:
        raise RuntimeError(
            f"FATAL: sentence for part {part_label!r} was not found verbatim "
            "in the reconstructed part text -- cannot resolve its enclosing "
            "CFR section. Refusing to guess or fall back to the whole part."
        )
    citation = None
    for (start, end), sec in zip(offsets, line_sections):
        if start <= idx < end:
            citation = sec
            break
    if citation is None:
        citation = line_sections[-1] if line_sections else None
    if citation is None:
        raise RuntimeError(
            f"FATAL: sentence for part {part_label!r} resolved to no "
            "enclosing CFR section at all -- cannot build a document "
            "context."
        )
    section_text = "\n".join(
        line for line, sec in zip(lines, line_sections) if sec == citation
    )
    return {"citation": citation, "section_text": section_text,
            "char_len": len(section_text)}


def build_context_prompt(document_text, chunk_content):
    """Anthropic's published Contextual Retrieval prompt, assembled via
    f-string (not .format()) so stray "{"/"}" characters anywhere in
    CFR text can never raise a KeyError. Text and structure match
    CONTEXT_PROMPT_TEMPLATE_DISPLAY exactly, placeholders substituted.
    """
    return (
        "<document>\n"
        f"{document_text}\n"
        "</document>\n"
        "Here is the chunk we want to situate within the whole document\n"
        "<chunk>\n"
        f"{chunk_content}\n"
        "</chunk>\n"
        "Please give a short succinct context to situate this chunk "
        "within the overall document for the purposes of improving "
        "search retrieval of the chunk. Answer only with the succinct "
        "context and nothing else."
    )


def generate_context(document_text, claims, model=None):
    """One LLM call: Anthropic's published context-generation prompt,
    chunk = the atomized claims (bullet-listed, this project's standard
    claims_block style).

    Returns (context_text_or_None, error). Plain text response, per
    the published prompt's own "answer only with the succinct context"
    instruction -- NOT JSON (see module docstring). On any call failure
    the text is None and `error` names the failure; callers must record
    it loudly, never substitute silently.
    """
    chunk_content = "\n".join(f"- {c}" for c in claims) or "(no claims produced)"
    prompt = build_context_prompt(document_text, chunk_content)
    response = generate_response(prompt, model=model)
    if not response or not hasattr(response, "content") or response.content is None:
        return None, "no_response"
    text = response.content.strip()
    if not text:
        return None, "empty_response"
    return text, None
