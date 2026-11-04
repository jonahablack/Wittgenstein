"""Read-only, deterministic baseline-versus-post-fix cross-reference comparison --
docs/eu-ai-act-cross-reference-annotation-protocol.md,
docs/eu-ai-act-cross-reference-comparison-template.md.

Never re-runs the pipeline, never calls `import_answer`/`construct_evidence_set`/
`detect_cross_reference_markers`, never writes to the baseline or post-fix directories
it reads from, and never fills a human-judgment label -- it only reads two sets of
already-generated `<case_id>.diagnostic.json` files plus the cases file they came
from, and reports differences in already-computed, machine-observable fields.

Every field this module writes is a **parser output observation**, never a legal
interpretation, a necessity judgment, or an answer-support claim -- see the fixed
`DISCLAIMER` list, always attached to the generated worksheet.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from wittgenstein.schemas.smoke_test import SmokeTestCaseFile

#: Attached verbatim to every generated worksheet -- never edited per-run.
DISCLAIMER = [
    "This worksheet records parser output, not legal interpretation.",
    "Target resolution is structural (location-text or document-id pattern matching), never semantic.",
    "Target presence does not establish that a reference is necessary to interpret the claim.",
    "Target presence does not establish that the target supports, contradicts, or resolves the answer.",
    "Human annotation is required for usefulness, necessity, false reassurance, unnecessary escalation, "
    "and interpretation -- none of those judgments are made or inferred by this worksheet.",
]

#: Fields compared for "did anything outside cross-reference detection change" --
#: deliberately excludes `cross_reference_markers` itself and the two fields expected
#: to legitimately vary run-to-run (processing_time_seconds; corpus_profile's
#: index_timestamp, if present).
_NON_CROSS_REFERENCE_FIELDS = (
    "retrieval_candidates",
    "selected_context_items",
    "packed_context_items",
    "omitted_context_items",
    "answer_claims",
    "answer_support_edges",
    "claim_evidence_comparisons",
    "evidence_sets",
    "evidence_set_metrics",
    "conflict_explanations",
    "size3_diagnostics",
    "risk_events",
)


def _load_case_diagnostic(directory: Path, case_id: str) -> dict | None:
    path = directory / f"{case_id}.diagnostic.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def _marker_key(marker: dict) -> str:
    """Identity for matching a marker across two runs -- `marker_text` only, never
    `reference_type`. A pre-fix baseline's markers were written before this fix added
    `reference_type` to the schema at all (the field is simply absent from that JSON),
    so keying on it would make every unchanged pre-existing marker look "new" purely
    because of a schema addition, not a detection change.
    """

    return marker["marker_text"]


def _flatten_markers(diagnostic_report: dict) -> list[dict]:
    return [m for markers in diagnostic_report.get("cross_reference_markers", {}).values() for m in markers]


def _deduplicated_markers(markers: list[dict]) -> list[dict]:
    """One entry per distinct `marker_text`, with an `occurrence_count` recording how
    many claim fragments in this case actually contained it -- the same citation
    repeated across several answer-claim fragments (e.g. one long answer split into
    several claims that each happen to mention "Annex III") is one logical finding,
    not several, but the repeat count is preserved rather than silently discarded.
    """

    by_text: dict[str, dict] = {}
    counts: dict[str, int] = {}
    for marker in markers:
        key = _marker_key(marker)
        counts[key] = counts.get(key, 0) + 1
        by_text.setdefault(key, marker)
    return [{**by_text[key], "occurrence_count": counts[key]} for key in by_text]


def _strip_volatile(value: dict, *, strip_evidence_set_ids: bool = True) -> dict:
    """Removes fields already known to legitimately vary run-to-run (uuids, wall-clock
    timing) before an equality comparison -- mirrors the existing determinism-test
    normalization pattern in tests/integration/test_real_trace_smoke_cases.py, applied
    here for the same reason: a difference in a uuid or a timestamp is not a real
    output difference.
    """

    result = json.loads(json.dumps(value))  # deep copy via round-trip, avoids mutating the input
    if isinstance(result, dict):
        result.pop("construction_latency_seconds", None)
        if strip_evidence_set_ids:
            result.pop("evidence_set_id", None)
    return result


def _non_cross_reference_diff_fields(baseline: dict, post_fix: dict) -> list[str]:
    changed = []
    for field_name in _NON_CROSS_REFERENCE_FIELDS:
        base_value = baseline.get(field_name)
        post_value = post_fix.get(field_name)
        if field_name in ("evidence_sets",) or field_name == "evidence_set_metrics":
            base_value = [_strip_volatile(v) for v in (base_value or [])]
            post_value = [_strip_volatile(v) for v in (post_value or [])]
        elif field_name == "claim_evidence_comparisons":
            base_value = [{k: v for k, v in item.items() if k != "comparison_id"} for item in (base_value or [])]
            post_value = [{k: v for k, v in item.items() if k != "comparison_id"} for item in (post_value or [])]
        elif field_name == "risk_events":
            base_value = [{k: v for k, v in item.items() if k != "risk_event_id"} for item in (base_value or [])]
            post_value = [{k: v for k, v in item.items() if k != "risk_event_id"} for item in (post_value or [])]
        if base_value != post_value:
            changed.append(field_name)
    return changed


def _compare_case(
    case_id: str,
    case_metadata: dict | None,
    baseline: dict | None,
    post_fix: dict | None,
) -> dict:
    entry: dict = {"case_id": case_id}

    if case_metadata is not None:
        entry["query"] = case_metadata["query"]
        entry["answer_origin"] = case_metadata["answer_source_method"]
        entry["expected_evidence_locations"] = case_metadata["expected_evidence_locations"]
    else:
        entry["query"] = None
        entry["answer_origin"] = None
        entry["expected_evidence_locations"] = []
        entry["note"] = "Case not found in the supplied cases file -- query/answer_origin unavailable."

    entry["present_in_baseline"] = baseline is not None
    entry["present_in_post_fix"] = post_fix is not None
    if baseline is None or post_fix is None:
        entry["note"] = entry.get("note", "") + " Case missing from one of the two output directories."
        return entry

    baseline_markers = _deduplicated_markers(_flatten_markers(baseline))
    post_fix_markers = _deduplicated_markers(_flatten_markers(post_fix))
    baseline_by_key = {_marker_key(m): m for m in baseline_markers}
    post_fix_by_key = {_marker_key(m): m for m in post_fix_markers}

    newly_detected = [post_fix_by_key[k] for k in post_fix_by_key if k not in baseline_by_key]
    changed_states = [
        {
            "marker_text": key,
            "reference_type": post_fix_by_key[key].get("reference_type"),
            "baseline_target_state": baseline_by_key[key]["target_state"],
            "post_fix_target_state": post_fix_by_key[key]["target_state"],
        }
        for key in (set(baseline_by_key) & set(post_fix_by_key))
        if baseline_by_key[key]["target_state"] != post_fix_by_key[key]["target_state"]
    ]

    def _summarize(m: dict) -> dict:
        return {
            "marker_text": m["marker_text"],
            "reference_type": m.get("reference_type"),
            "target_identifier": m.get("target_identifier"),
            "target_state": m["target_state"],
            "extraction_method": m.get("extraction_method"),
            "extraction_confidence": m.get("extraction_confidence"),
            "warning": m.get("warning"),
            "occurrence_count": m.get("occurrence_count", 1),
        }

    entry.update(
        {
            "baseline_markers": [_summarize(m) for m in baseline_markers],
            "post_fix_markers": [_summarize(m) for m in post_fix_markers],
            "markers_newly_detected": [
                {"marker_text": m["marker_text"], "reference_type": m.get("reference_type")}
                for m in newly_detected
            ],
            "target_states_changed": changed_states,
            "relevant_answer_claims": [
                {"claim_id": c["claim_id"], "text": c["text"]} for c in post_fix.get("answer_claims", [])
            ],
            "linked_evidence_propositions": sorted(
                {
                    item["segment_id"]
                    for item in (post_fix.get("packed_context_items") or [])
                    if item.get("segment_id")
                }
            ),
            "evidence_set_statuses": [
                es.get("relationship_status") for es in (post_fix.get("evidence_sets") or [])
            ],
            "baseline_processing_time_seconds": baseline.get("processing_time_seconds"),
            "post_fix_processing_time_seconds": post_fix.get("processing_time_seconds"),
            "non_cross_reference_output_changed": bool(_non_cross_reference_diff_fields(baseline, post_fix)),
            "non_cross_reference_diff_fields": _non_cross_reference_diff_fields(baseline, post_fix),
        }
    )
    return entry


def generate_comparison_worksheet(baseline_dir: Path, post_fix_dir: Path, cases_path: Path) -> dict:
    """Builds the full comparison worksheet as a JSON-serializable dict. Read-only:
    opens files under `baseline_dir`/`post_fix_dir`/`cases_path` and never writes to
    any of them.
    """

    case_file = SmokeTestCaseFile.model_validate(json.loads(cases_path.read_text()))
    cases_by_id = {
        c.case_id: {
            "query": c.query,
            "answer_source_method": c.answer_source_method,
            "expected_evidence_locations": c.expected_evidence_locations,
        }
        for c in case_file.cases
    }

    baseline_ids = {p.stem[: -len(".diagnostic")] for p in baseline_dir.glob("*.diagnostic.json")}
    post_fix_ids = {p.stem[: -len(".diagnostic")] for p in post_fix_dir.glob("*.diagnostic.json")}
    all_case_ids = sorted(set(cases_by_id) | baseline_ids | post_fix_ids)

    cases = [
        _compare_case(
            case_id,
            cases_by_id.get(case_id),
            _load_case_diagnostic(baseline_dir, case_id),
            _load_case_diagnostic(post_fix_dir, case_id),
        )
        for case_id in all_case_ids
    ]

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "baseline_dir": str(baseline_dir),
        "post_fix_dir": str(post_fix_dir),
        "cases_file": str(cases_path),
        "disclaimer": DISCLAIMER,
        "case_ids": {
            "in_cases_file_only": sorted(set(cases_by_id) - baseline_ids - post_fix_ids),
            "baseline_only": sorted(baseline_ids - post_fix_ids),
            "post_fix_only": sorted(post_fix_ids - baseline_ids),
            "common": sorted(baseline_ids & post_fix_ids),
        },
        "cases": cases,
    }
