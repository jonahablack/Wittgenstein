// Numbers shown on the About page. Each block names the run that produced it; the raw
// results stay local (research/, not in the repo), the scripts that make them are in
// engine/scripts/.

/** engine/scripts/baseline_checks.py, planted errors on held-out FDA labels
 *  (lisinopril, atorvastatin, levothyroxine). Detection = share flagged for review.
 *  Baseline thresholds are set so 5% of the 240 correct answers are flagged. */
export const PLANTED = {
  correct: 240,
  falseAlarms: { similarity: 0.05, nli: 0.05, wittgenstein: 0 },
  nliAtDefault: 0.761, // NLI judge at the usual 0.5 cut-off, all errors
  rows: [
    { error: "Dose changed", example: "500 mg → 1050 mg", n: 60, similarity: 0.05, nli: 1.0, wittgenstein: 1.0 },
    { error: "Unit changed", example: "mg → mcg", n: 60, similarity: 0.133, nli: 0.983, wittgenstein: 1.0 },
    { error: "Patient group dropped", example: "“in patients with eGFR < 30” removed", n: 30, similarity: 0.167, nli: 0.067, wittgenstein: 1.0 },
    { error: "Condition dropped", example: "“if …” clause removed", n: 17, similarity: 0.235, nli: 0.235, wittgenstein: 1.0 },
    { error: "Negation flipped", example: "“not” added or removed", n: 60, similarity: 0.067, nli: 0.983, wittgenstein: 0.983 },
    { error: "Hedge strengthened", example: "“may” → “must”", n: 60, similarity: 0.033, nli: 0.717, wittgenstein: 0.967 },
    { error: "Cited to another drug", example: "right sentence, wrong passage", n: 60, similarity: 1.0, nli: 1.0, wittgenstein: 0.933 },
  ],
  all: { n: 347, similarity: 0.248, nli: 0.827, wittgenstein: 0.98 },
};

/** research/red-team/2026-11-05: Qwen2-1.5B-Instruct, local, over six FDA labels at once,
 *  40 held-out questions, each answer labelled against the label text (by Claude, not
 *  by clinicians). Checker column: the code as it ran on these answers. */
export const REAL = {
  model: "Qwen2-1.5B-Instruct",
  total: 40,
  outcomes: [
    { key: "correct", label: "Correct", n: 18 },
    { key: "error", label: "Wrong content", n: 11 },
    { key: "empty", label: "No real answer", n: 9 },
    { key: "cite", label: "Right content, wrong citation", n: 2 },
  ],
  problemsWithCitation: { k: 14, n: 22 },
  table: [
    { group: "Wrong content", n: 11, similarity: 4, nli: 10, wittgenstein: 10 },
    { group: "No real answer (e.g. just “[2]”)", n: 9, similarity: 0, nli: 1, wittgenstein: 9 },
    { group: "Right content, wrong citation", n: 2, similarity: 1, nli: 1, wittgenstein: 1 },
    { group: "Correct (false alarms)", n: 18, similarity: 1, nli: 4, wittgenstein: 4 },
  ],
};

/** Direct probes of cross-encoder/nli-deberta-v3-xsmall (the base model agrees). */
export const NLI_FOOLED = [
  {
    claim: "The maximum daily dose of metformin extended-release is 2,550 mg.",
    source: "2,550 mg is the maximum for immediate-release. (Extended-release: 2,000 mg.)",
    truth: "Contradicted",
    entailment: 0.99,
  },
  {
    claim: "With erythromycin, do not exceed 20 mg of atorvastatin.",
    source: "The 20 mg limit is stated for clarithromycin or itraconazole.",
    truth: "Not supported",
    entailment: 0.89,
  },
  {
    claim: "Keep the INR between 2.5 and 3.0.",
    source: "Target INR range, 2.0 to 3.0.",
    truth: "Contradicted",
    entailment: 0.97,
  },
];

/** Counterfactual probe: a value in the passages changed, same model asked again. */
export const PROBE = {
  total: 29,
  parts: [
    { key: "follows", label: "Followed the edited passage", n: 20 },
    { key: "inconclusive", label: "Rewrote the answer (unstable)", n: 8 },
    { key: "ignored", label: "Kept the old value", n: 1 },
  ],
};

/** Published evidence (research/medical-education, research/case-studies). */
export const LITERATURE = [
  {
    stat: "50–90%",
    text: "of LLM answers to medical questions were not fully supported by the sources they cited.",
    source: "Wu et al., Nature Communications 2025",
    href: "https://pmc.ncbi.nlm.nih.gov/articles/PMC12003634/",
  },
  {
    stat: "17–33%",
    text: "of queries to commercial legal research tools built on retrieval produced hallucinations.",
    source: "Stanford RegLab & HAI, 2024",
    href: "https://arxiv.org/pdf/2405.20362",
  },
  {
    stat: "2×",
    text: "as many omissions in LLM-written clinical summaries as in physicians’ summaries.",
    source: "JAMA Internal Medicine, 2025",
    href: "https://jamanetwork.com/journals/jamainternalmedicine/fullarticle/2833236",
  },
];
