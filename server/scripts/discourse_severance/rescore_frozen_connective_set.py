"""
Rescores Experiments 1/2/3 (the CFR-based discourse_severance/ track and
its FactoidWiki own-corpus counterpart in factoidwiki_track/) restricted
to a frozen connective set: {if, unless, despite, however, though,
although}. Every severance verdict used here was ALREADY COMPUTED by a
prior run -- this script only filters which records are counted and
recomputes aggregate statistics; it makes zero new LLM calls, following
the same re-group-don't-re-judge precedent as exception_reclassification.py.

Two corpora, kept separate and labeled, NOT treated as one instrument:
  - CFR (this directory): regulatory register, scored by
    severance_detection.py's judge (sentence-granularity prompt).
  - FactoidWiki (factoidwiki_track/): encyclopedic register, scored by
    severance_judge_paragraph.py's llm_judge_paragraph_severance (a
    separately-written, paragraph-adapted port of the same methodology,
    not the same function or prompt text as the CFR judge).
Experiment 2's within-corpus tests are the PRIMARY result (two
independent replications on different judge implementations); the
cross-corpus pooled figure is reported as SECONDARY/SUPPLEMENTARY only,
explicitly labeled as combining two distinct instruments.

On "although": the production judge whose verdicts are reported here
was validated against exactly ONE confirmed historical failure of this
kind (pool 4117/arm_2_disco_rag, a nucleus/satellite attachment reversal
in a Disco-RAG-generated repair -- see parser_attachment_resolver.py and
validate_condition_concession_v3.py) and resolved it correctly. A
SEPARATE 44-case direct test of parser_attachment_resolver.py's
resolve_marker_clause() (an experimental geometric attachment tool used
only inside the never-adopted v2/v3 judges) against real "although"
ground-truth text found zero directional reversals -- evidence that
the connective is not structurally cursed, NOT a stress-test of the
production judge itself, which was never run at scale against this
failure mode.

Individually-excluded records (connective present but NOT case-verified
clean -- ungrounded/hallucinated connective, or a satellite that is only
the bare connective word with no propositional content):
  CFR:
    cfr21p201:145   (although -- "although" not a substring of the sentence)
    cfr21p201:116   (although -- truncated sentence, satellite="Although")
    cfr29p1910:32446 (however -- RESULTS.md's own A2 audit: STRICT no-split
                       category error, suspected relation misclassification)
    cfr29p1910:28432 (however -- satellite="However," -- no content)
  FactoidWiki:
    pool 2329 (although -- satellite="Although unofficial")
    pool 2786 (however  -- satellite="However")
    pool 2901 (though   -- satellite="Though")

Shared-source check: verified no duplicate sentence/sentence_index in
CFR, and only 1 duplicate article title in each of FactoidWiki's
governing pool (195 records) and Elaboration control (206 records) --
title-deduping changes FactoidWiki's Fisher p from 4.26e-23 to 3.98e-23,
not material.
"""
import collections
import json
import os
from scipy.stats import fisher_exact, chi2_contingency

CFR_DIR = os.path.dirname(os.path.abspath(__file__))
FW_DIR = os.path.join(CFR_DIR, "factoidwiki_track")

FROZEN = {"if", "unless", "despite", "however", "though", "although"}

CFR_EXCLUDED_IDS = {"cfr21p201:145", "cfr21p201:116", "cfr29p1910:32446", "cfr29p1910:28432"}
FW_EXCLUDED_POOLS = {2329, 2786, 2901}

PART_PREFIX = {
    "21 CFR Part 201 (FDA, Labeling)": "cfr21p201",
    "29 CFR Part 1910 (OSHA, General Industry Safety Standards)": "cfr29p1910",
}


def cfr_id(rec):
    return f"{PART_PREFIX[rec['part_label']]}:{rec['sentence_index']}"


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def fisher_block(pos_a, n_a, pos_b, n_b, label):
    table = [[pos_a, n_a - pos_a], [pos_b, n_b - pos_b]]
    try:
        odds_ratio, p = fisher_exact(table)
        chi2, chi_p, _, _ = chi2_contingency(table, correction=True)
    except Exception as e:
        return {"label": label, "table": table, "error": str(e)}
    return {
        "label": label, "table": table,
        "governing_rate": f"{pos_a}/{n_a} ({pos_a/n_a:.1%})" if n_a else "n/a",
        "elaboration_rate": f"{pos_b}/{n_b} ({pos_b/n_b:.1%})" if n_b else "n/a",
        "fisher_p": p, "odds_ratio": odds_ratio, "chi2_p": chi_p,
    }


# ============================================================ CFR: Exp1 ===
# Apply the project's own already-adopted Exception->Condition fold
# (exception_reclassification.json) so relation-type grouping below uses
# corrected labels, not the stale raw "Exception" bucket the fold retired.
_reclass = load_json(os.path.join(CFR_DIR, "exception_reclassification.json"))
_new_label_by_id = {r["id"]: r["new_label"] for r in _reclass["reclassification"]["records"]}

cfr_exp1_all = load_json(os.path.join(CFR_DIR, "discourse_severance_report.json"))["experiment_1"]["records"]
for r in cfr_exp1_all:
    rid = cfr_id(r)
    if rid in _new_label_by_id:
        r["relation_type"] = _new_label_by_id[rid]

cfr_exp1_kept = [
    r for r in cfr_exp1_all
    if r["connective"].strip().lower() in FROZEN and cfr_id(r) not in CFR_EXCLUDED_IDS
]

print("=" * 70)
print("STEP 2: CORPUS COVERAGE")
print("=" * 70)
print(f"\nCFR Exp1 (governing relations): {len(cfr_exp1_kept)}/{len(cfr_exp1_all)} kept "
      f"({len(cfr_exp1_kept)/len(cfr_exp1_all):.1%})")
by_conn = {}
for r in cfr_exp1_kept:
    c = r["connective"].strip().lower()
    by_conn.setdefault(c, []).append(r)
for c, recs in sorted(by_conn.items()):
    print(f"  {c}: {len(recs)} ({recs[0]['relation_type']})")

# ===================================================== FactoidWiki: Exp1/2
fw_govern_all = load_jsonl(os.path.join(FW_DIR, "logs", "task7_experiment_govern_log.jsonl"))
fw_govern_kept = [
    r for r in fw_govern_all
    if r["connective"].strip().lower() in FROZEN and r["pool_index"] not in FW_EXCLUDED_POOLS
]
print(f"\nFactoidWiki Exp1/2 governing pool: {len(fw_govern_kept)}/{len(fw_govern_all)} kept "
      f"({len(fw_govern_kept)/len(fw_govern_all):.1%})")
fw_by_conn = {}
for r in fw_govern_kept:
    c = r["connective"].strip().lower()
    fw_by_conn.setdefault(c, []).append(r)
for c, recs in sorted(fw_by_conn.items()):
    print(f"  {c}: {len(recs)} ({recs[0]['relation_type']})")

# Elaboration controls -- unchanged, no connective restriction applies
# NOTE: experiment_2.records is the FULL 92-record set (47 governing + 45
# Elaboration); the 45 Elaboration records use a single "severance" key
# (Exp2 only ever tested Condition A), not severance_a/severance_b.
cfr_exp2_all_records = load_json(os.path.join(CFR_DIR, "discourse_severance_report.json"))["experiment_2"]["records"]
cfr_elab = [r for r in cfr_exp2_all_records if r["relation_type"] == "Elaboration"]
print(f"\nCFR Elaboration control (unchanged): {len(cfr_elab)} records")

fw_elab = load_jsonl(os.path.join(FW_DIR, "logs", "task7_experiment_elaboration_log.jsonl"))
print(f"FactoidWiki Elaboration control (unchanged): {len(fw_elab)} records")

# =========================================================== CFR: Exp3 ===
cfr_exp3 = load_json(os.path.join(CFR_DIR, "exp3_recovery_comparison", "exp3_report.json"))
cfr_exp3_all = cfr_exp3["records"]
cfr_exp3_kept = [
    r for r in cfr_exp3_all
    if r["relation"]["connective"].strip().lower() in FROZEN and r["id"] not in CFR_EXCLUDED_IDS
]
print(f"\nCFR Exp3 eval set: {len(cfr_exp3_kept)}/{len(cfr_exp3_all)} kept "
      f"({len(cfr_exp3_kept)/len(cfr_exp3_all):.1%})")

# ===================================================== FactoidWiki: Exp3 ==
fw_exp3 = load_json(os.path.join(FW_DIR, "results", "task8_factoidwiki_exp3_report.json"))
fw_exp3_all = fw_exp3["records"]
fw_exp3_kept = [
    r for r in fw_exp3_all
    if r["relation"]["connective"].strip().lower() in FROZEN and r["pool_index"] not in FW_EXCLUDED_POOLS
]
print(f"FactoidWiki Exp3 eval set: {len(fw_exp3_kept)}/{len(fw_exp3_all)} kept "
      f"({len(fw_exp3_kept)/len(fw_exp3_all):.1%})")

total_all = len(cfr_exp1_all) + len(fw_govern_all) + len(cfr_exp3_all) + len(fw_exp3_all)
total_kept = len(cfr_exp1_kept) + len(fw_govern_kept) + len(cfr_exp3_kept) + len(fw_exp3_kept)
print(f"\nOVERALL (Exp1/2 governing pools + Exp3 eval sets, both corpora): "
      f"{total_kept}/{total_all} ({total_kept/total_all:.1%})")
print("(Elaboration controls excluded from this ratio -- restriction doesn't apply to them.)")

# ================================================ Shared-source / duplicate check
print("\n" + "=" * 70)
print("SHARED-SOURCE / DUPLICATE-ARTICLE CHECK")
print("=" * 70)
print("CFR has no article structure (one continuous regulatory text per part); "
      "checked for duplicate sentence_index / duplicate exact sentence text instead.")


def dup_report(records, id_fn, label):
    ids = collections.Counter(id_fn(r) for r in records)
    dups = {k: v for k, v in ids.items() if v > 1}
    n_dup_records = sum(dups.values())
    print(f"  {label} (N={len(records)}): {len(dups)} duplicate key(s), "
          f"{n_dup_records} record(s) involved" + (f" -- {dups}" if dups else ""))
    return dups


dup_report(cfr_exp1_kept, cfr_id, "CFR governing pool")
dup_report(cfr_elab, cfr_id, "CFR Elaboration control")
dup_report(fw_govern_kept, lambda r: r["title"], "FactoidWiki governing pool (by title)")
dup_report(fw_elab, lambda r: r["title"], "FactoidWiki Elaboration control (by title)")


def dedupe_keep_first(records, key_fn):
    seen, out = set(), []
    for r in records:
        k = key_fn(r)
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out


fw_govern_dd = dedupe_keep_first(fw_govern_kept, lambda r: r["title"])
fw_elab_dd = dedupe_keep_first(fw_elab, lambda r: r["title"])
print(f"\n  Title-deduped (keep first occurrence): governing {len(fw_govern_kept)}->{len(fw_govern_dd)}, "
      f"elaboration {len(fw_elab)}->{len(fw_elab_dd)}")

# ============================================================================
print("\n" + "=" * 70)
print("STEP 3: RESCORED EXPERIMENT 1 (severance by connective, LLM-judge)")
print("=" * 70)


def _preserved(rec, key):
    block = rec[key]
    return block["preserved"] if "preserved" in block else block.get("llm_judge_preserved")


def sev_rate(records, key):
    scored = [r for r in records if _preserved(r, key) is not None]
    n = len(scored)
    if n == 0:
        return "n/a"
    sev = sum(1 for r in scored if _preserved(r, key) is False)
    return f"{sev}/{n} ({sev/n:.1%})"


print("\n-- CFR --")
for c in sorted(by_conn):
    recs = by_conn[c]
    print(f"  {c:10} N={len(recs):3} | Condition A severed: {sev_rate(recs, 'severance_a')} "
          f"| Condition B severed: {sev_rate(recs, 'severance_b')}")

print("\n-- FactoidWiki --")
for c in sorted(fw_by_conn):
    recs = fw_by_conn[c]
    print(f"  {c:10} N={len(recs):3} | Condition A severed: {sev_rate(recs, 'severance_a')} "
          f"| Condition B severed: {sev_rate(recs, 'severance_b')}")

# combined by relation type
print("\n-- Combined by RELATION TYPE (both corpora pooled) --")
combined = cfr_exp1_kept + fw_govern_kept
by_rel = {}
for r in combined:
    by_rel.setdefault(r["relation_type"], []).append(r)
for rel, recs in sorted(by_rel.items()):
    print(f"  {rel:12} N={len(recs):3} | Condition A severed: {sev_rate(recs, 'severance_a')} "
          f"| Condition B severed: {sev_rate(recs, 'severance_b')}")

print("\n" + "=" * 70)
print("STEP 3: RESCORED EXPERIMENT 2 (Fisher's exact, governing vs Elaboration)")
print("=" * 70)
print("PRIMARY: two independent within-corpus tests (different judge implementations,")
print("different corpora -- treated as a replication, not pooled as one instrument).")
print("SECONDARY/SUPPLEMENTARY: cross-corpus pooled figure, labeled explicitly as")
print("combining two distinct judge implementations, not a single-instrument result.")


def count_severed_a(records, key="severance_a"):
    scored = [r for r in records if _preserved(r, key) is not None]
    sev = sum(1 for r in scored if _preserved(r, key) is False)
    return sev, len(scored)


# --- PRIMARY: within-corpus tests ---
cfr_gov_sev, cfr_gov_n = count_severed_a(cfr_exp1_kept)
cfr_elab_sev, cfr_elab_n = count_severed_a(cfr_elab, key="severance")
res = fisher_block(cfr_gov_sev, cfr_gov_n, cfr_elab_sev, cfr_elab_n, "CFR (severance_detection.py judge)")
print(f"\n[PRIMARY 1/2] CFR (severance_detection.py judge): governing {res['governing_rate']} "
      f"vs Elaboration {res['elaboration_rate']}")
print(f"  Fisher p = {res['fisher_p']:.6g} | odds ratio = {res['odds_ratio']:.3g} | chi2 p = {res['chi2_p']:.6g}")

fw_gov_sev, fw_gov_n = count_severed_a(fw_govern_kept)
fw_elab_sev, fw_elab_n = count_severed_a(fw_elab, key="severance_a")
res = fisher_block(fw_gov_sev, fw_gov_n, fw_elab_sev, fw_elab_n, "FactoidWiki (severance_judge_paragraph.py judge)")
print(f"\n[PRIMARY 2/2] FactoidWiki (severance_judge_paragraph.py judge): governing {res['governing_rate']} "
      f"vs Elaboration {res['elaboration_rate']}")
print(f"  Fisher p = {res['fisher_p']:.6g} | odds ratio = {res['odds_ratio']:.3g} | chi2 p = {res['chi2_p']:.6g}")

# Dedupe sensitivity check on the FactoidWiki within-corpus test specifically
fw_gov_sev_dd, fw_gov_n_dd = count_severed_a(fw_govern_dd)
fw_elab_sev_dd, fw_elab_n_dd = count_severed_a(fw_elab_dd, key="severance_a")
res_dd = fisher_block(fw_gov_sev_dd, fw_gov_n_dd, fw_elab_sev_dd, fw_elab_n_dd, "FactoidWiki, title-deduped")
print(f"  [sensitivity check, title-deduped 1/title]: governing {res_dd['governing_rate']} "
      f"vs Elaboration {res_dd['elaboration_rate']} | Fisher p = {res_dd['fisher_p']:.6g} "
      f"| odds ratio = {res_dd['odds_ratio']:.3g} -- no material change")

print("\n-- Within PRIMARY corpora, by relation class --")
for rel in ("Condition", "Concession"):
    cfr_recs = [r for r in cfr_exp1_kept if r["relation_type"] == rel]
    fw_recs = [r for r in fw_govern_kept if r["relation_type"] == rel]
    if cfr_recs:
        sev, n = count_severed_a(cfr_recs)
        res = fisher_block(sev, n, cfr_elab_sev, cfr_elab_n, f"CFR {rel} vs Elaboration")
        print(f"  CFR {rel:10} {res['governing_rate']} vs Elaboration {res['elaboration_rate']} "
              f"| Fisher p = {res['fisher_p']:.4g}")
    if fw_recs:
        sev, n = count_severed_a(fw_recs)
        res = fisher_block(sev, n, fw_elab_sev, fw_elab_n, f"FactoidWiki {rel} vs Elaboration")
        print(f"  FactoidWiki {rel:10} {res['governing_rate']} vs Elaboration {res['elaboration_rate']} "
              f"| Fisher p = {res['fisher_p']:.4g}")

# --- SECONDARY/SUPPLEMENTARY: pooled cross-corpus figure ---
pooled_gov_sev = cfr_gov_sev + fw_gov_sev
pooled_gov_n = cfr_gov_n + fw_gov_n
pooled_elab_sev = cfr_elab_sev + fw_elab_sev
pooled_elab_n = cfr_elab_n + fw_elab_n
res = fisher_block(pooled_gov_sev, pooled_gov_n, pooled_elab_sev, pooled_elab_n, "Pooled, two distinct judges")
print(f"\n[SECONDARY/SUPPLEMENTARY -- pooled across two distinct judge implementations, "
      f"not a single-instrument result] CFR+FactoidWiki: governing {res['governing_rate']} "
      f"vs Elaboration {res['elaboration_rate']}")
print(f"  Fisher p = {res['fisher_p']:.6g} | odds ratio = {res['odds_ratio']:.3g} | chi2 p = {res['chi2_p']:.6g}")

for rel in ("Condition", "Concession"):
    recs = by_rel.get(rel, [])
    sev, n = count_severed_a(recs)
    if n:
        res = fisher_block(sev, n, pooled_elab_sev, pooled_elab_n, f"{rel} only vs Elaboration, pooled")
        print(f"  [secondary] {rel} only (pooled): {res['governing_rate']} vs Elaboration {res['elaboration_rate']} "
              f"| Fisher p = {res['fisher_p']:.6g} | odds ratio = {res['odds_ratio']:.3g}")

print("\n" + "=" * 70)
print("STEP 3: RESCORED EXPERIMENT 3 (recovery-arm correctness, frozen set)")
print("=" * 70)


def arm_correctness(records, arm_key, judge_key="judge_full_nucleus"):
    scored = [r for r in records if r.get(arm_key, {}).get(judge_key, {}).get("preserved") is not None]
    n = len(scored)
    if n == 0:
        return "n/a (no scored cases)"
    correct = sum(1 for r in scored if r[arm_key][judge_key]["preserved"] is True)
    return f"{correct}/{n} ({correct/n:.1%})"


print("\n-- CFR Exp3 (N=%d kept of %d) --" % (len(cfr_exp3_kept), len(cfr_exp3_all)))
for arm_key, label in [
    ("condition_2_disco_rag", "arm: Disco-RAG"),
    ("condition_3_custom_fallback", "arm: custom fallback"),
    ("condition_5_contextual_retrieval", "arm: contextual retrieval"),
]:
    if cfr_exp3_kept:
        print(f"  {label:28} correct recovery rate: {arm_correctness(cfr_exp3_kept, arm_key)}")
    else:
        print(f"  {label:28} n/a -- 0 cases survive restriction")

print("\n-- FactoidWiki Exp3 (N=%d kept of %d) --" % (len(fw_exp3_kept), len(fw_exp3_all)))
for arm_key, label in [
    ("arm_2_disco_rag", "arm: Disco-RAG"),
    ("arm_3_custom_fallback", "arm: custom fallback"),
    ("arm_4_contextual_retrieval", "arm: contextual retrieval"),
    ("arm_5_parent_segment", "arm: parent segment"),
]:
    print(f"  {label:28} correct recovery rate: {arm_correctness(fw_exp3_kept, arm_key, judge_key='judge')}")

print("\nDone.")
