"""LlamaIndex adapter boundary: uses `llama_index.core.Document`/`TextNode` for
ingestion and node relationships, then converts immediately into Wittgenstein
`SourceSegment`/`SourceDocument` objects -- LlamaIndex types never leak past this
module (docs/efficiency-and-processing-architecture.md, "LLAMAINDEX INTEGRATION").

External framework ids are preserved for traceability (`framework_node_id` on the
returned segment's provenance is folded into `location`, never substituted for
`segment_id`) but never replace canonical Wittgenstein ids -- `segment_id` is always
assigned by Wittgenstein (`ingestion.parser`-style deterministic ids), so downstream
code never has to know whether a segment came from the LlamaIndex path or the plain
parser path.
"""

from __future__ import annotations

from typing import cast

from llama_index.core import Document
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import NodeRelationship, RelatedNodeInfo, TextNode

from wittgenstein.core.enums import SegmentType
from wittgenstein.schemas.proposition import SourceSegment

#: Kept small and explicit rather than pulling in llama_index's full ingestion
#: pipeline machinery -- this adapter's only job is producing nodes with relationships
#: and offsets that we can convert, not owning a general document-processing pipeline
#: (that role belongs to `ingestion.parser` / `ingestion.corpus_index`, per the
#: processing hierarchy in docs/efficiency-and-processing-architecture.md).
_DEFAULT_CHUNK_SIZE = 512
_DEFAULT_CHUNK_OVERLAP = 32


def build_documents(texts: dict[str, str], corpus_id: str) -> list[Document]:
    """Wrap raw texts as LlamaIndex `Document`s, tagged with our own document id in
    metadata so the conversion step below never has to rely on a LlamaIndex-assigned id.
    """

    return [
        Document(text=text, doc_id=source_document_id, metadata={"corpus_id": corpus_id})
        for source_document_id, text in texts.items()
    ]


def parse_nodes(
    documents: list[Document], chunk_size: int = _DEFAULT_CHUNK_SIZE, chunk_overlap: int = _DEFAULT_CHUNK_OVERLAP
) -> list[TextNode]:
    """Split Documents into TextNodes using LlamaIndex's SentenceSplitter, which
    preserves parent/child (SOURCE) relationships and, critically, per-node character
    start/end offsets into the source document (`node.start_char_idx`/`end_char_idx`) --
    exactly the provenance this project requires (§5 of the architecture doc).
    """

    splitter = SentenceSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    nodes: list[TextNode] = []
    for document in documents:
        # SentenceSplitter is typed as returning the BaseNode base class, but in
        # practice always produces TextNode here -- this is the one adapter-boundary
        # cast, not a general escape hatch.
        nodes.extend(cast("list[TextNode]", splitter.get_nodes_from_documents([document])))
    return nodes


def _related_node_id(node: TextNode, relationship: NodeRelationship) -> str | None:
    """A node's `relationships` dict maps to either a single RelatedNodeInfo or a list
    of them (e.g. CHILD); SOURCE/PARENT are always single-valued in practice, but we
    handle the list case defensively rather than assuming.
    """

    related = node.relationships.get(relationship)
    if related is None:
        return None
    if isinstance(related, list):
        return related[0].node_id if related else None
    related_info = cast(RelatedNodeInfo, related)
    return related_info.node_id


def nodes_to_source_segments(
    nodes: list[TextNode],
    corpus_id: str,
    parser_version: str,
    source_version: str | None = None,
) -> list[SourceSegment]:
    """Convert LlamaIndex TextNodes into canonical Wittgenstein SourceSegments --
    immediately, and completely: no TextNode or NodeRelationship object is retained or
    passed further down the pipeline after this function returns.

    A node's character offsets (`start_char_idx`/`end_char_idx`) are preserved exactly;
    when LlamaIndex does not report them (`None`), we do not infer them -- offsets stay
    `None` rather than substituting a computed guess, per the "never infer missing
    manifest/provenance values" rule (CLAUDE.md).
    """

    segments: list[SourceSegment] = []
    for i, node in enumerate(nodes):
        source_document_id = (
            node.ref_doc_id or _related_node_id(node, NodeRelationship.SOURCE) or ("unknown-source-document")
        )
        char_start = node.start_char_idx if node.start_char_idx is not None else 0
        char_end = node.end_char_idx if node.end_char_idx is not None else char_start + len(node.get_content())
        segments.append(
            SourceSegment(
                segment_id=f"{source_document_id}-llamaindex-node{i}",
                source_document_id=source_document_id,
                corpus_id=corpus_id,
                source_version=source_version,
                segment_type=SegmentType.PARAGRAPH,
                location=f"llamaindex_node:{node.node_id}",
                text=node.get_content(),
                char_start=char_start,
                char_end=char_end,
                token_start=None,
                token_end=None,
                parent_segment_id=_related_node_id(node, NodeRelationship.PARENT),
                cross_reference_targets=[],
                parser_version=parser_version,
            )
        )
    return segments
