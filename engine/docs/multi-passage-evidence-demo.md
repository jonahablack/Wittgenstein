# Multi-passage evidence-set demo

A walkthrough of the multi-passage evidence-set layer described in
`docs/multi-passage-evidence-plan.md`, using the same fictional "widget certification
program" domain as `docs/review-loop-demo.md` and
`src/wittgenstein/demo/widget_corpus.py`. Everything below runs offline -- no LLM
provider credentials are required or used, and no dense/hybrid retrieval is involved.

## 1. What this layer adds

`review/imported_answer.py::import_answer` already builds one `ClaimEvidenceComparison`
per (answer claim, packed passage) pair. Most of the time one packed passage directly
supports a claim and nothing more is needed. When no single passage does, this layer
(`review/evidence_set.py::construct_evidence_set`) asks a narrower question: do *two*
of the packed passages, taken together, supply the claim's separate components (e.g.
one confirms the applicable widget class, another confirms the applicable zone)? The
result is always a candidate relationship (`EvidenceSet.relationship_status`, one of
the five `composite_*` statuses), never a factual adjudication -- exactly like a
single-passage `ClaimEvidenceComparison`.

## 2. Run it directly

```bash
uv run python - <<'EOF'
from wittgenstein.demo.widget_corpus import documents
from wittgenstein.review.imported_answer import import_answer

result = import_answer(
    query="What must a manufacturer show for eligibility, and what threshold must a Class I widget pass?",
    answer=(
        "A manufacturer is eligible for Standard Certification if it has held a valid "
        "Facility Registration for at least 12 months, and a Class I widget must pass "
        "the Load Stress Test at a 95% threshold."
    ),
    corpus=documents(),
    corpus_id="widget-certification-demo",
)

for es in result.evidence_sets:
    print(es.relationship_status, es.member_context_item_ids)
    print(" ", es.explanation)

print("support_requirement:", result.trace.support_requirement)
EOF
```

This claim genuinely needs two source passages (the Section 1 eligibility rule and the
Section 3 testing-threshold table row are independent facts, neither of which states
the other), so `import_answer` retrieves and packs both, `construct_evidence_set`
finds no single passage that alone reaches `direct_support_candidate`, and it proposes
a two-member `EvidenceSet`. Because that set has members, `result.trace.support_requirement`
(`schemas/trace.py::SupportRequirement`) is populated with `is_multi_hop=True` and the
two contributing item ids -- connecting to, without promoting or modifying, the
registered `RET_MULTIHOP_SUPPORT_INCOMPLETE` mechanism, whose gate condition
("the trace records a support-set or dependency structure to compare against") this
now makes evaluable against real traces.

## 3. The worked example from the plan doc

The clean, hand-constructed example the plan doc's design was built around:

```bash
uv run python - <<'EOF'
from wittgenstein.schemas.trace import AnswerClaim, ContextItem
from wittgenstein.review.claim_linking import compare_claim_to_candidate
from wittgenstein.review.evidence_set import construct_evidence_set

claim = AnswerClaim(claim_id="c1", text="Class III widgets in Zone A must be inspected annually.")
a = ContextItem(item_id="a", excerpt="Class III widgets must be inspected annually.", rank=1)
b = ContextItem(item_id="b", excerpt="This annual requirement applies only to widgets operating in Zone A.", rank=2)

comparisons = [compare_claim_to_candidate(claim, item) for item in (a, b)]
evidence_set, metrics = construct_evidence_set(claim, [a, b], comparisons, trace_id="t1")

print(evidence_set.relationship_status)     # composite_support_candidate
print(evidence_set.member_context_item_ids) # ['a', 'b']
print(evidence_set.covered_component_ids)   # entity/predicate/... + both scope tokens
print(metrics)                              # attempted=True, sets_considered=1, ...
EOF
```

`a` alone is honestly classified `qualification_required` (it never mentions Zone A),
not a false `direct_support_candidate` -- see
`docs/multi-passage-evidence-plan.md` §11 for why that matters.

## 4. Reviewer-facing fields

Every `EvidenceSet` carries, for a reviewer:

- `members[].field_comparisons` -- each member's own full field-by-field comparison
  against the claim, with exact source spans (never just a final label).
- `covered_component_ids` / `unresolved_component_ids` / `redundant_component_ids` --
  which claim components are covered, still missing, or covered by more than one
  member (recorded, not an error).
- `conflicts` -- any explicit incompatibility detected between two members, with the
  specific field and a bounded explanation.
- `construction_rationale` / `explanation` -- bounded, reviewer-facing text drawn from
  the fixed templates in `evidence_set.py::_bounded_evidence_set_explanation`. Never a
  sentence like "the answer is correct" or "these sources prove the answer."

## 5. Smoke-test integration

```bash
uv run wittgenstein smoke-test run \
  --cases data/examples/real_trace_smoke/cases.example.json \
  --output-dir /tmp/smoke-out
uv run wittgenstein smoke-test report --output-dir /tmp/smoke-out
```

Each case's `<case_id>.inspection.json` now includes `evidence_sets` and
`evidence_set_metrics`; the aggregate report includes an `evidence_set_summary`
(claims evaluated, attempted vs. skipped counts and why, relationship-status counts,
mean candidate-pool size). `smoke-005-multi-passage-cross-reference`'s bundled corpus
text turns out to give a single retrieved passage that already directly supports its
claim on its own -- a real, honest finding (single-passage support is always
preferred), documented in `docs/real-trace-smoke-test-results.md` rather than forced
into a fabricated composite result.

## 6. Known limitations

- The candidate pool for composition is packed items only; an explicit cross-reference
  or definitional dependency to a passage *outside* the packed set is not resolved
  (category 5 in `docs/multi-passage-evidence-plan.md` §10) -- such a claim stays
  `composite_unresolved`.
- Regex-based `object_value`/`numeric_value` extraction is noticeably less reliable on
  long, complex real-corpus sentences than on the plan's clean worked example; a
  genuinely complementary real-corpus pair can land on `composite_conflict_candidate`
  from an extraction artifact rather than a real disagreement (see
  `docs/multi-passage-evidence-plan.md` §11's last note). A human-labeled pilot is
  needed to quantify how often this happens.
- Default max evidence-set size is 2; a genuine three-way composition is only found
  when no valid two-item set exists at all (see `docs/multi-passage-evidence-plan.md`
  §9) -- the search prefers the smallest working set, which can settle for an
  incomplete two-item combination rather than searching further.
