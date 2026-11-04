"""Task 3: resolve the Propositionizer prompt-format ambiguity.

The model's own README documents the inference prompt as
    "Title: {title}. Section: {section}. Content: {content}"
(WITH a "Content:" label). The released training-data card
(chentong00/propositionizer-wiki-data) documents its OWN `sources` field,
in prose, as
    "Title: {title}. Section: {section}. {content}"
(NO "Content:" label) -- inconsistent with the model README.

Task 2's download (download_data.py) already surfaced a directly
relevant empirical fact: the training-data card's prose description of
its own field does not match the field's actual content. A full scan of
all 42,857 rows in the real downloaded train.jsonl found the literal
substring ". Content: " in 100% of `sources` values (42857/42857, zero
exceptions) -- i.e. the real training data is itself formatted WITH the
"Content:" label, matching the model README, not the card's prose about
itself. See README.md in this directory for the full write-up.

This script adds the second, independently-requested piece of evidence:
actually RUNNING the model with both candidate formats on the same 10
real paragraphs (get_format_test_slice(), disjoint from the paragraphs
used in Tasks 4/5) and comparing output sanity -- does either format
fail to produce a well-formed JSON-array-of-strings more often, or
degrade in some other way (truncation, empty output, obviously
incomplete lists)?

Usage:
    venv/bin/python server/scripts/discourse_severance/factoidwiki_track/resolve_prompt_format.py
"""

import json
import os
import time

from download_data import get_format_test_slice, shuffled_records
from env_utils import RESULTS_DIR, ensure_dirs
from propositionizer import build_prompt, generate_propositions, load_model_and_tokenizer

DEVICE = "cpu"  # device comparison is Task 4's job; Task 3 only needs one consistent device
MAX_NEW_TOKENS = 512
OUTPUT_JSON = os.path.join(RESULTS_DIR, "task3_prompt_format_resolution.json")


def run_one_record(model, tokenizer, record):
    """Runs both candidate formats on one record. Returns a result dict
    with everything needed for both the aggregate stats and the
    side-by-side qualitative report.
    """
    prompt_with = build_prompt(record["title"], record["section"], record["content"],
                                with_content_label=True)
    prompt_without = build_prompt(record["title"], record["section"], record["content"],
                                   with_content_label=False)

    gen_with = generate_propositions(model, tokenizer, prompt_with, DEVICE, MAX_NEW_TOKENS)
    gen_without = generate_propositions(model, tokenizer, prompt_without, DEVICE, MAX_NEW_TOKENS)

    return {
        "title": record["title"],
        "section": record["section"],
        "content": record["content"],
        "n_ground_truth_targets": len(record["targets"]),
        "ground_truth_targets": record["targets"],
        "with_label": {"prompt": prompt_with, **gen_with},
        "without_label": {"prompt": prompt_without, **gen_without},
    }


def summarize(results):
    def stats_for(key):
        n = len(results)
        n_parsed = sum(1 for r in results if r[key]["parsed"] is not None)
        n_empty_list = sum(1 for r in results if r[key]["parsed"] == [])
        n_nonempty_valid = sum(1 for r in results if r[key]["parsed"])
        elapsed = [r[key]["elapsed_seconds"] for r in results]
        prop_counts = [len(r[key]["parsed"]) for r in results if r[key]["parsed"]]
        return {
            "n": n,
            "n_parsed_as_json_list_of_str": n_parsed,
            "n_parse_failures": n - n_parsed,
            "n_parsed_but_empty_list": n_empty_list,
            "n_nonempty_valid": n_nonempty_valid,
            "parse_success_rate": n_parsed / n if n else None,
            "nonempty_rate": n_nonempty_valid / n if n else None,
            "avg_elapsed_seconds": sum(elapsed) / len(elapsed) if elapsed else None,
            "avg_proposition_count": sum(prop_counts) / len(prop_counts) if prop_counts else None,
            "avg_ground_truth_count": sum(r["n_ground_truth_targets"] for r in results) / len(results),
        }

    return {
        "with_label": stats_for("with_label"),
        "without_label": stats_for("without_label"),
    }


def print_side_by_side(results, n=10):
    for i, r in enumerate(results[:n]):
        print(f"\n{'=' * 90}")
        print(f"[{i}] Title: {r['title']!r} | Section: {r['section']!r}")
        print(f"Content ({len(r['content'])} chars): {r['content'][:300]}"
              f"{'...' if len(r['content']) > 300 else ''}")
        print(f"Ground truth ({r['n_ground_truth_targets']} propositions): "
              f"{r['ground_truth_targets']}")
        for key, label in (("with_label", "WITH 'Content:' label (model README format)"),
                            ("without_label", "WITHOUT 'Content:' label (dataset-card prose format)")):
            g = r[key]
            n_props = len(g["parsed"]) if g["parsed"] else 0
            print(f"\n  -- {label} -- elapsed={g['elapsed_seconds']:.2f}s")
            print(f"     parse_error: {g['parse_error']}")
            print(f"     parsed ({n_props} propositions): {g['parsed']}")
            if g["parsed"] is None:
                print(f"     RAW decoded output: {g['decoded'][:500]!r}")


def decide_winner(summary):
    w, wo = summary["with_label"], summary["without_label"]
    reasons = []
    if w["parse_success_rate"] != wo["parse_success_rate"]:
        winner = "with_label" if w["parse_success_rate"] > wo["parse_success_rate"] else "without_label"
        reasons.append(
            f"parse success rate differs: with_label={w['parse_success_rate']:.0%} "
            f"vs without_label={wo['parse_success_rate']:.0%}"
        )
        return winner, reasons
    if w["nonempty_rate"] != wo["nonempty_rate"]:
        winner = "with_label" if w["nonempty_rate"] > wo["nonempty_rate"] else "without_label"
        reasons.append(
            f"non-empty output rate differs: with_label={w['nonempty_rate']:.0%} "
            f"vs without_label={wo['nonempty_rate']:.0%}"
        )
        return winner, reasons
    # Tied on both hard quantitative metrics -- fall back to the
    # empirical training-data-format evidence from download_data.py: the
    # model was fine-tuned exclusively on WITH-label-formatted sources
    # (100% of 42,857 real rows), so with_label matches the training
    # distribution and without_label is out-of-distribution.
    reasons.append(
        "tied on parse-success and non-empty rate; deciding on the "
        "corroborating evidence that 100% of the model's own real "
        "training rows (42,857/42,857) use the WITH-'Content:'-label "
        "format, so that format matches the training distribution and "
        "the without-label format is out-of-distribution for this model."
    )
    return "with_label", reasons


def main():
    ensure_dirs()
    print("Loading model for Task 3 (prompt-format resolution) ...")
    model, tokenizer = load_model_and_tokenizer(DEVICE)

    records = get_format_test_slice(shuffled_records())
    print(f"\nRunning both prompt formats on {len(records)} real paragraphs "
          f"(device={DEVICE}, max_new_tokens={MAX_NEW_TOKENS}) ...")

    results = []
    t0 = time.time()
    for i, record in enumerate(records):
        print(f"  [{i + 1}/{len(records)}] {record['title']!r} ...", flush=True)
        results.append(run_one_record(model, tokenizer, record))
    elapsed_total = time.time() - t0
    print(f"\nDone in {elapsed_total:.1f}s ({elapsed_total / (2 * len(records)):.2f}s/call avg, "
          f"{2 * len(records)} calls total).")

    summary = summarize(results)
    winner, reasons = decide_winner(summary)

    print("\n" + "#" * 90)
    print("SUMMARY")
    print("#" * 90)
    print(json.dumps(summary, indent=2))
    print(f"\nWINNER: {winner}")
    for reason in reasons:
        print(f"  - {reason}")

    print("\n" + "#" * 90)
    print("SIDE-BY-SIDE EXAMPLES (all 10)")
    print("#" * 90)
    print_side_by_side(results, n=len(results))

    output = {
        "device": DEVICE,
        "max_new_tokens": MAX_NEW_TOKENS,
        "n_records": len(records),
        "elapsed_total_seconds": elapsed_total,
        "summary": summary,
        "winner": winner,
        "winner_reasons": reasons,
        "records": results,
    }
    with open(OUTPUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2, ensure_ascii=False)
    print(f"\nWrote {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
