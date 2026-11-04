"""Render a Markdown dossier for one failure mechanism.

The dossier is the single human-readable artifact meant to answer "what do we
actually know about this mechanism, and what don't we know yet" -- it always
includes an explicit open-evidence-gaps section rather than only the positive case.
"""

from __future__ import annotations

from wittgenstein.registry.repository import Registry


def render_dossier(registry: Registry, mechanism_id: str) -> str:
    mechanism = registry.mechanism(mechanism_id)
    evidence = registry.evidence_for_mechanism(mechanism_id)
    gates = registry.gates_for_mechanism(mechanism_id)
    triggers = registry.triggers_for_mechanism(mechanism_id)
    review_actions = [ra for ra in registry.review_actions.values() if mechanism_id in ra.applicable_mechanism_ids]

    lines: list[str] = []
    lines.append(f"# {mechanism.canonical_name}")
    lines.append("")
    lines.append(f"**ID**: `{mechanism.id}`  ")
    lines.append(f"**Epistemic status**: `{mechanism.epistemic_status.value}`  ")
    lines.append(f"**Default evidence grade**: `{mechanism.default_evidence_grade.value}`  ")
    lines.append(f"**Default activation policy**: `{mechanism.default_activation_policy.value}`  ")
    lines.append(f"**Pipeline stage**: `{mechanism.pipeline_stage.value}`  ")
    lines.append(f"**Failure object**: `{mechanism.failure_object.value}`  ")
    lines.append(f"**Registry version**: {mechanism.registry_version}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(mechanism.short_description.strip())
    lines.append("")
    lines.append("## Causal claim (as stated)")
    lines.append("")
    lines.append(mechanism.causal_claim.strip())
    lines.append("")
    lines.append("## Necessary causal ingredients")
    lines.append("")
    for item in mechanism.necessary_causal_ingredients:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## Known boundary conditions")
    lines.append("")
    for item in mechanism.known_boundary_conditions:
        lines.append(f"- {item}")
    lines.append("")

    lines.append("## Supporting and conflicting evidence records")
    lines.append("")
    if not evidence:
        lines.append("_No evidence records linked yet. This is an open evidence gap._")
    supporting = [e for e in evidence if e.direction.value == "supports"]
    conflicting = [e for e in evidence if e.direction.value in ("refutes", "mixed")]
    non_committal = [e for e in evidence if e.direction.value == "null"]
    if evidence:
        lines.append(
            f"{len(supporting)} supporting, {len(conflicting)} refuting/mixed, "
            f"{len(non_committal)} non-committal (direction=null)."
        )
        lines.append("")
    for e in evidence:
        lines.append(f"### {e.id} ({e.verification_status.value}, direction={e.direction.value})")
        lines.append("")
        lines.append(f"- **Citation**: {e.full_citation.strip()}")
        lines.append(f"- **Venue / year**: {e.venue} / {e.publication_year}")
        lines.append(f"- **Peer review status**: {e.peer_review_status.value}")
        lines.append(f"- **Study type**: {e.study_type.value}")
        lines.append(f"- **Evidence grade**: {e.evidence_grade.value}")
        lines.append(f'- **Quote** ({e.quote_location.strip()}): "{e.exact_quote.strip()}"')
        lines.append(f"- **Task**: {e.task.strip()}")
        lines.append(f"- **Dataset/corpus**: {e.dataset_or_corpus.strip()}")
        lines.append(f"- **Intervention/comparison**: {e.intervention_or_comparison.strip()}")
        effect_text = e.effect_size_text.strip() if e.effect_size_text else "not yet extracted"
        lines.append(f"- **Observed effect**: {effect_text}")
        if e.statistical_evidence:
            lines.append(f"- **Statistical evidence**: {e.statistical_evidence.strip()}")
        known_envelope = e.experimental_envelope.known_fields()
        if known_envelope:
            lines.append("- **Experimental envelope** (known dimensions only):")
            for field_name, value in known_envelope.items():
                lines.append(f"  - `{field_name}`: {value}")
        else:
            lines.append("- **Experimental envelope**: no dimensions recorded yet.")
        lines.append(f"- **Stated limitations**: {e.stated_limitations.strip()}")
        lines.append("")

    lines.append("## Manifest gates")
    lines.append("")
    for g in gates:
        lines.append(f"### {g.id}")
        lines.append("")
        lines.append(g.description.strip())
        if g.required_manifest_predicates:
            lines.append("")
            lines.append("Required:")
            for p in g.required_manifest_predicates:
                lines.append(f"- {p.description} (`{p.field_path} {p.operator.value} {p.expected_value}`)")
        if g.disqualifying_predicates:
            lines.append("")
            lines.append("Disqualifying:")
            for p in g.disqualifying_predicates:
                lines.append(f"- {p.description} (`{p.field_path} {p.operator.value} {p.expected_value}`)")
        if g.strengthening_predicates:
            lines.append("")
            lines.append("Strengthening (informational only):")
            for p in g.strengthening_predicates:
                lines.append(f"- {p.description}")
        lines.append("")
        lines.append(f"_Unknown-data behavior_: {g.unknown_manifest_behavior}")
        lines.append("")

    lines.append("## Trace triggers")
    lines.append("")
    for t in triggers:
        lines.append(f"### {t.id}")
        lines.append("")
        lines.append(t.description.strip())
        lines.append("")
        lines.append(f"Causal claim permitted from this trigger alone: **{t.causal_claim_permitted}**")
        lines.append("")

    lines.append("## Allowed vs. prohibited product language")
    lines.append("")
    lines.append(f"- **Allowed**: language consistent with `{mechanism.epistemic_status.value}`.")
    lines.append(
        "- **Prohibited**: presenting this mechanism as a confirmed cause of any specific answer "
        "error unless a causal evidence record or local causal validation is directly linked."
    )
    lines.append("")

    lines.append("## Reviewer actions")
    lines.append("")
    for ra in review_actions:
        lines.append(f"- **{ra.id}**: {ra.prompt_text.strip()}")
    lines.append("")

    lines.append("## Open evidence gaps")
    lines.append("")
    gaps = [e for e in evidence if e.is_unverified_or_incomplete()]
    if not evidence:
        lines.append("- No primary source has been confirmed and extracted yet.")
    elif gaps:
        for gap in gaps:
            lines.append(f"- {gap.id}: {gap.stated_limitations.strip()}")
    else:
        lines.append("- None currently open; all linked evidence records are verified.")
    lines.append("")

    return "\n".join(lines)
