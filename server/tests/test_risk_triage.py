"""Regression tests for risk_triage.py, one per confirmed bug class
documented in that file's comments, plus coverage for the RST-grounded
Condition/Concession satellite detectors added in the hedge/nested-
conditional -> condition_satellite/concession_satellite rebuild:

  - word-boundary matching (no bare `in` substring checks)
  - shared modal-strength wordlists for source and formal strings
  - "no ___ than" idiom masking
  - detect_modal_mismatch no-op in symbolic-logic mode
  - segment-level detectors fire only when claim-level didn't
  - Unformalized tier for axioms with no formal representation
  - dedupe-for-scoring is a safe no-op now that _OVERLAPPING_GROUPS is empty
  - condition_satellite / concession_satellite: severed vs dropped vs
    present-no-flag, the spaCy well-formedness gate, and word-boundary
    safety on the new connective wordlists

detect_hedges and detect_nested_conditionals/detect_segment_nested_
conditionals were retired in that rebuild (superseded by
condition_satellite/concession_satellite and their segment fallbacks).
Their dedicated tests tested behavior that no longer exists and are
removed rather than adapted, per the project owner's explicit
instruction -- they are not ported forward in any form below.
"""

from components import risk_triage
from components.risk_triage import (
    _contains_phrase,
    _dedupe_for_scoring,
    _has_subject_and_finite_verb,
    _lower,
    _modal_strength,
    annotate_axiom,
    annotate_axioms,
    compute_tier,
    detect_concession_satellite,
    detect_condition_satellite,
    detect_modal_mismatch,
    detect_negation_scope,
    detect_segment_concession_satellite,
    detect_segment_condition_satellite,
    detect_segment_negation_scope,
    flag_claim,
)


def _flag_types(flags):
    return {f["type"] for f in flags}


# --- word-boundary matching ---------------------------------------------------


def test_no_does_not_match_nonprofit():
    assert not _contains_phrase("the nonprofit was founded in 1990", "no")
    # and at detector level: no negation flag from "nonprofit" alone
    assert detect_negation_scope("The nonprofit was founded in 1990 and it grew.") is None


def test_all_does_not_match_small():
    assert not _contains_phrase("a small dog barked", "all")
    assert _modal_strength("A small dog barked.") is None


def test_can_may_do_not_match_canada_mayor():
    assert not _contains_phrase("canada", "can")
    assert not _contains_phrase("the mayor spoke", "may")
    assert _modal_strength("The mayor of Canada spoke.") is None


def test_real_word_still_matches_at_boundaries():
    assert _contains_phrase("no dogs are allowed", "no")
    assert _contains_phrase("all men are mortal", "all")
    assert _contains_phrase("it may rain", "may")
    assert _contains_phrase("(no)", "no")  # punctuation-adjacent still matches


# --- word-boundary safety on the NEW Condition/Concession connectives -------
#
# _CONDITION_CONNECTIVES / _CONCESSION_CONNECTIVES are brand new in this
# rebuild, so they get their own boundary-safety checks, following this
# file's existing precedent (nonprofit/small/canada/mayor above) for what
# a bare-`in`-substring bug would look like on the new lists specifically.


def test_if_does_not_match_gift():
    """"if" is a realistic collision risk: it is a contiguous substring of
    "gift"."""
    assert not _contains_phrase("a lovely gift", "if")
    assert detect_condition_satellite("She received a lovely gift.", "X") is None


def test_never_does_not_match_nevertheless():
    """"nevertheless" is a brand-new Concession connective that starts
    with "never" -- a _NEGATION_WORDS entry used elsewhere in this file.
    Confirms the two lists don't cross-contaminate through a substring
    collision."""
    text = "The nonprofit struggled financially; nevertheless it survived."
    assert not _contains_phrase(text, "never")
    assert detect_negation_scope(text) is None


def test_not_does_not_match_notwithstanding():
    """"notwithstanding" is a brand-new Concession connective that starts
    with "not" -- a _NEGATION_WORDS entry used elsewhere in this file."""
    assert not _contains_phrase("notwithstanding the delay", "not")


# --- shared modal wordlists: verbatim-preserved modal is recognized ----------


def test_can_preserved_verbatim_in_formal_no_false_flag():
    """Confirmed bug: "can" was missing from the formal-side weak list, so a
    formal string preserving "can" verbatim was reported as having no
    explicit modal marker at all."""
    english = "AI can generate entirely new possibilities."
    formal = "It is possible that AI can generate entirely new possibilities."
    assert detect_modal_mismatch(english, formal, formal_mode="english") is None


def test_perhaps_preserved_verbatim_in_formal_no_false_flag():
    english = "Perhaps the theory is incomplete."
    formal = "Perhaps the theory is incomplete in some respect."
    assert detect_modal_mismatch(english, formal, formal_mode="english") is None


def test_should_preserved_verbatim_in_formal_no_false_flag():
    """Confirmed bug: there was no medium-tier formal-side list at all, so
    "should" preserved verbatim in the formal string always produced a
    false "modal marker dropped" flag."""
    english = "The system should be deployed carefully."
    formal = "The system should be deployed with care."
    assert detect_modal_mismatch(english, formal, formal_mode="english") is None


def test_dropped_modal_still_flagged():
    """The real failure (qualifier dropped) must still fire."""
    flag = detect_modal_mismatch(
        "The policy may change.", "The policy changes.", formal_mode="english"
    )
    assert flag is not None
    assert flag["type"] == "modal_mismatch"
    assert "no explicit modal marker" in flag["reason"]


def test_strength_mismatch_flagged():
    flag = detect_modal_mismatch(
        "Users may opt out.", "All users must opt out.", formal_mode="english"
    )
    assert flag is not None
    assert "weak" in flag["reason"] and "strong" in flag["reason"]


# --- "no ___ than" idiom masking ---------------------------------------------


def test_no_than_idiom_masked_in_lower():
    for word in ("less", "more", "fewer", "greater", "later", "earlier", "sooner"):
        masked = _lower(f"delivered in no {word} than five days")
        assert f"no {word} than" not in masked


def test_no_less_than_no_false_negation_flag():
    """Confirmed bug: bare "no" inside "no less than" plus an unrelated
    "and" elsewhere produced a spurious negation-scope flag."""
    sentence = (
        "The vendor must retain logs for no less than ninety days, "
        "and this requirement applies to all subcontractors."
    )
    assert detect_negation_scope(sentence) is None
    assert detect_segment_negation_scope(sentence) is None


def test_no_more_than_no_false_strong_modal():
    """Latent sibling of the negation bug: idiomatic "no" must not read as
    a strong modal on its own."""
    assert _modal_strength("Responses arrive in no more than five minutes.") is None


def test_real_negation_still_detected_alongside_idiom():
    sentence = "The vendor must not delete logs, and retains them for no less than ninety days."
    flag = detect_negation_scope(sentence)
    assert flag is not None and flag["type"] == "negation_scope"


# --- modal mismatch is a no-op in symbolic-logic mode ------------------------


def test_modal_mismatch_noop_in_logic_mode():
    english = "Every payment must be authorized."
    formal = "Payment(x) >> Authorized(x)"  # symbolic: no modal by construction
    assert detect_modal_mismatch(english, formal, formal_mode="logic") is None
    # identical inputs in english mode DO flag -- proving the no-op is the
    # mode check, not the inputs
    assert detect_modal_mismatch(english, formal, formal_mode="english") is not None


def test_annotate_axiom_logic_mode_no_modal_flag():
    ax = {
        "english": "Every payment must be authorized.",
        "formal": "Payment(x) >> Authorized(x)",
        "segment_index": 0,
    }
    annotate_axiom(ax, mode="logic")
    assert "modal_mismatch" not in _flag_types(ax["risk_flags"])


def test_annotate_axiom_both_mode_checks_formal_english():
    # formal_english preserves the modal -> no mismatch flag, even though
    # formal_logic (symbolic) obviously has none.
    ax = {
        "english": "The policy may change.",
        "formal_logic": "Policy(x) >> Change(x)",
        "formal_english": "It may be that the policy changes.",
        "segment_index": 0,
    }
    annotate_axiom(ax, mode="both")
    assert "modal_mismatch" not in _flag_types(ax["risk_flags"])

    # formal_english drops the modal -> mismatch fires, and it fired off
    # formal_english, not formal_logic.
    ax2 = {
        "english": "The policy may change.",
        "formal_logic": "Policy(x) >> Change(x)",
        "formal_english": "The policy changes.",
        "segment_index": 0,
    }
    annotate_axiom(ax2, mode="both")
    assert "modal_mismatch" in _flag_types(ax2["risk_flags"])


# --- condition_satellite: well-formedness gate -------------------------------


def test_condition_satellite_well_formedness_gate_rejects_bare_phrase():
    """"except for good cause" has no subject/finite verb of its own --
    it's a phrase, not a clause -- so it must not be flagged even though
    "except" text is absent from a bare-nucleus formal string."""
    assert _has_subject_and_finite_verb("for good cause") is False
    english = "The applicant may request an extension except for good cause."
    assert detect_condition_satellite(english, "Whatever") is None


def test_condition_satellite_well_formedness_gate_accepts_real_clause():
    assert _has_subject_and_finite_verb("the parties agree otherwise in writing") is True


# --- condition_satellite: severed / dropped / present-no-flag ---------------


def test_condition_satellite_present_no_flag():
    """Connective and clause content both survive in the formal string --
    treated as still co-occurring with the nucleus, so no flag."""
    english = "Unless the client provides written notice, the contract automatically renews."
    formal = "Unless the client provides written notice, the contract automatically renews."
    assert detect_condition_satellite(english, formal) is None


def test_condition_satellite_dropped():
    """Neither the connective nor the clause's content survives -- the
    whole satellite vanished during formalization."""
    english = "Unless the client provides written notice, the contract automatically renews."
    formal = "The contract automatically renews."
    flag = detect_condition_satellite(english, formal)
    assert flag is not None
    assert flag["type"] == "condition_satellite"
    assert "unless" in flag["reason"]
    assert "shows no trace of that satellite at all" in flag["reason"]


def test_condition_satellite_severed():
    """The clause's content survives, but detached from the connective
    that marked it as a condition -- reads as an independent fact."""
    english = "Unless the client provides written notice, the contract automatically renews."
    formal = "The client provides written notice. The contract automatically renews."
    flag = detect_condition_satellite(english, formal)
    assert flag is not None
    assert flag["type"] == "condition_satellite"
    assert "does not keep the connective and the clause's content together" in flag["reason"]


def test_condition_satellite_no_connective_no_flag():
    assert detect_condition_satellite("The contract automatically renews.", "X") is None


# --- concession_satellite: severed / dropped / present-no-flag --------------


def test_concession_satellite_present_no_flag():
    english = "Although the applicant may request an extension, the deadline remains fixed."
    formal = "Although the applicant may request an extension, the deadline remains fixed."
    assert detect_concession_satellite(english, formal) is None


def test_concession_satellite_dropped():
    english = "Although the applicant may request an extension, the deadline remains fixed."
    formal = "The deadline remains fixed."
    flag = detect_concession_satellite(english, formal)
    assert flag is not None
    assert flag["type"] == "concession_satellite"
    assert "although" in flag["reason"]
    assert "shows no trace of that satellite at all" in flag["reason"]


def test_concession_satellite_severed():
    english = "Although the applicant may request an extension, the deadline remains fixed."
    formal = "The applicant may request an extension. The deadline remains fixed."
    flag = detect_concession_satellite(english, formal)
    assert flag is not None
    assert flag["type"] == "concession_satellite"
    assert "does not keep the connective and the clause's content together" in flag["reason"]


def test_concession_satellite_however_standalone_not_flagged():
    """"However, ..." with nothing preceding it to concede against must
    not be flagged, even though the following clause is well-formed on
    its own."""
    english = "However, the team adapted quickly."
    assert detect_concession_satellite(english, "Whatever") is None


def test_concession_satellite_however_connecting_clauses_is_flagged():
    english = "The plan failed, however the team adapted quickly."
    formal = "The plan failed."
    flag = detect_concession_satellite(english, formal)
    assert flag is not None and flag["type"] == "concession_satellite"


def test_concession_satellite_even_if_also_triggers_condition():
    """"even if" is deliberately in BOTH connective lists -- both
    detectors independently check it, and both may fire on the same
    text; this is intentional, not deduped (see _OVERLAPPING_GROUPS)."""
    english = "Even if the market does shift, the contract price stays fixed."
    formal = "The contract price stays fixed."
    cond_flag = detect_condition_satellite(english, formal)
    conc_flag = detect_concession_satellite(english, formal)
    assert cond_flag is not None and cond_flag["type"] == "condition_satellite"
    assert conc_flag is not None and conc_flag["type"] == "concession_satellite"


# --- segment-level satellite detectors: fire only when claim-level didn't ---

_CONDITION_SEGMENT = (
    "Unless the parties agree otherwise in writing, the fee is due within 30 days."
)
_CONCESSION_SEGMENT = (
    "Although the applicant may request an extension, the deadline remains fixed."
)


def test_segment_condition_satellite_fires_when_claim_level_did_not():
    """Claim extraction split the satellite into a different claim than
    the nucleus: neither claim's own text shows a Condition connective,
    but the source segment does."""
    flags = flag_claim(
        english="The fee is due within 30 days.",
        formal="Due(fee, 30)",
        formal_mode="logic",
        segment_text=_CONDITION_SEGMENT,
    )
    types = _flag_types(flags)
    assert "condition_satellite" not in types
    assert "segment_condition_satellite" in types


def test_segment_condition_satellite_suppressed_when_claim_level_fired():
    flags = flag_claim(
        english="Unless the parties agree otherwise in writing, the fee is due within 30 days.",
        formal="F",
        formal_mode="english",
        segment_text=_CONDITION_SEGMENT,
    )
    types = _flag_types(flags)
    assert "condition_satellite" in types
    assert "segment_condition_satellite" not in types


def test_segment_concession_satellite_fires_when_claim_level_did_not():
    flags = flag_claim(
        english="The deadline remains fixed.",
        formal="Fixed(deadline)",
        formal_mode="logic",
        segment_text=_CONCESSION_SEGMENT,
    )
    types = _flag_types(flags)
    assert "concession_satellite" not in types
    assert "segment_concession_satellite" in types


def test_segment_concession_satellite_suppressed_when_claim_level_fired():
    flags = flag_claim(
        english="Although the applicant may request an extension, the deadline remains fixed.",
        formal="F",
        formal_mode="english",
        segment_text=_CONCESSION_SEGMENT,
    )
    types = _flag_types(flags)
    assert "concession_satellite" in types
    assert "segment_concession_satellite" not in types


def test_segment_satellite_detectors_standalone():
    assert detect_segment_condition_satellite(_CONDITION_SEGMENT) is not None
    assert detect_segment_condition_satellite("The sky is blue.") is None
    assert detect_segment_concession_satellite(_CONCESSION_SEGMENT) is not None
    assert detect_segment_concession_satellite("The sky is blue.") is None


def test_condition_and_concession_satellite_are_noop_in_logic_mode():
    """Like detect_modal_mismatch, both are skipped entirely in "logic"
    formal_mode -- a symbolic formal string can no more contain "unless"
    than it can contain "must", by construction. This gating lives in
    flag_claim, not inside the detector functions themselves."""
    english = "Unless the client provides written notice, the contract automatically renews."
    flags_logic = flag_claim(english, "Renews(contract)", formal_mode="logic")
    assert "condition_satellite" not in _flag_types(flags_logic)
    # identical inputs in english mode DO flag -- proving the no-op is the
    # mode check in flag_claim, not the detector itself (which is
    # mode-agnostic and would flag this on its own).
    flags_english = flag_claim(english, "Renews(contract)", formal_mode="english")
    assert "condition_satellite" in _flag_types(flags_english)
    assert detect_condition_satellite(english, "Renews(contract)") is not None


# --- segment_negation_scope (kept, unchanged parent detector) ---------------


_NEGATION_SEGMENT = (
    "The processor shall not transfer personal data abroad, and shall "
    "not permit subprocessors to do so."
)


def test_segment_negation_scope_fires_when_claim_level_did_not():
    flags = flag_claim(
        english="The processor shall not transfer personal data abroad.",
        formal="F",
        formal_mode="logic",
        segment_text=_NEGATION_SEGMENT,
    )
    types = _flag_types(flags)
    assert "negation_scope" not in types
    assert "segment_negation_scope" in types


def test_segment_negation_scope_suppressed_when_claim_level_fired():
    flags = flag_claim(
        english="The processor shall not transfer data abroad and shall not permit subprocessors to do so.",
        formal="F",
        formal_mode="logic",
        segment_text=_NEGATION_SEGMENT,
    )
    types = _flag_types(flags)
    assert "negation_scope" in types
    assert "segment_negation_scope" not in types


def test_segment_negation_scope_standalone():
    assert detect_segment_negation_scope(_NEGATION_SEGMENT) is not None
    assert detect_segment_negation_scope("The sky is blue.") is None


# --- Unformalized tier -------------------------------------------------------


def test_unformalized_tier_for_formal_none():
    ax = {"english": "Every event must have a cause.", "formal": None, "segment_index": 3}
    annotate_axiom(ax, mode="logic")
    assert ax["risk_tier"] == "Unformalized"
    assert ax["risk_flags"] == []


def test_unformalized_tier_for_both_mode_all_none():
    ax = {
        "english": "Every event must have a cause.",
        "formal_logic": None,
        "formal_english": None,
        "segment_index": 3,
    }
    annotate_axiom(ax, mode="both")
    assert ax["risk_tier"] == "Unformalized"
    assert ax["risk_flags"] == []


def test_unformalized_skips_segment_checks():
    """Segment-level checks must not pile flags onto an Unformalized axiom,
    even when the source segment would trigger them."""
    ax = {"english": "The contract terminates.", "formal": None, "segment_index": 9}
    annotate_axioms([ax], mode="logic", segment_lookup={9: _CONDITION_SEGMENT})
    assert ax["risk_tier"] == "Unformalized"
    assert ax["risk_flags"] == []


def test_formalized_axiom_gets_normal_tier():
    ax = {"english": "The sky is blue.", "formal": "Blue(sky)", "segment_index": 0}
    annotate_axiom(ax, mode="logic")
    assert ax["risk_tier"] in ("Low", "Medium", "High")


# --- dedupe-for-scoring is a safe no-op with an empty _OVERLAPPING_GROUPS ---


def test_dedupe_is_noop_with_empty_overlapping_groups():
    """_OVERLAPPING_GROUPS is empty now that hedge (the only entry's other
    member) is retired -- _dedupe_for_scoring must be a safe no-op and
    must not silently drop any flags."""
    flags = [
        {"type": "condition_satellite", "reason": "r1"},
        {"type": "modal_mismatch", "reason": "r2"},
        {"type": "cross_reference", "reason": "r3"},
    ]
    scored = _dedupe_for_scoring(flags)
    assert _flag_types(scored) == {"condition_satellite", "modal_mismatch", "cross_reference"}


def test_condition_satellite_and_cross_reference_both_counted_in_tier():
    """Integration-style tier check with the new weights: condition_satellite
    (3) + cross_reference (1) = 4 -> High. Replaces the old hedge-based
    dedupe test (hedge no longer exists); condition_satellite/
    cross_reference are unrelated signals here, so nothing should dedupe."""
    english = "As noted above, unless the client objects in writing, the fee applies."
    formal = "The fee applies."  # condition dropped -> condition_satellite; "as noted above" -> cross_reference
    flags = flag_claim(english, formal, formal_mode="english")
    types = _flag_types(flags)
    assert {"condition_satellite", "cross_reference"} <= types
    scored = _dedupe_for_scoring(flags)
    assert {"condition_satellite", "cross_reference"} <= _flag_types(scored)
    assert compute_tier(flags) == "High"  # 3 + 1 = 4


def test_no_bare_in_substring_checks_in_module():
    """Structural guard: phrase matching must go through the boundary-safe
    helpers. A bare `<string> in text` check on a phrase list would
    reintroduce the nonprofit/small/canada bug class. We check the module
    source for the known-bad pattern of iterating a phrase list with `in`.
    """
    import inspect
    src = inspect.getsource(risk_triage)
    for bad in ("p in text", "phrase in text", "marker in text", "w in text"):
        assert bad not in src, f"bare substring check found: {bad}"
