import type { UnitPoint } from "../generated/live";
import { type FieldData, type PipelineRun, type RunState, useApp } from "../store";

/** The evidence field (all units of the chunker this pipeline uses). */
export function useField(run: RunState, pipeline: PipelineRun | undefined): FieldData | undefined {
  const config = useApp((s) => s.config);
  // A run's pipelines arrive with its first events, so just after a question is sent
  // the active one may not exist yet.
  const chunker = config?.pipelines.find((p) => p.pipeline_id === pipeline?.id)?.chunker ?? "structural";
  return run.fields[chunker];
}

export function unitOf(field: FieldData | undefined, unitId: string | null | undefined): UnitPoint | undefined {
  if (!field || !unitId) return undefined;
  const i = field.index.get(unitId);
  return i === undefined ? undefined : field.units[i];
}
