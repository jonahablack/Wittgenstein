"""Export JSON Schema files for every public interchange schema.

These are the schemas external tools/integrations should validate against -- kept
separate from the Pydantic models themselves so the interchange format is explicit and
versioned independently of internal refactors.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from wittgenstein import schemas as s

EXPORTED_MODELS: dict[str, type[BaseModel]] = {
    "FailureMechanism": s.FailureMechanism,
    "ManifestGate": s.ManifestGate,
    "TraceTrigger": s.TraceTrigger,
    "EvidenceRecord": s.EvidenceRecord,
    "ExperimentalEnvelope": s.ExperimentalEnvelope,
    "PipelineManifest": s.PipelineManifest,
    "CorpusProfile": s.CorpusProfile,
    "QueryTrace": s.QueryTrace,
    "ApplicabilityAssessment": s.ApplicabilityAssessment,
    "RiskEvent": s.RiskEvent,
    "ReviewAction": s.ReviewAction,
    "LocalValidationRecord": s.LocalValidationRecord,
    "SourceDocument": s.SourceDocument,
    "SourceSegment": s.SourceSegment,
    "PropositionCandidate": s.PropositionCandidate,
    "PropositionAnnotation": s.PropositionAnnotation,
    "LLMExtractionResult": s.LLMExtractionResult,
    "ReviewEvent": s.ReviewEvent,
    "SmokeTestCase": s.SmokeTestCase,
    "SmokeTestCaseFile": s.SmokeTestCaseFile,
    "ClaimEvidenceComparison": s.ClaimEvidenceComparison,
    "EvidenceSet": s.EvidenceSet,
}


def export_all(output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, model in EXPORTED_MODELS.items():
        schema = model.model_json_schema()
        schema["$id"] = f"https://wittgenstein-rag-reliability/schemas/{name}.schema.json"
        path = output_dir / f"{name}.schema.json"
        path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
        written.append(path)
    return written
