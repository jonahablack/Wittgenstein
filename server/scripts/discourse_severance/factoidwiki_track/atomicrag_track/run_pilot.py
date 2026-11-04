"""Pilot: run AtomicRAG's OpenIE atomization (atomicrag_openie_adapter.py)
on a small (default 20) sample of the EXISTING FactoidWiki relation-labeled
paragraphs already logged by ../run_experiment_1_2.py
(../logs/task7_experiment_govern_log.jsonl,
../logs/task7_experiment_elaboration_log.jsonl -- same source paragraphs
the Propositionizer track scored, read from their `content` field), and
print the resulting knowledge fragments for hand inspection before
committing to the full 272+206-paragraph run.

Per this project's established practice (pilot before scaling, e.g.
../measure_throughput.py / ../spot_check_sample.py precedents): this is a
real, paid run of a small sample, not a stub -- its purpose is to catch a
broken prompt/parse/config BEFORE spending the full run's budget, not to
avoid spending money at all.

Usage:
    venv/bin/python server/scripts/discourse_severance/factoidwiki_track/atomicrag_track/run_pilot.py
    venv/bin/python server/scripts/discourse_severance/factoidwiki_track/atomicrag_track/run_pilot.py --n 20
"""

import argparse
import json
import os
import random
import sys

ATOMICRAG_TRACK_DIR = os.path.dirname(os.path.abspath(__file__))
FACTOIDWIKI_TRACK_DIR = os.path.dirname(ATOMICRAG_TRACK_DIR)
if ATOMICRAG_TRACK_DIR not in sys.path:
    sys.path.insert(0, ATOMICRAG_TRACK_DIR)
if FACTOIDWIKI_TRACK_DIR not in sys.path:
    sys.path.insert(0, FACTOIDWIKI_TRACK_DIR)

from env_utils import load_server_env  # noqa: E402  (reused directly from ../env_utils.py -- atomicrag_track is nested INSIDE factoidwiki_track, not a sibling of it, so this is intra-track reuse of the .env-loading helper, not the cross-track import env_utils.py's own docstring warns against; RESULTS_DIR/LOGS_DIR/CACHE_DIR below are still defined locally, not imported, so this track's outputs stay in its own subtree)

load_server_env()

import atomicrag_openie_adapter as adapter  # noqa: E402

GOVERN_LOG = os.path.join(FACTOIDWIKI_TRACK_DIR, "logs", "task7_experiment_govern_log.jsonl")
ELABORATION_LOG = os.path.join(FACTOIDWIKI_TRACK_DIR, "logs", "task7_experiment_elaboration_log.jsonl")
CACHE_DIR = os.path.join(ATOMICRAG_TRACK_DIR, "atomicrag_llm_cache")
RESULTS_DIR = os.path.join(ATOMICRAG_TRACK_DIR, "results")
PILOT_REPORT = os.path.join(RESULTS_DIR, "pilot_report.json")

PILOT_SEED = 13  # matches this project's fixed-seed sampling convention (download_data.SPLIT_SEED etc.)


def _load_jsonl(path):
    records = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def build_pilot_sample(n):
    """Deterministic sample split roughly evenly across govern (Condition +
    Concession) and elaboration-control records, so the pilot sees both
    the governing-relation paragraphs the experiment cares about AND the
    control-type paragraphs, not just one.
    """
    govern = _load_jsonl(GOVERN_LOG)
    elaboration = _load_jsonl(ELABORATION_LOG)

    n_govern = (n + 1) // 2
    n_elab = n - n_govern

    rng = random.Random(PILOT_SEED)
    govern_sample = sorted(rng.sample(govern, min(n_govern, len(govern))), key=lambda r: r["pool_index"])
    elab_sample = sorted(rng.sample(elaboration, min(n_elab, len(elaboration))), key=lambda r: r["pool_index"])

    sample = []
    for rec in govern_sample:
        sample.append({"key": f"govern-{rec['pool_index']}", "relation_type": rec["relation_type"],
                        "pool_index": rec["pool_index"], "content": rec["content"]})
    for rec in elab_sample:
        sample.append({"key": f"elab-{rec['pool_index']}", "relation_type": rec["relation_type"],
                        "pool_index": rec["pool_index"], "content": rec["content"]})
    return sample


def _sanity_flags(propositions, content):
    """Cheap, non-LLM sanity checks (mirrors this project's convention of
    catching mechanical failure modes without spending a judge call --
    see ../candidate_prefilter.py's rationale). Not a pass/fail gate, just
    flags surfaced for the human inspecting pilot output.
    """
    flags = []
    if not propositions:
        flags.append("EMPTY: zero knowledge fragments produced")
    if any(len(p.strip()) < 8 for p in propositions):
        flags.append("SUSPICIOUSLY_SHORT: a fragment under 8 chars")
    if len(propositions) > 25:
        flags.append(f"SUSPICIOUSLY_MANY: {len(propositions)} fragments for one paragraph")
    total_frag_chars = sum(len(p) for p in propositions)
    if total_frag_chars < 0.2 * len(content):
        flags.append("LOW_COVERAGE: fragments total far shorter than source paragraph (possible truncation/garbling)")
    return flags


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=20, help="pilot sample size (default 20)")
    args = parser.parse_args()

    os.makedirs(RESULTS_DIR, exist_ok=True)
    os.makedirs(CACHE_DIR, exist_ok=True)

    sample = build_pilot_sample(args.n)
    print(f"Pilot sample: {len(sample)} paragraphs "
          f"({sum(1 for r in sample if r['relation_type'] in ('Condition', 'Concession'))} governing, "
          f"{sum(1 for r in sample if r['relation_type'] == 'Elaboration')} elaboration-control).")

    id_to_content = {r["key"]: r["content"] for r in sample}
    print(f"Calling AtomicRAG OpenIE (batch_unified_openie) on {len(id_to_content)} paragraphs "
          f"-- {2 * len(id_to_content)} real LLM calls (NER + unified extraction per paragraph)...")
    atomization = adapter.run_atomicrag_atomization(id_to_content, save_dir=CACHE_DIR)

    rows = []
    n_flagged = 0
    total_prompt_tokens = 0
    total_completion_tokens = 0
    for r in sample:
        result = atomization[r["key"]]
        flags = _sanity_flags(result["atomicrag_propositions"], r["content"])
        if flags:
            n_flagged += 1
        total_prompt_tokens += result["atomicrag_prompt_tokens"]
        total_completion_tokens += result["atomicrag_completion_tokens"]
        rows.append({**r, **result, "sanity_flags": flags})

        print(f"\n--- {r['key']} ({r['relation_type']}) ---")
        print(f"Paragraph: {r['content'][:200]}{'...' if len(r['content']) > 200 else ''}")
        print(f"AtomicRAG fragments ({result['n_atomicrag_propositions']}):")
        for p in result["atomicrag_propositions"]:
            print(f"  - {p}")
        if result["atomicrag_error"]:
            print(f"  ERROR: {result['atomicrag_error']}")
        if flags:
            print(f"  FLAGS: {flags}")

    report = {
        "n_pilot_paragraphs": len(sample),
        "n_flagged": n_flagged,
        "total_prompt_tokens": total_prompt_tokens,
        "total_completion_tokens": total_completion_tokens,
        "n_real_llm_calls": 2 * len(sample),
        "attribution_statement": adapter.ATTRIBUTION_STATEMENT,
        "rows": rows,
    }
    with open(PILOT_REPORT, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)

    print("\n" + "#" * 90)
    print(f"PILOT DONE: {len(sample)} paragraphs, {n_flagged} flagged by cheap sanity checks, "
          f"{2 * len(sample)} real LLM calls, {total_prompt_tokens} prompt + {total_completion_tokens} "
          "completion tokens.")
    print(f"Wrote {PILOT_REPORT}")


if __name__ == "__main__":
    main()
