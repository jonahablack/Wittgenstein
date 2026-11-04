# Literature review protocol

A PRISMA-style protocol for finding, screening, and extracting evidence for the
registry. This governs `EvidenceRecord` creation — see `docs/registry-governance.md`
for how the resulting evidence changes a mechanism's status.

## Research question

For a candidate RAG failure mechanism, what peer-reviewed (or, provisionally,
preprint) empirical evidence exists that (a) the mechanism's necessary causal
ingredients actually produce a measurable effect, (b) under what experimental
envelope, and (c) with what stated limitations and boundary conditions?

## Search sources and venues

- ACL Anthology (ACL, EMNLP, NAACL, Findings, TACL, COLM)
- NeurIPS, ICML, ICLR proceedings
- arXiv cs.CL / cs.IR / cs.AI (preprint tier only — see peer-review policy below)
- Semantic Scholar / Google Scholar for citation-chaining (discovery only, not a
  source of primary evidence itself)

## Search-query logging

Every search must be logged before screening begins, in a dated entry under
`docs/logs/` (per the parent workspace's logging convention) or in the mechanism's
own evidence-gap notes, recording:

- Exact query string(s) used, verbatim.
- Source/database searched.
- Date searched (results drift over time; re-running the same query later can surface
  different results).
- Number of results returned, and how many were screened.

## Screening / inclusion / exclusion criteria

**Include** a paper as a candidate source if it:

- Reports an empirical result (not purely a position paper or survey without new
  data) bearing on the mechanism's causal claim.
- States its experimental setting with enough detail to populate
  `ExperimentalEnvelope` (task, retrieval config, generator, etc.) — a paper that
  cannot be mapped to an envelope cannot be usefully compared for transferability.

**Exclude**:

- Marketing/blog-post "evaluations" with no described methodology.
- Papers whose only relevant claim is a passing anecdotal mention, not a measured
  result.
- Duplicate reports of the same underlying experiment (see duplicate handling below).

## Peer-review policy

- `peer_review_status=peer_reviewed` only for venues with a documented peer-review
  process (the venues listed above, plus workshop papers explicitly marked
  `workshop`).
- arXiv preprints are `preprint` regardless of how well-cited they are, until/unless
  a peer-reviewed version is found and substituted as the primary source.
- `A1`/`A2` evidence grades require `peer_reviewed` status
  (`schemas/evidence.py::EvidenceRecord._a_grade_requires_peer_review`) — this is
  enforced in code, not just policy.

## Study-quality / evidence-grade procedure

Assign `evidence_grade` using this decision order:

1. Is it a peer-reviewed causal intervention directly on the mechanism's claim? → A1.
2. Is it a peer-reviewed strong controlled comparison (not a designed intervention,
   but a clean comparison)? → A2.
3. Is it peer-reviewed but requires a mechanistic-transfer argument to apply (e.g. a
   long-context finding being applied to RAG)? → B1.
4. Is it peer-reviewed evidence about one pipeline component in isolation? → B2.
5. Is it empirical but not peer-reviewed? → C.
6. Is it this project's own local testing? → D.
7. Otherwise → E (hypothesis).

## Duplicate handling

When two papers report the same underlying experiment (e.g. a conference paper and
its extended preprint), create one `EvidenceRecord` for the stronger version
(peer-reviewed over preprint) and note the other's existence in `stated_limitations`
or `full_citation`, rather than creating two records that would double-count as
"independent support" in a dossier.

## Evidence extraction procedure

1. Obtain the primary source (PDF or authoritative HTML) — never extract from a
   secondary summary.
2. Copy `exact_quote` verbatim, character-for-character, including the exact
   `quote_location` (e.g. "Table 3", "Section 5.2", "Abstract").
3. Populate `experimental_envelope` from the paper's stated methodology, leaving any
   field the paper doesn't specify as `None` — do not infer. **Always set
   `rag_presence` explicitly** (`True` if the study evaluates an actual
   retrieve-then-generate pipeline, `False` if it's a related but non-RAG setting such
   as plain long-context QA) — never leave it `None` for a paper you have actually
   read; the evidence-threshold rule (`docs/evidence-grading.md`) treats an unset
   `rag_presence` as disqualifying for `externally_established`, same as `False`.
3a. Set `direction` (`supports` / `refutes` / `mixed` / `null`) based on the paper's
   own stated finding relative to the mechanism's causal claim — never left unset. A
   paper that speaks to the mechanism's setting without taking a clear position on the
   claim itself is `null`, not `supports`.
4. Record `effect_size_text` and `statistical_evidence` verbatim or as directly
   computable from reported numbers; never estimate or round beyond what's reported.
5. Record `stated_limitations` from the paper's own limitations/threats-to-validity
   section, not just your own assessment.
6. Set `verification_status=verified` only once all of the above is done and a second
   pass has confirmed the quote against the source. Until then,
   `verification_status=unverified` with literal `TODO` placeholders.

## Single vs. dual reviewer procedure

- A record may be created by a single reviewer with `verification_status=unverified`.
- Promotion to `verified` requires a second reviewer to independently check the quote
  and metadata against the primary source (or, for a solo contributor, a second pass
  after a time gap, disclosed as such).
- `extraction_reviewer` records who did the (first) extraction; a dual-review pass
  should be noted in the mechanism's dossier notes, not silently folded in.

## Contradiction / null-result handling

Evidence that contradicts an existing record, or reports a null result, is recorded as
its own `EvidenceRecord` linked to the same mechanism — never discarded and never
used to silently overwrite the existing record.
`REP_SEGMENTATION_GRANULARITY_MISMATCH` is seeded specifically to demonstrate this:
two evidence records, explicitly not merged into one "winning" chunking-method claim.

## Registry update / versioning policy

New/updated evidence triggers a `registry_version` bump per `docs/registry-spec.md`.
A verification pass that removes the last `TODO` from a mechanism's qualifying
evidence is what unblocks `default_activation_policy` moving off
`disabled_by_default_or_research_mode` — see
`registry/validator.py::_check_activation_requires_verified_evidence`.

## Citation chaining

Forward and backward citation chaining (via Semantic Scholar or similar) is permitted
for *discovery* — finding candidate papers to screen — but a paper found this way
still goes through the full screening/extraction procedure above before becoming an
`EvidenceRecord`. Citation chaining is never itself evidence.

## Documenting omitted and unvalidated modes

A candidate failure mode that was searched for and not found empirically supported
should still be recorded — as a `research_hypothesis` mechanism with an empty or
gap-noting evidence list (see the eleven `HYP_*` mechanisms in
`data/registry/failure_modes.seed.yaml`), not silently dropped. The absence of strong
evidence is itself useful information for the next literature-review pass, and
prevents the same ground being re-searched from scratch.
