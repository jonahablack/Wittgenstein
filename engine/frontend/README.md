# Frontend (stub + one static review screen)

This is still mostly a documented stub, not a built application — see
`docs/implementation-plan.md` and `docs/adr/0001-registry-first-architecture.md`. The
one exception is `public/review.html`: a single static HTML file (no build step, no
framework, no dependencies) implementing the review-loop prototype described in
`docs/review-loop-implementation-plan.md` §H and `docs/review-loop-demo.md`. No UI
polish is invested there beyond basic legibility, per that plan's explicit
"no polished visual design before the review loop works end to end."

## Intent

When built, this frontend should render `RiskEvent`s and `ApplicabilityAssessment`s
returned by `POST /risk-events/derive` and `POST /applicability/assess` as
registry-driven review alerts: one card per risk event, showing

- the mechanism's `canonical_name` and `epistemic_status` (with status-appropriate
  visual treatment — an `externally_established` finding should not look the same as
  a `trace_integrity_condition` or `research_hypothesis` one),
- `observed_evidence` and `eligibility_gate_results` (what was actually seen, not an
  inferred verdict),
- `allowed_claim_language` rendered verbatim, never paraphrased or strengthened,
- the linked `reviewer_action` as a concrete, bounded question,
- a link to the mechanism's dossier (`GET /registry/mechanisms/{id}/dossier`).

## Explicit non-goal

No component in this stub computes or displays a numerical "risk score" or
"hallucination probability" — the backend does not produce one, and the frontend must
not synthesize one client-side either.

## Types

`src/types/` mirrors the backend's public schemas closely enough to type-check
against API responses (see `../schemas/generated/` for the JSON Schema source of
truth); it is hand-written here rather than codegen'd, since codegen tooling is out of
scope for this milestone.

## Running

`package.json` still has no build/dev scripts wired up, and the eventual framework-based
frontend for `RiskEvent`/`ApplicabilityAssessment` cards described above remains
unbuilt. To run the one static page that does exist:

```bash
make api                              # backend, in one terminal
python -m http.server 8080 -d public  # from this directory, in another
```

Then open `http://localhost:8080/review.html` — see `docs/review-loop-demo.md` for the
walkthrough. It talks to the backend via CORS-enabled `fetch` calls (dev-only
`allow_origins=["*"]` in `api/app.py`), not through any bundler.
