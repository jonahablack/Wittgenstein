"""Plumbing tests for server/scripts/external_robustness_check.py.

These run the script's classifier-invocation logic on a tiny INLINE
SYNTHETIC sample only -- no network, no report files, no external data.
They prove that the external robustness check would classify and
aggregate correctly, independent of whether the FactoidWiki download is
reachable at test time. (The synthetic sentences here are hand-written
fixtures, unmistakably NOT external validation data.)
"""

from scripts.external_robustness_check import (
    CLAIM_LEVEL_FLAG_TYPES,
    SELF_TEST_PROPOSITIONS,
    classify_proposition,
    classify_propositions,
    extract_proposition,
    pick_examples,
)


def _factoidwiki_style_record():
    """Shape-faithful synthetic copy of a FactoidWiki record: contents is
    '<title>\n<proposition>' and content_span points at the proposition."""
    title = "Synthetic Test Page"
    prop = "The country faces the Pacific Ocean."
    contents = f"{title}\n{prop}"
    start = len(title) + 1
    return {
        "id": "synthetic-0000",
        "contents": contents,
        "metadata": {
            "title_span": [0, len(title)],
            "section_span": [len(title), len(title)],
            "content_span": [start, start + len(prop)],
        },
    }


def test_extract_proposition_uses_content_span():
    rec = _factoidwiki_style_record()
    assert extract_proposition(rec) == "The country faces the Pacific Ocean."


def test_extract_proposition_falls_back_without_span():
    rec = {"contents": "Title\nA plain proposition.", "metadata": {}}
    assert extract_proposition(rec) == "A plain proposition."


def test_classify_proposition_runs_claim_level_detectors_only():
    """A strong-modal claim with formal='' must NOT produce a
    modal_mismatch flag: the script passes formal_mode='logic', in which
    detect_modal_mismatch is a documented no-op (condition_satellite and
    concession_satellite are no-ops here for the same reason). Only the
    three formal-string-independent claim-level linguistic detectors can
    fire on external propositions."""
    out = classify_proposition(
        "All vendors must not share data unless the client consents "
        "and the policy permits it, as noted above."
    )
    types = {f["type"] for f in out["flags"]}
    assert "modal_mismatch" not in types
    assert types <= set(CLAIM_LEVEL_FLAG_TYPES)
    assert "negation_scope" in types
    assert "cross_reference" in types
    assert out["tier"] in {"Low", "Medium", "High"}


def test_classify_proposition_clean_text_has_no_flags():
    out = classify_proposition("Paris is the capital of France.")
    assert out["flags"] == []
    assert out["tier"] == "Low"


def test_classify_propositions_aggregates_synthetic_sample():
    items = [
        (f"synthetic-{i}", text)
        for i, text in enumerate(SELF_TEST_PROPOSITIONS)
    ]
    agg = classify_propositions(items)

    assert agg["total"] == len(SELF_TEST_PROPOSITIONS)
    # The synthetic sample is built so every claim-level detector fires
    # at least once somewhere, and the clean control sentence does not.
    for ftype in CLAIM_LEVEL_FLAG_TYPES:
        assert agg["flag_counts"].get(ftype, 0) >= 1, ftype
    assert agg["flagged"] == agg["total"] - 1  # only the control is clean
    assert sum(agg["tier_counts"].values()) == agg["total"]
    assert set(agg["tier_counts"]) <= {"Low", "Medium", "High"}

    # Examples are drawn from the results with reasons attached.
    examples = pick_examples(agg["results"], per_type=1)
    assert set(examples) == set(agg["flag_counts"])
    for exs in examples.values():
        for ex in exs:
            assert ex["reason"]
            assert ex["id"].startswith("synthetic-")

# test_count_month_may_hedges_distinguishes_month_from_modal was removed
# alongside detect_hedges and count_month_may_hedges in the RST-grounded
# classifier rebuild: it tested a false-positive pattern (capitalized
# month "May" colliding with modal "may") specific to the now-retired
# hedge detector, which no longer exists.
