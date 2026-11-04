"""Rebuild Experiment 3's Concession-relevant dangerous-failure labels
using the validated content-overlap check (min of nucleus/satellite
lemma-overlap with the repaired propositions, 70% threshold primary,
60% reported alongside) instead of any of the three failed QA patterns
("does S prevent N?", two-part A/B contrast-legibility, open-ended
synthesis).

Refined check (spot-check found and fixed two real measurement issues
before this was trusted -- see the spot-check report):
  - quote-normalization: spaCy lemmatizes a word differently depending
    on whether it's inside quote marks (confirmed on "medicated" ->
    lemma 'medicated' in quotes vs 'medicate' unquoted) -- strip quote
    characters before parsing.
  - connective words excluded from the target-lemma set -- counting the
    connective itself (despite/however/though/...) as required "content"
    was circular with the old hand-audit's own severed criterion
    ("presented as unconnected parallel facts" implies connective
    absence), and inflated the apparent discrimination.
Even after both fixes, the discrimination against the hand-audited
subset remained significant (70% threshold: 65.7% vs 88.7%, Fisher
p=0.0074) -- see the spot-check report for the full before/after table.

Applies to ALL 96 Concession records x 5 generative arms in
task8_factoidwiki_exp3_report.json (480 arm-instances), not just the
117-case hand-audited subset used for validation -- this is the actual
"rebuild," not another validation pass.

Usage:
    venv/bin/python server/scripts/discourse_severance/factoidwiki_track/rebuild_exp3_concession_content_check.py
"""
import json
import os
import re

import spacy

HERE = os.path.dirname(os.path.abspath(__file__))
REPORT_PATH = os.path.join(HERE, "results", "task8_factoidwiki_exp3_report.json")
OUT_PATH = os.path.join(HERE, "results", "exp3_concession_content_check_rebuild.json")

nlp = spacy.load("en_core_web_sm")

CONNECTIVES = {"despite", "however", "although", "though", "while", "but", "rather",
               "nevertheless", "nonetheless", "yet", "whereas"}
GENERATIVE_ARMS = ["arm_1_no_elicitation", "arm_2_disco_rag", "arm_3_custom_fallback",
                    "arm_4_contextual_retrieval", "arm_5_parent_segment"]
PRIMARY_THRESHOLD = 0.70
SECONDARY_THRESHOLD = 0.60


def normalize_quotes(text):
    return re.sub(r'["“”‘’\']', '', text)


def content_lemmas(text, min_len=4):
    doc = nlp(normalize_quotes(text))
    return {t.lemma_.lower() for t in doc if t.is_alpha and len(t.lemma_) >= min_len
            and not t.is_stop and t.lemma_.lower() not in CONNECTIVES}


def overlap_ratio(target_text, propositions):
    target_lemmas = content_lemmas(target_text)
    if not target_lemmas:
        return None
    claims_lemmas = content_lemmas(" ".join(propositions))
    return len(target_lemmas & claims_lemmas) / len(target_lemmas)


def main():
    report = json.load(open(REPORT_PATH, encoding="utf-8"))
    concession_records = [r for r in report["records"] if r["relation_type"] == "Concession"]
    print(f"Concession records: {len(concession_records)}")

    out_records = []
    n_scored = 0
    n_skipped = 0
    for rec in concession_records:
        rel = rec["relation"]
        out_rec = {"pool_index": rec.get("pool_index"), "title": rec.get("title"),
                   "relation": rel, "arms": {}}
        for arm_key in GENERATIVE_ARMS:
            arm = rec.get(arm_key, {})
            props = arm.get("propositions")
            old_judge = arm.get("judge", {})
            if not props:
                n_skipped += 1
                out_rec["arms"][arm_key] = {"content_check": None, "old_judge_preserved": old_judge.get("preserved")}
                continue
            nuc_ov = overlap_ratio(rel["nucleus"], props)
            sat_ov = overlap_ratio(rel["satellite"], props)
            if nuc_ov is None or sat_ov is None:
                n_skipped += 1
                out_rec["arms"][arm_key] = {"content_check": None, "old_judge_preserved": old_judge.get("preserved")}
                continue
            n_scored += 1
            min_ov = min(nuc_ov, sat_ov)
            out_rec["arms"][arm_key] = {
                "nuc_overlap": round(nuc_ov, 3), "sat_overlap": round(sat_ov, 3), "min_overlap": round(min_ov, 3),
                "dangerous_failure_70": min_ov < PRIMARY_THRESHOLD,
                "dangerous_failure_60": min_ov < SECONDARY_THRESHOLD,
                "old_judge_preserved": old_judge.get("preserved"),
            }
        out_records.append(out_rec)

    json.dump(out_records, open(OUT_PATH, "w", encoding="utf-8"), indent=2)
    print(f"Scored arm-instances: {n_scored} | skipped (no propositions/no content): {n_skipped}")
    print(f"Saved to {OUT_PATH}\n")

    print("=" * 78)
    print("Per-arm summary: NEW content-check dangerous-failure rate vs OLD judge-based rate")
    print("=" * 78)
    for arm_key in GENERATIVE_ARMS:
        scored = [rec["arms"][arm_key] for rec in out_records if rec["arms"][arm_key].get("min_overlap") is not None]
        if not scored:
            continue
        n = len(scored)
        n_new_70 = sum(1 for a in scored if a["dangerous_failure_70"])
        n_new_60 = sum(1 for a in scored if a["dangerous_failure_60"])
        old_scored = [a for a in scored if a["old_judge_preserved"] is not None]
        n_old_failure = sum(1 for a in old_scored if a["old_judge_preserved"] is False)
        both_scored = [a for a in scored if a["old_judge_preserved"] is not None]
        n_agree = sum(1 for a in both_scored if a["dangerous_failure_70"] == (a["old_judge_preserved"] is False))
        print(f"\n{arm_key} (n={n}):")
        print(f"  NEW dangerous-failure (70% threshold): {n_new_70}/{n} ({n_new_70/n:.1%})")
        print(f"  NEW dangerous-failure (60% threshold): {n_new_60}/{n} ({n_new_60/n:.1%})")
        if old_scored:
            print(f"  OLD judge dangerous-failure (preserved=False): {n_old_failure}/{len(old_scored)} "
                  f"({n_old_failure/len(old_scored):.1%})")
            print(f"  Agreement between OLD judge and NEW 70% check: {n_agree}/{len(both_scored)} "
                  f"({n_agree/len(both_scored):.1%})")


if __name__ == "__main__":
    main()
