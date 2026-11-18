# Admissions review

`POST /live/admissions/check` (or `/v1/admissions/check` with an API key) checks an
AI-written summary of one application against the application itself, sentence by
sentence, and returns what a reviewer should look at. Code: `wittgenstein/admissions.py`.

```json
{
  "documents": {"experiences.md": "...", "personal_statement.md": "...", "letters.md": "..."},
  "summary": "Applicant 0417 has 1,200 hours of clinical experience as an EMT [1]. ...",
  "citations": ["experiences.md#Emergency Medical Technician", "academics.md"]
}
```

`citations` are what the summary's `[n]` markers point to, in order: a file name, or
`file#Section heading` for a `## ` section (a heading prefix is enough).

What it adds to the usual answer checks (each goes to a person; nothing is acted on):

| Flag | When |
|---|---|
| `protected_characteristic` | The summary mentions race, ethnicity or national origin; says whether the file states it or the summary inferred it |
| `source_figures_disagree` | The file gives different figures for the same activity (e.g. hours in the experiences entry vs. an essay) |
| `context_omitted` | The summary reports a setback the file explains elsewhere, without the explanation |

The number in "Applicant 0417" is read as the file's label, not a claim. Search-side
checks (query coverage, retriever agreement) are skipped: they don't apply to a whole file.

Deliberately not done: scoring, ranking or recommending applicants; guessing whether an
essay was written with AI; inferring any demographic attribute.

Synthetic example files: `data/fixtures/admissions_synthetic/` (fictional applicants).
