"""Task 6 downstream: deterministic sample selection for the required
human/AI spot-check of Stage-2 output (README.md's "Validate the
validator" section).

Per this track's established practice (see task5b's spot-check
methodology in results/task5b_revised_precision_report.json), the sample
selection itself must be reproducible and not hand-picked -- this script
is the record of exactly which pool_indices were reviewed and how they
were chosen, so the spot-check numbers in results/task6_two_stage_pipeline_report.json
can be traced back to a concrete, auditable sample rather than an
unlogged ad hoc read. If a group is small enough, ALL of it is reviewed
(same choice task5b made at 53/71 hits, judged not excessive); otherwise
a fixed-seed random sample is drawn (seed=13, matching this project's
SPLIT_SEED convention in download_data.py).

Usage:
    venv/bin/python server/scripts/discourse_severance/factoidwiki_track/spot_check_sample.py \\
        --group confirmed --relation Condition
    venv/bin/python server/scripts/discourse_severance/factoidwiki_track/spot_check_sample.py \\
        --group rejected --relation Concession --sample-size 15
"""

import argparse
import json
import os
import random

from env_utils import LOGS_DIR

STAGE2_LOG = os.path.join(LOGS_DIR, "task6_stage2_log.jsonl")
SAMPLE_SEED = 13  # matches download_data.SPLIT_SEED's documented convention


def load_stage2_log(path=STAGE2_LOG):
    """De-dup by pool_index, keeping the LAST write -- same convention as
    run_two_stage_pipeline.py's _load_by_pool_index. Without this, a
    pool_index that errored and was later fixed via --retry-stage2-errors
    (appended as a SECOND line for the same index, per that function's
    docstring) would show up TWICE here: once as the stale pre-retry
    "_error" entry and once as the real post-retry verdict -- silently
    double-counting it and letting a phantom errored copy leak into a
    "rejected" sample alongside its own corrected version.
    """
    records = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    by_index = {r["pool_index"]: r for r in records}
    return [by_index[k] for k in sorted(by_index)]


def select_sample(records, relation, group, sample_size=None, seed=SAMPLE_SEED):
    pool = [
        r for r in records
        if r["relation_type"] == relation
        and (r["stage2"].get("confirmed") if group == "confirmed" else not r["stage2"].get("confirmed"))
    ]
    pool = sorted(pool, key=lambda r: r["pool_index"])  # stable order before sampling
    if sample_size is None or sample_size >= len(pool):
        return pool, "all"
    rng = random.Random(seed)
    sampled = rng.sample(pool, sample_size)
    return sorted(sampled, key=lambda r: r["pool_index"]), f"random sample, seed={seed}"


def format_record(r):
    lines = [
        "=" * 100,
        f"pool_index={r['pool_index']}  title={r['title']!r}  relation_type={r['relation_type']}  "
        f"stage2_confirmed={r['stage2'].get('confirmed')}  model_stated_verdict={r['stage2'].get('model_stated_verdict')}",
        f"content: {r['content']}",
        f"nucleus:    {r['nucleus']!r}",
        f"satellite:  {r['satellite']!r}",
        f"connective: {r['connective']!r}",
        f"stage1 rationale: {r.get('rationale')!r}",
    ]
    checks = r["stage2"].get("checks") or {}
    for k, v in checks.items():
        if v:
            lines.append(f"  {k}: applies={v.get('applies')} | {v.get('reason')}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--group", choices=["confirmed", "rejected"], required=True)
    parser.add_argument("--relation", choices=["Condition", "Concession"], required=True)
    parser.add_argument("--sample-size", type=int, default=None,
                         help="omit to review the ENTIRE group")
    parser.add_argument("--stage2-log", type=str, default=STAGE2_LOG)
    args = parser.parse_args()

    records = load_stage2_log(args.stage2_log)
    sample, method = select_sample(records, args.relation, args.group, args.sample_size)

    print(f"# {args.relation} / {args.group}: {len(sample)} record(s) selected via [{method}]")
    print(f"# pool_indices: {[r['pool_index'] for r in sample]}")
    for r in sample:
        print(format_record(r))


if __name__ == "__main__":
    main()
