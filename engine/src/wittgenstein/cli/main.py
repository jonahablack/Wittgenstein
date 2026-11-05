"""Typer CLI: `wittgenstein <group> <command>`.

Every command here is a thin wrapper around the same service/registry/matching
modules the API uses -- no logic is duplicated between CLI and API.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime
from pathlib import Path

import typer
import yaml
from rich.console import Console
from rich.table import Table

from wittgenstein.registry.dossier import render_dossier
from wittgenstein.registry.loader import RegistryLoadError, load_registry
from wittgenstein.registry.validator import RegistrySeedIntegrityError
from wittgenstein.schemas.manifest import PipelineManifest
from wittgenstein.schemas.trace import QueryTrace
from wittgenstein.services.applicability_service import assess_mechanism
from wittgenstein.services.registry_service import default_seed_dir
from wittgenstein.services.trace_service import validate as validate_trace_service

app = typer.Typer(help="Wittgenstein RAG Reliability CLI.")
registry_app = typer.Typer(help="Inspect and edit the failure-mechanism registry.")
manifest_app = typer.Typer(help="Validate and profile pipeline manifests.")
trace_app = typer.Typer(help="Validate query traces.")
applicability_app = typer.Typer(help="Run applicability assessments.")
schemas_app = typer.Typer(help="Export JSON Schemas.")
examples_app = typer.Typer(help="Generate synthetic example data.")
demo_app = typer.Typer(help="Run the vertical-slice ingestion/retrieval/packing demo.")
smoke_test_app = typer.Typer(help="Run the real-trace smoke-test harness.")
evidence_set_app = typer.Typer(help="Real-corpus diagnostics for the multi-passage evidence-set layer.")
fixture_app = typer.Typer(help="Controlled synthetic-corpus fixtures (e.g. the Asteria manual).")

app.add_typer(registry_app, name="registry")
app.add_typer(manifest_app, name="manifest")
app.add_typer(trace_app, name="trace")
app.add_typer(applicability_app, name="applicability")
app.add_typer(schemas_app, name="schemas")
app.add_typer(examples_app, name="examples")
app.add_typer(demo_app, name="demo")
app.add_typer(smoke_test_app, name="smoke-test")
app.add_typer(evidence_set_app, name="evidence-set")
app.add_typer(fixture_app, name="fixture")

console = Console()


def _seed_dir_option(seed_dir: Path | None) -> Path:
    return seed_dir or default_seed_dir()


@registry_app.command("validate")
def registry_validate(
    seed_dir: Path = typer.Option(None, help="Registry seed directory (default: data/registry)."),
) -> None:
    """Load and validate the full registry, exiting non-zero on any integrity problem."""

    try:
        registry = load_registry(_seed_dir_option(seed_dir))
    except (RegistryLoadError, RegistrySeedIntegrityError) as exc:
        console.print(f"[bold red]Registry validation FAILED[/bold red]\n{exc}")
        raise typer.Exit(code=1) from exc
    console.print(
        f"[bold green]OK[/bold green]: {len(registry.mechanisms)} mechanisms, "
        f"{len(registry.evidence)} evidence records, {len(registry.gates)} manifest gates, "
        f"{len(registry.triggers)} trace triggers, {len(registry.review_actions)} review actions."
    )


@registry_app.command("list")
def registry_list(seed_dir: Path = typer.Option(None)) -> None:
    """List all mechanisms with their epistemic status and activation policy."""

    registry = load_registry(_seed_dir_option(seed_dir))
    table = Table(title="Failure mechanisms")
    table.add_column("id")
    table.add_column("epistemic_status")
    table.add_column("activation_policy")
    table.add_column("evidence_count", justify="right")
    for m in sorted(registry.mechanisms.values(), key=lambda m: m.id):
        table.add_row(
            m.id,
            m.epistemic_status.value,
            m.default_activation_policy.value,
            str(len(registry.evidence_for_mechanism(m.id))),
        )
    console.print(table)


@registry_app.command("show")
def registry_show(mechanism_id: str, seed_dir: Path = typer.Option(None)) -> None:
    """Print the full record for one mechanism as JSON."""

    registry = load_registry(_seed_dir_option(seed_dir))
    console.print_json(registry.mechanism(mechanism_id).model_dump_json())


@registry_app.command("dossier")
def registry_dossier(
    mechanism_id: str,
    seed_dir: Path = typer.Option(None),
    output: Path = typer.Option(None, help="Write Markdown to this file instead of stdout."),
) -> None:
    """Generate the Markdown dossier for one mechanism."""

    registry = load_registry(_seed_dir_option(seed_dir))
    md = render_dossier(registry, mechanism_id)
    if output:
        output.write_text(md)
        console.print(f"Wrote dossier to {output}")
    else:
        console.print(md)


@registry_app.command("export")
def registry_export(
    fmt: str = typer.Option("json", "--format", help="json | csv | yaml"),
    seed_dir: Path = typer.Option(None),
    output: Path = typer.Option(None, help="Output file (default: stdout)."),
) -> None:
    """Export all mechanisms in the requested interchange format."""

    registry = load_registry(_seed_dir_option(seed_dir))
    mechanisms = [m.model_dump(mode="json") for m in registry.mechanisms.values()]

    if fmt == "json":
        text = json.dumps(mechanisms, indent=2)
    elif fmt == "yaml":
        text = yaml.safe_dump(mechanisms, sort_keys=False)
    elif fmt == "csv":
        buf = io.StringIO()
        fieldnames = [
            "id",
            "canonical_name",
            "epistemic_status",
            "default_evidence_grade",
            "default_activation_policy",
            "pipeline_stage",
            "failure_object",
        ]
        writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for m in mechanisms:
            writer.writerow(m)
        text = buf.getvalue()
    else:
        console.print(f"[bold red]Unknown format:[/bold red] {fmt}")
        raise typer.Exit(code=1)

    if output:
        output.write_text(text)
        console.print(f"Wrote {fmt} export to {output}")
    else:
        console.print(text)


@registry_app.command("add-mechanism")
def registry_add_mechanism(seed_dir: Path = typer.Option(None)) -> None:
    """Interactively append a new mechanism to failure_modes.seed.yaml.

    New mechanisms always start as research_hypothesis / E_hypothesis /
    disabled_by_default_or_research_mode -- raise the status later, with evidence
    attached, via `registry validate` enforcing the epistemic rules. This command
    rewrites the seed file via YAML dump and does not preserve comments.
    """

    seed_dir = _seed_dir_option(seed_dir)
    mechanism_id = typer.prompt("Mechanism id (SCREAMING_SNAKE_CASE)")
    canonical_name = typer.prompt("Canonical name")
    short_description = typer.prompt("Short description")
    causal_claim = typer.prompt("Causal claim (state conservatively)")
    pipeline_stage = typer.prompt(
        "Pipeline stage (corpus_available|parsed_representation|index_units|retrieval_candidates|"
        "reranked_candidates|selected_context_items|packed_context_items|actual_prompt_token_spans|"
        "answer_claims|answer_to_evidence_support_edges|reviewer_judgments)"
    )
    failure_object = typer.prompt(
        "Failure object (retrieval_quality|context_utilization|context_integrity|"
        "answer_correctness|answer_attribution|answer_consistency)"
    )
    ingredients = typer.prompt("Necessary causal ingredients (comma-separated)").split(",")
    boundaries = typer.prompt("Known boundary conditions (comma-separated)").split(",")
    tags = typer.prompt("Tags (comma-separated)", default="").split(",")

    record = {
        "id": mechanism_id,
        "canonical_name": canonical_name,
        "short_description": short_description,
        "causal_claim": causal_claim,
        "pipeline_stage": pipeline_stage,
        "failure_object": failure_object,
        "necessary_causal_ingredients": [s.strip() for s in ingredients if s.strip()],
        "known_boundary_conditions": [s.strip() for s in boundaries if s.strip()],
        "epistemic_status": "research_hypothesis",
        "default_evidence_grade": "E_hypothesis",
        "default_activation_policy": "disabled_by_default_or_research_mode",
        "tags": [t.strip() for t in tags if t.strip()],
        "created_at": datetime.now(UTC).isoformat(),
        "updated_at": datetime.now(UTC).isoformat(),
        "registry_version": "0.1.0",
    }

    path = seed_dir / "failure_modes.seed.yaml"
    data = yaml.safe_load(path.read_text())
    data["mechanisms"].append(record)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
    console.print(f"[bold green]Added[/bold green] {mechanism_id} to {path}. Run `registry validate` next.")


@registry_app.command("add-evidence")
def registry_add_evidence(seed_dir: Path = typer.Option(None)) -> None:
    """Interactively append a new evidence record to evidence_records.seed.yaml.

    `exact_quote` must be copied verbatim from the primary source. If you have not yet
    personally verified it against the source, type the literal string
    "TODO: verify against primary source" and answer 'unverified' below.
    """

    seed_dir = _seed_dir_option(seed_dir)
    mechanism_id = typer.prompt("failure_mechanism_id")
    evidence_id = typer.prompt("Evidence id (e.g. EV-<MECHANISM>-002)")
    full_citation = typer.prompt("Full citation")
    title = typer.prompt("Title")
    authors = typer.prompt("Authors (comma-separated)").split(",")
    venue = typer.prompt("Venue")
    year = typer.prompt("Publication year (blank if unknown)", default="")
    peer_review_status = typer.prompt(
        "Peer review status (peer_reviewed|preprint|workshop|technical_report|unknown)"
    )
    exact_quote = typer.prompt("Exact quote (verbatim, or TODO placeholder)")
    quote_location = typer.prompt("Quote location (e.g. Table 3)")
    verification_status = typer.prompt("Verification status (verified|unverified|disputed|retracted_source)")
    evidence_grade = typer.prompt(
        "Evidence grade (A1_direct_causal_peer_reviewed|A2_strong_comparative_peer_reviewed|"
        "B1_mechanistic_transfer_peer_reviewed|B2_component_evidence_peer_reviewed|"
        "C_preprint_empirical|D_local_empirical|E_hypothesis)"
    )
    reviewer = typer.prompt("Extraction reviewer")

    record = {
        "id": evidence_id,
        "failure_mechanism_id": mechanism_id,
        "full_citation": full_citation,
        "title": title,
        "authors": [a.strip() for a in authors if a.strip()],
        "venue": venue,
        "publication_year": int(year) if year.strip() else None,
        "peer_review_status": peer_review_status,
        "persistent_identifier": None,
        "source_url": None,
        "exact_quote": exact_quote,
        "quote_location": quote_location,
        "quote_type": "finding_statement",
        "study_type": "observational_benchmark",
        "task": "TODO",
        "dataset_or_corpus": "TODO",
        "experimental_envelope": {},
        "intervention_or_comparison": "TODO",
        "outcome_metrics": [],
        "effect_size_text": None,
        "statistical_evidence": None,
        "stated_limitations": "TODO",
        "evidence_grade": evidence_grade,
        "extraction_reviewer": reviewer,
        "extraction_date": datetime.now(UTC).date().isoformat(),
        "verification_status": verification_status,
    }

    path = seed_dir / "evidence_records.seed.yaml"
    data = yaml.safe_load(path.read_text())
    data["evidence_records"].append(record)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
    console.print(f"[bold green]Added[/bold green] {evidence_id} to {path}. Run `registry validate` next.")


@manifest_app.command("validate")
def manifest_validate(manifest_file: Path) -> None:
    """Parse and structurally validate a PipelineManifest JSON/YAML file."""

    raw = _load_structured_file(manifest_file)
    try:
        PipelineManifest.model_validate(raw)
    except Exception as exc:  # noqa: BLE001 - surface full Pydantic error to the user
        console.print(f"[bold red]Invalid manifest[/bold red]\n{exc}")
        raise typer.Exit(code=1) from exc
    console.print("[bold green]OK[/bold green]: manifest is structurally valid.")


@manifest_app.command("profile")
def manifest_profile_cmd(manifest_file: Path) -> None:
    """Build and print the ExperimentalEnvelope derived from a manifest."""

    from wittgenstein.profiling.manifest_profile import build_envelope

    raw = _load_structured_file(manifest_file)
    manifest = PipelineManifest.model_validate(raw)
    envelope = build_envelope(manifest)
    console.print_json(envelope.model_dump_json())


@trace_app.command("validate")
def trace_validate(trace_file: Path) -> None:
    """Parse and structurally validate a QueryTrace JSON/YAML file."""

    raw = _load_structured_file(trace_file)
    try:
        trace = QueryTrace.model_validate(raw)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[bold red]Invalid trace[/bold red]\n{exc}")
        raise typer.Exit(code=1) from exc
    problems = validate_trace_service(trace)
    if problems:
        console.print("[bold yellow]Structural issues found:[/bold yellow]")
        for p in problems:
            console.print(f"- {p}")
        raise typer.Exit(code=1)
    console.print("[bold green]OK[/bold green]: trace is structurally valid.")


@applicability_app.command("assess")
def applicability_assess(
    manifest: Path = typer.Option(..., "--manifest"),
    trace: Path = typer.Option(None, "--trace"),
    mechanism_id: str = typer.Option(None, help="Assess only this mechanism id; default: all implemented."),
    seed_dir: Path = typer.Option(None),
) -> None:
    """Run the deterministic applicability assessment for one manifest (+ optional trace)."""

    from wittgenstein.matching.eligibility import MECHANISM_EVALUATORS

    registry = load_registry(_seed_dir_option(seed_dir))
    manifest_obj = PipelineManifest.model_validate(_load_structured_file(manifest))
    trace_obj = QueryTrace.model_validate(_load_structured_file(trace)) if trace else None

    mechanism_ids = [mechanism_id] if mechanism_id else list(MECHANISM_EVALUATORS)
    for mid in mechanism_ids:
        assessment = assess_mechanism(registry, mid, manifest_obj, trace_obj)
        console.print(f"\n[bold]{mid}[/bold]: {assessment.transfer_level.value} ({assessment.confidence.value})")
        console.print(assessment.explanation)


@schemas_app.command("export")
def schemas_export(output_dir: Path = typer.Option(Path("schemas/generated"))) -> None:
    """Export JSON Schema files for every public interchange schema."""

    from wittgenstein.exports.json_schema import export_all

    written = export_all(output_dir)
    console.print(f"Wrote {len(written)} schema file(s) to {output_dir}")


@examples_app.command("generate")
def examples_generate(output_dir: Path = typer.Option(Path("data/examples"))) -> None:
    """Regenerate the bundled synthetic example manifests/traces."""

    import sys

    repo_root = Path(__file__).resolve().parents[3]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from scripts.generate_example_data import main as generate_main

    generate_main(output_dir)
    console.print(f"Wrote example data to {output_dir}")


@demo_app.command("run")
def demo_run(
    enhanced: bool = typer.Option(
        False, "--enhanced", help="Also run the optional enhanced mode (deterministic offline DemoLLMClient)."
    ),
    output_dir: Path = typer.Option(
        None, help="If set, write each trace/manifest as JSON here instead of only printing a summary."
    ),
) -> None:
    """Run the no-LLM-baseline vertical-slice demo (ingestion -> BM25 retrieval ->
    programmatic packing -> QueryTrace) against the bundled widget-certification
    corpus, and optionally the enhanced mode alongside it.
    """

    from wittgenstein.demo.pipeline import run_enhanced_demo, run_no_llm_baseline_demo
    from wittgenstein.demo.widget_corpus import DEMO_QUERIES, documents

    def _run(label: str, results, corpus_metrics) -> None:
        console.print(
            f"\n[bold]{label}[/bold] -- corpus ingestion: {corpus_metrics.ingestion_latency_seconds:.4f}s"
        )
        table = Table(title=label)
        table.add_column("Query")
        table.add_column("Retrieved")
        table.add_column("Packed")
        table.add_column("Omitted")
        table.add_column("Prompt tokens")
        table.add_column("Retrieval latency (s)")
        for result in results:
            trace = result.trace
            table.add_row(
                trace.query,
                str(len(trace.retrieval_candidates or [])),
                str(len(trace.packed_context_items or [])),
                str(len(trace.omitted_context_items or [])),
                str(trace.final_prompt_token_count),
                f"{result.metrics.retrieval_latency_seconds:.4f}"
                if result.metrics.retrieval_latency_seconds
                else "-",
            )
        console.print(table)
        if output_dir is not None:
            output_dir.mkdir(parents=True, exist_ok=True)
            for result in results:
                trace_path = output_dir / f"{result.trace.trace_id}.trace.json"
                manifest_path = output_dir / f"{result.manifest.manifest_id}.manifest.json"
                trace_path.write_text(result.trace.model_dump_json(indent=2))
                manifest_path.write_text(result.manifest.model_dump_json(indent=2))
            console.print(f"Wrote {len(results)} trace/manifest pair(s) to {output_dir}")

    _, corpus_metrics, results = run_no_llm_baseline_demo(documents(), DEMO_QUERIES)
    _run("No-LLM baseline", results, corpus_metrics)

    if enhanced:
        _, enhanced_metrics, enhanced_results = run_enhanced_demo(documents(), DEMO_QUERIES)
        _run("Enhanced (DemoLLMClient)", enhanced_results, enhanced_metrics)


@smoke_test_app.command("run")
def smoke_test_run(
    cases: Path = typer.Option(..., help="Path to a cases.*.json file (SmokeTestCaseFile shape)."),
    output_dir: Path = typer.Option(
        ..., help="Directory to write per-case inspection reports and labels templates."
    ),
    enhanced: bool = typer.Option(
        False,
        "--enhanced",
        help="Allow an LLM call for ambiguous answer-claim candidates (a configured "
        "AnthropicProviderClient if available, else the offline DemoLLMClient). Never called by default.",
    ),
) -> None:
    """Run every case in a real-trace smoke-test cases file through imported-answer
    mode, writing an inspection report and a manual-labels template per case -- see
    docs/real-trace-smoke-test-plan.md.
    """

    from wittgenstein.smoke_test.runner import run_smoke_test

    results = run_smoke_test(cases, output_dir, enhanced=enhanced)

    table = Table(title="Real-trace smoke test")
    table.add_column("Case")
    table.add_column("Claims")
    table.add_column("Risk events")
    table.add_column("LLM calls")
    table.add_column("Time (s)")
    for result in results:
        table.add_row(
            result.case.case_id,
            str(len(result.imported_answer.trace.answer_claims)),
            str(len(result.imported_answer.risk_events)),
            str(result.imported_answer.metrics.llm_call_count),
            f"{result.processing_time_seconds:.3f}",
        )
    console.print(table)
    console.print(f"Wrote {len(results)} inspection report(s)/labels template(s) to {output_dir}")


@smoke_test_app.command("report")
def smoke_test_report(
    output_dir: Path = typer.Option(
        ..., help="Directory containing *.inspection.json/*.labels_template.json from a prior 'smoke-test run'."
    ),
) -> None:
    """Aggregate a completed run's inspection reports and (possibly human-filled-in)
    labels templates into one diagnostic summary -- see
    docs/real-trace-smoke-test-plan.md, "Produce summary metrics". Never collapses the
    pilot into one score, and never claims statistical generalization.
    """

    from wittgenstein.smoke_test.report import generate_report

    report = generate_report(output_dir)
    report_path = output_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2))

    console.print(f"[bold]{report['case_count']}[/bold] case(s) aggregated.")
    console.print(
        f"Missed-evidence count: {report['missed_evidence_count']['missed_count']} "
        f"(labeled: {report['missed_evidence_count']['labeled_count']}/"
        f"{report['missed_evidence_count']['total_count']})"
    )
    console.print(f"Spurious-link count: {report['spurious_link_count']['count']}")
    console.print(f"Provenance failures: {report['provenance_failures']['count']}")
    for caveat in report["caveats"]:
        console.print(f"[dim]Caveat: {caveat}[/dim]")
    console.print(f"Wrote full report to {report_path}")


@evidence_set_app.command("diagnose")
def evidence_set_diagnose(
    cases: Path = typer.Option(..., help="Path to a cases.*.json file (SmokeTestCaseFile shape)."),
    output_dir: Path = typer.Option(
        ..., help="Directory to write per-case diagnostic reports and labels templates."
    ),
    diagnostic_max_set_size: int | None = typer.Option(
        None,
        "--diagnostic-max-set-size",
        help="Only 3 is accepted. Runs a bounded, explicitly-warned diagnostic-only size-3 "
        "evidence-set search for small cases (never used by any other command, never changes "
        "the default max_set_size=2 construction `import_answer` itself runs).",
    ),
) -> None:
    """Run every case in a cases file through imported-answer mode plus read-only
    cross-reference/conflict/evidence-set-size diagnostics, writing a per-case
    diagnostic report and a manual-labels template -- see
    docs/evidence-set-real-corpus-diagnostics-plan.md. Always no-LLM, always
    deterministic; never modifies any pipeline output.
    """

    if diagnostic_max_set_size is not None and diagnostic_max_set_size != 3:
        raise typer.BadParameter("--diagnostic-max-set-size only accepts 3 (or omit it entirely).")

    from wittgenstein.evidence_set_diagnostics.runner import run_evidence_set_diagnostics

    results = run_evidence_set_diagnostics(cases, output_dir, diagnostic_max_set_size=diagnostic_max_set_size)

    table = Table(title="Evidence-set real-corpus diagnostics")
    table.add_column("Case")
    table.add_column("Claims")
    table.add_column("Cross-ref markers")
    table.add_column("Conflicts explained")
    table.add_column("Time (s)")
    for result in results:
        table.add_row(
            result.case.case_id,
            str(len(result.imported_answer.trace.answer_claims)),
            str(sum(len(m) for m in result.cross_reference_markers.values())),
            str(sum(len(e) for e in result.conflict_explanations.values())),
            f"{result.processing_time_seconds:.3f}",
        )
    console.print(table)
    console.print(f"Wrote {len(results)} diagnostic report(s)/labels template(s) to {output_dir}")


@evidence_set_app.command("report")
def evidence_set_diagnostics_report(
    output_dir: Path = typer.Option(
        ..., help="Directory containing *.diagnostic.json/*.diagnostic_labels.json from a prior 'diagnose' run."
    ),
) -> None:
    """Aggregate a completed diagnostic run's reports and (possibly human-filled-in)
    labels templates into one summary -- see
    docs/evidence-set-real-corpus-diagnostics-plan.md §10. Never recommends a next
    implementation priority; that classification is a human judgment made after
    reading the manual labels this report aggregates.
    """

    from wittgenstein.evidence_set_diagnostics.report import generate_diagnostic_report

    report = generate_diagnostic_report(output_dir)
    report_path = output_dir / "diagnostic_report.json"
    report_path.write_text(json.dumps(report, indent=2))

    console.print(f"[bold]{report['case_count']}[/bold] case(s) aggregated.")
    console.print(f"Cross-reference markers: {report['cross_reference_target_states']['total_markers']}")
    console.print(f"Conflicts explained: {report['conflict_diagnostics']['total_conflicts_explained']}")
    for caveat in report["caveats"]:
        console.print(f"[dim]Caveat: {caveat}[/dim]")
    console.print(f"Wrote full report to {report_path}")


@evidence_set_app.command("compare-cross-reference")
def evidence_set_compare_cross_reference(
    baseline: Path = typer.Option(
        ..., help="Directory containing a prior (pre-fix) diagnose run's *.diagnostic.json files."
    ),
    post_fix: Path = typer.Option(
        ..., help="Directory containing a later (post-fix) diagnose run's *.diagnostic.json files."
    ),
    cases: Path = typer.Option(
        ..., help="The cases.*.json file both runs were generated from (for query/answer_origin/locations)."
    ),
    output: Path = typer.Option(..., help="Where to write the comparison worksheet JSON."),
) -> None:
    """Read-only, deterministic baseline-vs-post-fix cross-reference comparison -- see
    docs/eu-ai-act-cross-reference-annotation-protocol.md. Never re-runs the pipeline,
    never alters diagnostics or annotation labels, and never fills a human-judgment
    label -- only compares already-computed, machine-observable fields from two
    existing diagnose runs.
    """

    import subprocess

    from wittgenstein.evidence_set_diagnostics.cross_reference_comparison import generate_comparison_worksheet

    result = subprocess.run(["git", "check-ignore", "-q", str(output)], capture_output=True)
    if result.returncode != 0:
        raise typer.BadParameter(
            f"{output} is not git-ignored -- refusing to write a comparison worksheet (which may embed "
            "source-derived claim/answer text from the diagnose runs) to a path git could track. Write it "
            "under a gitignored local_corpora/ path instead."
        )

    worksheet = generate_comparison_worksheet(baseline, post_fix, cases)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(worksheet, indent=2))

    case_ids = worksheet["case_ids"]
    console.print(f"[bold]{len(case_ids['common'])}[/bold] case(s) present in both runs.")
    if case_ids["baseline_only"] or case_ids["post_fix_only"] or case_ids["in_cases_file_only"]:
        console.print(
            f"[yellow]Mismatched case IDs -- baseline only: {case_ids['baseline_only']}, "
            f"post-fix only: {case_ids['post_fix_only']}, "
            f"in cases file but neither run: {case_ids['in_cases_file_only']}[/yellow]"
        )
    newly_detected_total = sum(len(c.get("markers_newly_detected", [])) for c in worksheet["cases"])
    console.print(f"Markers newly detected (post-fix only): {newly_detected_total}")
    console.print(f"Wrote comparison worksheet to {output}")


def _load_structured_file(path: Path) -> dict:
    text = path.read_text()
    if path.suffix in (".yaml", ".yml"):
        return yaml.safe_load(text)
    return json.loads(text)


_FIXTURE_DIRS = {"asteria_manual": Path("data/fixtures/asteria_manual")}


def _resolve_fixture_dir(name: str) -> Path:
    fixture_dir = _FIXTURE_DIRS.get(name)
    if fixture_dir is None:
        raise typer.BadParameter(f"Unknown fixture {name!r}. Known fixtures: {sorted(_FIXTURE_DIRS)}.")
    if not fixture_dir.exists():
        raise typer.BadParameter(f"Fixture directory {fixture_dir} does not exist.")
    return fixture_dir


@fixture_app.command("load")
def fixture_load(name: str = typer.Argument(..., help="Fixture name, e.g. 'asteria_manual'.")) -> None:
    """Load a controlled synthetic-corpus fixture and run its fixture-integrity
    validator (docs/controlled-synthetic-corpus-plan.md §14) -- every executable case
    is actually run through the real, no-LLM pipeline and checked against its
    hand-recorded expected/<case_id>.expected.json ground truth. Exits non-zero if any
    check fails.
    """

    from wittgenstein.fixtures.asteria_validator import validate_asteria_fixture

    fixture_dir = _resolve_fixture_dir(name)
    report = validate_asteria_fixture(fixture_dir)

    console.print(f"Fixture {name!r}: {report.case_count} case(s) checked.")
    if report.ok:
        console.print("[green]All fixture-integrity checks passed.[/green]")
        return

    for issue in report.issues:
        prefix = f"case={issue.case_id}: " if issue.case_id else ""
        console.print(f"[red][{issue.check}] {prefix}{issue.message}[/red]")
    raise typer.Exit(code=1)


@fixture_app.command("run")
def fixture_run(
    name: str = typer.Argument(..., help="Fixture name, e.g. 'asteria_manual'."),
    case: str = typer.Option(..., "--case", help="case_id from the fixture's cases.json to run."),
    manifest: str = typer.Option(
        None,
        "--manifest",
        help="Manifest id to run under (defaults to the case's own pipeline_manifest_id).",
    ),
    output_dir: Path = typer.Option(
        ..., "--output-dir", help="Directory to write the case's diagnostic report and labels template."
    ),
) -> None:
    """Run one fixture case through the real, no-LLM pipeline (via
    evidence_set_diagnostics.runner.run_diagnostic_case, unmodified) and write its
    diagnostic report/labels template -- the same JSON shape 'wittgenstein evidence-set
    diagnose' produces, so the local frontend/API tooling and any diagnostic report
    reader work identically for a fixture case. A manifest's own
    retrieval_manifest.candidate_depth (if set) is honored as the retrieval top_k --
    see docs/controlled-synthetic-corpus-plan.md §11 (asteria-p4-full-context-control's
    candidate_depth=1).
    """

    from wittgenstein.evidence_set_diagnostics.runner import (
        build_diagnostic_labels_template,
        build_diagnostic_report,
        run_diagnostic_case,
    )
    from wittgenstein.schemas.smoke_test import SmokeTestCaseFile
    from wittgenstein.smoke_test.manifest_registry import load_manifests

    fixture_dir = _resolve_fixture_dir(name)
    case_file = SmokeTestCaseFile.model_validate(json.loads((fixture_dir / "cases" / "cases.json").read_text()))
    matching = [c for c in case_file.cases if c.case_id == case]
    if not matching:
        raise typer.BadParameter(f"No case {case!r} found in {name}'s cases.json.")
    (selected_case,) = matching

    manifests = load_manifests(fixture_dir / "manifests.json")
    manifest_id = manifest or selected_case.pipeline_manifest_id
    if manifest_id not in manifests:
        raise typer.BadParameter(f"Manifest {manifest_id!r} not found in {name}'s manifests.json.")
    if manifest_id != selected_case.pipeline_manifest_id:
        selected_case = selected_case.model_copy(update={"pipeline_manifest_id": manifest_id})

    resolved_manifest = manifests[manifest_id]
    top_k = resolved_manifest.retrieval_manifest.candidate_depth
    token_budget = resolved_manifest.packing_manifest.evidence_budget_tokens

    case_result = run_diagnostic_case(selected_case, manifests, top_k=top_k, token_budget=token_budget)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"{selected_case.case_id}.diagnostic.json").write_text(
        json.dumps(build_diagnostic_report(case_result), indent=2, default=str)
    )
    (output_dir / f"{selected_case.case_id}.diagnostic_labels.json").write_text(
        json.dumps(build_diagnostic_labels_template(case_result), indent=2)
    )

    trace = case_result.imported_answer.trace
    console.print(f"Case {selected_case.case_id!r} under manifest {manifest_id!r}:")
    console.print(f"  retrieved: {len(trace.retrieval_candidates or [])}")
    console.print(f"  packed: {len(trace.packed_context_items or [])}")
    console.print(f"  omitted: {len(trace.omitted_context_items or [])}")
    console.print(f"  llm_call_count: {case_result.imported_answer.metrics.llm_call_count}")
    console.print(f"Wrote diagnostic report/labels template to {output_dir}")


_DEMO_PASSAGES = [
    "The recommended starting dosage of metformin hydrochloride extended-release is 500 mg orally once daily "
    "with the evening meal.",
    "Increase the dose in increments of 500 mg weekly on the basis of glycemic control and tolerability, up to a "
    "maximum of 2,000 mg once daily with the evening meal.",
    "Metformin hydrochloride extended-release tablets are contraindicated in patients with severe renal "
    "impairment (eGFR below 30 mL/min/1.73 m2).",
]
_DEMO_RUNS = [
    (
        "What is the starting dose of metformin extended-release?",
        "The starting dose is 500 mg once daily with the evening meal. [1]",
    ),
    ("What is the maximum dose of metformin extended-release?", "The maximum dose is 2,550 mg per day. [2]"),
    ("Can metformin extended-release be used in severe renal impairment?", "[3]"),
    (
        "Is metformin extended-release contraindicated in renal impairment?",
        "Yes, metformin extended-release is contraindicated in renal impairment. [3]",
    ),
]


def _send_demo(url: str) -> None:
    import time
    import urllib.request

    for _ in range(120):  # wait for the server
        try:
            urllib.request.urlopen(url + "/live/config", timeout=2)
            break
        except OSError:
            time.sleep(0.5)
    from wittgenstein import monitor

    monitor.configure(url=url, source="demo pipeline")
    for q, a in _DEMO_RUNS:
        monitor.record(q, _DEMO_PASSAGES, a)


@app.command("serve")
def serve(
    port: int = typer.Option(8100, help="Port for the local interface and API."),
    host: str = typer.Option("127.0.0.1", help="Keep 127.0.0.1 unless you mean to expose it."),
    open_browser: bool = typer.Option(False, "--open/--no-open", help="Also open the interface in a browser tab."),
    audit_dir: Path = typer.Option(None, help="Where the audit feed is kept (default ~/.wittgenstein)."),
    demo: bool = typer.Option(False, help="Send four example audits so the feed isn't empty."),
) -> None:
    """Run Wittgenstein locally: the interface, the API, and the feed of audits from your
    own pipeline (connect it with `import wittgenstein.monitor as wm; wm.instrument()`)."""
    import os
    import threading
    import webbrowser

    import uvicorn

    from wittgenstein import service

    if audit_dir is not None:
        os.environ["WITTGENSTEIN_HOME"] = str(audit_dir.expanduser())
    service.apply_config_env()
    home = service.home()
    home.mkdir(parents=True, exist_ok=True)
    os.environ["WITTGENSTEIN_AUDIT_DIR"] = str(home)
    os.environ.setdefault("WITTGENSTEIN_DATABASE_URL", f"sqlite:///{home / 'wittgenstein.db'}")
    url = f"http://{'127.0.0.1' if host in {'0.0.0.0', '::'} else host}:{port}"
    console.print(f"[bold]Wittgenstein[/bold] running on {url}")
    console.print("See checked answers:  [cyan]wittgenstein watch[/cyan] (terminal)  ·  "
                  "[cyan]wittgenstein app[/cyan] (window)")  # fmt: skip
    _print_connect(url, feed=False)
    if open_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url + "/#/pipeline")).start()
    if demo:
        threading.Thread(target=_send_demo, args=(url,), daemon=True).start()
    uvicorn.run("wittgenstein.api.app:app", host=host, port=port, log_level="warning")


autostart_app = typer.Typer(help="Start Wittgenstein when you log in.")
app.add_typer(autostart_app, name="autostart")


@app.command("start")
def start_cmd(
    port: int = typer.Option(None, help="Port (default 8100, or the last one used)."),
    openai_upstream: str = typer.Option(
        None, help="Where the OpenAI-compatible proxy forwards (e.g. http://localhost:11434 for Ollama)."
    ),
    anthropic_upstream: str = typer.Option(None, help="Where the Anthropic proxy forwards."),
) -> None:
    """Run Wittgenstein in the background, independent of this terminal."""
    from wittgenstein import service

    service.save_config({"openai_upstream": openai_upstream, "anthropic_upstream": anthropic_upstream})
    _, message = service.start(port)
    console.print(message)
    if service.responding():
        _print_connect(service.url())


@app.command("stop")
def stop_cmd() -> None:
    """Stop the background server."""
    from wittgenstein import service

    console.print(service.stop())


@app.command("status")
def status_cmd() -> None:
    """Whether it's running, where, and how many audits the feed holds."""
    from wittgenstein import service

    st = service.status()
    console.print(f"[bold]{'Running' if st['running'] else 'Not running'}[/bold]  {st['url']}")
    console.print(f"Starts at login: {'yes' if st['autostart'] else 'no'}")
    if st["audits"] is not None:
        console.print(f"Audits in the feed: {st['audits']}  ({st['url']}/#/pipeline)")
    console.print(
        f"Proxy upstreams: OpenAI-compatible {st['openai_upstream']}  ·  Anthropic {st['anthropic_upstream']}"
    )
    console.print(f"Data: {st['home']}")


@autostart_app.command("enable")
def autostart_enable_cmd(port: int = typer.Option(None)) -> None:
    from wittgenstein import service

    console.print(service.autostart_enable(port))


@autostart_app.command("disable")
def autostart_disable_cmd() -> None:
    from wittgenstein import service

    console.print(service.autostart_disable())


@app.command(
    "run",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def run_cmd(
    ctx: typer.Context,
    source: str = typer.Option(None, help="Name for this program in the feed (default: the script's name)."),
) -> None:
    """Run a Python program with its LangChain / LlamaIndex pipeline audited, e.g.
    `wittgenstein run python app.py`. Nothing is installed into the program's environment."""
    from wittgenstein import service

    if not ctx.args:
        console.print("Usage: wittgenstein run python your_app.py")
        raise typer.Exit(2)
    raise typer.Exit(service.run(list(ctx.args), source))


@app.command("measure-model")
def measure_model_cmd(
    provider: str = typer.Option("local", help="local | claude | openai: the answer-writing model to measure."),
    yes: bool = typer.Option(False, "--yes", help="Don't ask before sending paid requests."),
    show: bool = typer.Option(False, help="Show the last measurement instead of measuring again."),
) -> None:
    """Measure how many passages the answering model uses reliably (fictional probes with
    near-identical decoys; graded by value, no model judges). The pipeline then trims or
    flags context beyond that. Every probe and answer is saved for audit."""
    from wittgenstein import service
    from wittgenstein.live import generator_profile as gp
    from wittgenstein.live.generate import ProviderError, get_provider

    service.apply_config_env()
    try:
        p = get_provider(provider)
    except (ProviderError, ValueError) as e:
        console.print(f"Can't use {provider!r}: {e}")
        raise typer.Exit(1) from e
    model = p.info.model_identifier or provider
    if show:
        prof = gp.load(p.info.provider_id, model)
        if prof is None:
            console.print(f"Not measured yet: {model}")
            raise typer.Exit(1)
    else:
        n = len(gp.probes()) * len(gp.SIZES)
        if provider in {"claude", "openai"} and not yes:
            typer.confirm(f"This sends {n} requests to {model} (billed to your API key). Continue?", abort=True)
        console.print(f"Measuring {model}: {n} generations…")
        prof = gp.measure(gp.with_provider(p), p.info.provider_id, model)
        path = gp.save(prof)
        console.print(f"Saved with every probe and answer: {path}")
    table = Table(title=f"{model} — measured {prof.measured_at[:16]}")
    table.add_column("Passages")
    table.add_column("Correct")
    table.add_column("Wrong passage")
    table.add_column("No answer")
    for s_ in prof.sizes:
        k = str(s_)
        table.add_row(k, f"{prof.accuracy[k]:.0%}", f"{prof.wrong_passage[k]:.0%}", f"{prof.no_answer[k]:.0%}")
    console.print(table)
    console.print(f"[bold]Reliable size: {prof.reliable_passages} passages[/bold]  ({prof.rule})")
    if prof.note:
        console.print(prof.note)


def _ensure_running(port: int | None) -> str:
    from wittgenstein import service

    if not service.responding(port):
        console.print("Starting Wittgenstein in the background…")
        ok, message = service.start(port)
        if not service.responding(port):
            console.print(message)
            raise typer.Exit(1)
    return service.url(port)


@app.command("watch")
def watch_cmd(
    port: int = typer.Option(None, help="Port of the server (default: the last one used, or 8100)."),
    plain: bool = typer.Option(False, help="Print one line per answer instead of the interactive view."),
) -> None:
    """Watch your RAG app's answers being checked, in the terminal (starts the server if needed)."""
    import contextlib

    from wittgenstein.tui import watch

    with contextlib.suppress(KeyboardInterrupt):
        watch(_ensure_running(port), plain=plain)


@app.command("app")
def app_cmd(
    port: int = typer.Option(None, help="Port of the server (default: the last one used, or 8100)."),
) -> None:
    """Open Wittgenstein in its own window (needs `pip install "wittgenstein-rag[app]"`)."""
    try:
        import webview
    except ImportError:
        console.print('The window needs one more package:  [cyan]pip install "wittgenstein-rag[app]"[/cyan]')
        console.print("Or use the terminal view:  [cyan]wittgenstein watch[/cyan]")
        raise typer.Exit(1) from None
    base = _ensure_running(port)
    webview.create_window("Wittgenstein", base + "/#/pipeline", width=1280, height=860, min_size=(720, 520))
    webview.start()
    console.print("Window closed; Wittgenstein keeps running in the background (`wittgenstein stop` to stop it).")


def _print_connect(url: str, feed: bool = True) -> None:
    if feed:
        console.print("See checked answers:  [cyan]wittgenstein watch[/cyan] (terminal)  ·  "
                      "[cyan]wittgenstein app[/cyan] (window)")  # fmt: skip
    console.print("Connect an app:")
    console.print("  Python (LangChain / LlamaIndex):  [cyan]wittgenstein run python app.py[/cyan]")
    console.print(f"  Any language, OpenAI-compatible:  base URL [cyan]{url}/proxy/openai/v1[/cyan]")
    console.print(f"  Any language, Anthropic:          base URL [cyan]{url}/proxy/anthropic[/cyan]")


if __name__ == "__main__":
    app()
