"""The human review loop: imported-answer review mode, answer-claim extraction and
evidence linking, and reviewer-action persistence -- docs/review-loop-implementation-plan.md.

This package is a *consumer* of the existing registry-matching pipeline
(`services/applicability_service.py`) and the existing vertical-slice orchestration
(`demo/pipeline.py`), not a parallel implementation of either.
"""
