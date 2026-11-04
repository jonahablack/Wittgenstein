"""Task 4: measure real Propositionizer throughput.

Runs the Propositionizer on 20 FRESH source paragraphs (disjoint from
the 10 used in Task 3's format resolution -- see
download_data.get_throughput_slice), using the prompt format Task 3
resolved, with max_new_tokens=512 passed explicitly (the documented
generation_config.json gotcha). Reports real wall-clock time per
paragraph (mean/median/min/max) on CPU, and -- if
torch.backends.mps.is_available() -- re-runs a subset on MPS and
compares, rather than assuming MPS helps (this project's prior research
flagged incomplete MPS op coverage for T5-style models historically).

Usage:
    venv/bin/python server/scripts/discourse_severance/factoidwiki_track/measure_throughput.py
"""

import json
import os
import statistics

from download_data import get_throughput_slice, shuffled_records
from env_utils import RESULTS_DIR, ensure_dirs
from propositionizer import build_prompt, generate_propositions, load_model_and_tokenizer, move_model_to_device

# Resolved by Task 3 -- see README.md "Task 3" section and
# results/task3_prompt_format_resolution.json for the evidence. Kept as
# an explicit module-level constant (not re-derived at runtime) so this
# script's behavior is legible on its own, per this track's fail-fast/
# no-hidden-magic convention.
WITH_CONTENT_LABEL = True  # Task 3 winner: WITH "Content:" label (model README format)

MAX_NEW_TOKENS = 512
N_MPS_COMPARISON = 5  # how many of the 20 to re-run on MPS for the CPU-vs-MPS comparison
OUTPUT_JSON = os.path.join(RESULTS_DIR, "task4_throughput.json")


def run_pass(model, tokenizer, records, device, label):
    results = []
    for i, record in enumerate(records):
        prompt = build_prompt(record["title"], record["section"], record["content"],
                               with_content_label=WITH_CONTENT_LABEL)
        gen = generate_propositions(model, tokenizer, prompt, device=device,
                                     max_new_tokens=MAX_NEW_TOKENS)
        status = "OK" if gen["parsed"] is not None else f"PARSE_FAIL({gen['parse_error']})"
        print(f"  [{label} {i + 1}/{len(records)}] {record['title']!r} "
              f"(content_len={len(record['content'])}) -- {gen['elapsed_seconds']:.2f}s -- {status}",
              flush=True)
        results.append({
            "title": record["title"],
            "content_len": len(record["content"]),
            "n_propositions": len(gen["parsed"]) if gen["parsed"] else None,
            **gen,
        })
    return results


def try_mps_pass(model, tokenizer, records):
    """Attempts MPS generation on `records`. Returns (results_or_None,
    note). Deliberately does NOT set PYTORCH_ENABLE_MPS_FALLBACK=1, so an
    op that MPS doesn't support raises a catchable, reportable error here
    rather than silently and invisibly falling back to CPU for that op
    (which would make the timing comparison meaningless without us
    knowing it happened).
    """
    import torch

    if not torch.backends.mps.is_available():
        return None, "torch.backends.mps.is_available() is False on this hardware/torch build."

    try:
        move_model_to_device(model, "mps")
    except Exception as e:
        return None, f"model.to('mps') raised {type(e).__name__}: {e}"

    results = []
    failure_note = None
    for i, record in enumerate(records):
        prompt = build_prompt(record["title"], record["section"], record["content"],
                               with_content_label=WITH_CONTENT_LABEL)
        try:
            gen = generate_propositions(model, tokenizer, prompt, device="mps",
                                         max_new_tokens=MAX_NEW_TOKENS)
        except Exception as e:
            failure_note = (
                f"generate() on device='mps' raised {type(e).__name__} on record "
                f"{i} ({record['title']!r}): {e}"
            )
            print(f"  [MPS {i + 1}/{len(records)}] FAILED -- {failure_note}", flush=True)
            break
        status = "OK" if gen["parsed"] is not None else f"PARSE_FAIL({gen['parse_error']})"
        print(f"  [MPS {i + 1}/{len(records)}] {record['title']!r} -- "
              f"{gen['elapsed_seconds']:.2f}s -- {status}", flush=True)
        results.append({
            "title": record["title"],
            "content_len": len(record["content"]),
            "n_propositions": len(gen["parsed"]) if gen["parsed"] else None,
            **gen,
        })

    move_model_to_device(model, "cpu")  # restore, regardless of outcome, for a clean process state
    if not results:
        return None, failure_note or "no results produced on MPS for an unknown reason"
    return results, failure_note  # failure_note may be a PARTIAL-failure note even with some results


def time_stats(elapsed_list):
    if not elapsed_list:
        return {"n": 0, "mean": None, "median": None, "min": None, "max": None, "stdev": None}
    return {
        "n": len(elapsed_list),
        "mean": statistics.mean(elapsed_list),
        "median": statistics.median(elapsed_list),
        "min": min(elapsed_list),
        "max": max(elapsed_list),
        "stdev": statistics.stdev(elapsed_list) if len(elapsed_list) > 1 else 0.0,
    }


def main():
    ensure_dirs()
    print(f"Task 4: throughput measurement. Resolved format: "
          f"{'WITH' if WITH_CONTENT_LABEL else 'WITHOUT'} 'Content:' label. "
          f"max_new_tokens={MAX_NEW_TOKENS}.")
    print("Loading model on CPU ...")
    model, tokenizer = load_model_and_tokenizer("cpu")

    records = get_throughput_slice(shuffled_records())
    print(f"\n=== CPU pass: {len(records)} fresh paragraphs ===")
    cpu_results = run_pass(model, tokenizer, records, device="cpu", label="CPU")
    cpu_times = [r["elapsed_seconds"] for r in cpu_results]
    cpu_stats = time_stats(cpu_times)
    print(f"\nCPU stats (seconds/paragraph): {cpu_stats}")

    mps_subset = records[:N_MPS_COMPARISON]
    print(f"\n=== MPS comparison: re-running the first {len(mps_subset)} of the same "
          "paragraphs on MPS ===")
    mps_results, mps_note = try_mps_pass(model, tokenizer, mps_subset)
    mps_stats = time_stats([r["elapsed_seconds"] for r in mps_results]) if mps_results else None
    print(f"MPS stats (seconds/paragraph): {mps_stats}")
    print(f"MPS note: {mps_note}")

    matched_cpu_times = cpu_times[:len(mps_subset)]
    comparison = None
    recommendation, recommendation_reason = "cpu", "default -- see notes below"
    if mps_results and len(mps_results) == len(matched_cpu_times):
        comparison = [
            {
                "title": mps_subset[i]["title"],
                "cpu_seconds": matched_cpu_times[i],
                "mps_seconds": mps_results[i]["elapsed_seconds"],
                "mps_faster": mps_results[i]["elapsed_seconds"] < matched_cpu_times[i],
            }
            for i in range(len(matched_cpu_times))
        ]
        cpu_matched_mean = statistics.mean(matched_cpu_times)
        mps_mean = mps_stats["mean"]
        if mps_mean < cpu_matched_mean * 0.8:  # require a clear margin, not just noise
            recommendation = "mps"
            recommendation_reason = (
                f"MPS mean {mps_mean:.2f}s/paragraph vs CPU mean {cpu_matched_mean:.2f}s/paragraph "
                f"on the SAME {len(matched_cpu_times)} paragraphs -- a clear win."
            )
        else:
            recommendation_reason = (
                f"MPS mean {mps_mean:.2f}s/paragraph vs CPU mean {cpu_matched_mean:.2f}s/paragraph "
                f"on the SAME {len(matched_cpu_times)} paragraphs -- not a clear/reliable win "
                "(within noise or actually slower), so CPU is recommended for the full-scale run."
            )
    else:
        recommendation_reason = f"MPS unusable on this hardware/torch build: {mps_note}"

    output = {
        "max_new_tokens": MAX_NEW_TOKENS,
        "with_content_label": WITH_CONTENT_LABEL,
        "cpu": {"per_paragraph": cpu_results, "stats": cpu_stats},
        "mps": {"per_paragraph": mps_results, "stats": mps_stats, "note": mps_note},
        "matched_cpu_vs_mps_comparison": comparison,
        "recommendation": recommendation,
        "recommendation_reason": recommendation_reason,
    }
    with open(OUTPUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2, ensure_ascii=False)

    print("\n" + "#" * 90)
    print(f"DEVICE RECOMMENDATION FOR FULL-SCALE RUN: {recommendation.upper()}")
    print(recommendation_reason)
    if cpu_stats["mean"]:
        for n in (100, 1000, 10000):
            hrs = cpu_stats["mean"] * n / 3600
            print(f"  Illustrative CPU-based estimate: {n:,} paragraphs -> "
                  f"~{hrs:.2f} hours (using CPU mean {cpu_stats['mean']:.2f}s/paragraph, "
                  "single-process, no batching)")
    print("#" * 90)
    print(f"\nWrote {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
