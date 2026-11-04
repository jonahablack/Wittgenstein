"""Helpers for turning a decomposed CorpusProfile into envelope-comparable summaries.

Deliberately does not produce a single "complexity score" -- see CorpusProfile's
docstring. `document_structure_summary` renders a short, honest, human-readable
summary string from the individual density dimensions instead.
"""

from __future__ import annotations

from wittgenstein.schemas.corpus_profile import CorpusProfile


def document_structure_summary(profile: CorpusProfile) -> str | None:
    parts: list[str] = []
    if profile.table_density is not None:
        parts.append(f"table_density={profile.table_density:.2f}")
    if profile.list_density is not None:
        parts.append(f"list_density={profile.list_density:.2f}")
    if profile.cross_reference_density is not None:
        parts.append(f"cross_reference_density={profile.cross_reference_density:.2f}")
    if profile.hierarchy_depth_distribution is not None:
        parts.append(f"hierarchy_depth_p50={profile.hierarchy_depth_distribution.p50}")
    return ", ".join(parts) if parts else None
