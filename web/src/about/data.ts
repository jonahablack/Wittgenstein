// Numbers for the About page's one chart: engine/scripts/baseline_checks.py, planted
// errors in sentences from held-out FDA labels (lisinopril, atorvastatin, levothyroxine).
// The entailment judge (cross-encoder/nli-deberta-v3-xsmall) has its threshold set to
// flag 5% of 240 correct answers; Wittgenstein flagged none of them. Raw results stay
// local (research/red-team/2026-11-05_baselines.json).

export const PATTERNS = [
  { pattern: "Negation flipped", example: "“not” added or removed", n: 60, judge: 0.983, wittgenstein: 0.983 },
  { pattern: "Hedge strengthened", example: "“may” → “must”", n: 60, judge: 0.717, wittgenstein: 0.967 },
  { pattern: "Condition dropped", example: "“if …” clause removed", n: 17, judge: 0.235, wittgenstein: 1.0 },
  { pattern: "Patient group dropped", example: "“in patients with …” removed", n: 30, judge: 0.067, wittgenstein: 1.0 },
];

export const SOURCES = [
  {
    text: "Revisiting Negation Blindness in Large Language Models, EMNLP 2025.",
    href: "https://aclanthology.org/2025.emnlp-main.1088",
    label: "aclanthology.org/2025.emnlp-main.1088",
  },
  {
    text: "SemEval Task: NLI4CT, 2023–2024.",
    href: "https://arxiv.org/abs/2305.02993",
    label: "arxiv.org/abs/2305.02993",
  },
  {
    text: "Leung et al., Classifying and Addressing the Diversity of Errors in Retrieval-Augmented Generation Systems, 2025.",
    href: "https://arxiv.org/abs/2510.13975",
    label: "arxiv.org/abs/2510.13975",
  },
  {
    text: "Datla et al., Policy→Tests, AAAI 2026.",
    href: "https://arxiv.org/abs/2512.04408",
    label: "arxiv.org/abs/2512.04408",
  },
  {
    text: "Fox et al., LLM Judges Verify Presence, Not Absence: Omission Blindness in AI Clinical Notes and What Recovers It, 2026.",
    href: "https://arxiv.org/abs/2608.31016",
    label: "arxiv.org/abs/2608.31016",
  },
];
