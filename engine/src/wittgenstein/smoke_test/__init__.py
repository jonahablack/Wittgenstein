"""Real-trace smoke-test harness -- docs/real-trace-smoke-test-plan.md.

Reuses `review.imported_answer.import_answer` for the actual pipeline run; this
package only adds corpus/manifest resolution from a `SmokeTestCase`, the inspection
report, and the manual-label template, none of which are a parallel pipeline
implementation.
"""
