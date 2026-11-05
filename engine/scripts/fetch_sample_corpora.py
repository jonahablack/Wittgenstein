"""Fetch public-domain sample documents into data/live_corpora/ (gitignored), one folder
per corpus with a meta.json title. Run: uv run python scripts/fetch_sample_corpora.py

Samples:
- austen: Pride and Prejudice (Project Gutenberg #1342; public domain in the USA).
- fda-labels: three FDA prescription drug labels from openFDA (US government works,
  public domain), pinned by SPL set id and converted to Markdown with the label's own
  numbered sections ("## 5 Warnings and Precautions", "### 5.1 Lactic Acidosis") so
  section cross-references like "(5.1)" can be resolved. Text is otherwise verbatim
  apart from whitespace normalization and paragraph breaks.
"""

from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "data" / "live_corpora"
UA = {"User-Agent": "wittgenstein-sample-fetch"}

GUTENBERG = {
    "austen": {
        "title": "Pride and Prejudice (Jane Austen)",
        "files": {"pride-and-prejudice.txt": "https://www.gutenberg.org/cache/epub/1342/pg1342.txt"},
        "license": "Public domain in the USA (Project Gutenberg eBook #1342).",
    },
}

#: SPL set ids pinned for reproducibility (single-ingredient prescription labels).
FDA_LABELS = {
    "metformin": "05999192-ebc6-4198-bd1e-f46abbfb4f8a",
    "warfarin": "598e5e2e-9264-8371-e063-6394a90aaf18",
    "amoxicillin": "102c62ca-da20-4866-84a8-e3513824af4a",
}
#: Held out from all check development: used only to evaluate (scripts/evaluate_checks.py).
FDA_LABELS_HELDOUT = {
    "lisinopril": "0e6364a4-6d66-4151-8197-d45e2a762895",
    "atorvastatin": "09cb8375-075c-47e8-a4eb-8ac667ed849e",
    "levothyroxine": "13e03769-9a4f-497f-9afa-95bf525090b3",
}
MAIN_SECTIONS = [
    "boxed_warning",
    "indications_and_usage",
    "dosage_and_administration",
    "dosage_forms_and_strengths",
    "contraindications",
    "warnings_and_cautions",
    "adverse_reactions",
    "drug_interactions",
    "use_in_specific_populations",
    "overdosage",
]
#: Subsections sometimes delivered only as separate fields.
POPULATION_SUBSECTIONS = ["pregnancy", "lactation", "nursing_mothers", "pediatric_use", "geriatric_use"]
_CONNECTORS = {"and", "of", "in", "with", "the", "for", "to", "or", "on", "a", "an"}


def _get(url: str) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return r.read()


def _clean(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"(?<=[A-Z]) N/A\b", "", text)  # the labels' literal "N/A" placeholders
    return re.sub(r"\(\s*(\d{1,2}(?:\.\d{1,2})?)\s*\)", r"(\1)", text)  # "( 5.1 )" -> "(5.1)"


def _paragraphs(body: str, per: int = 3) -> list[str]:
    out: list[str] = []
    for part in re.split(r"\s(?=•)", body):
        sents = re.split(r"(?<=[.!?])\s+(?=[A-Z•(])", part.strip())
        for i in range(0, len(sents), per):
            chunk = " ".join(sents[i : i + per]).strip()
            if chunk:
                out.append(chunk)
    return out


def _title_run(tokens: list[str]) -> int:
    """Number of leading tokens forming a Title Case heading."""
    n = 0
    while (
        n < len(tokens)
        and n < 9
        and (tokens[n][:1].isupper() or tokens[n].isdigit() or tokens[n].lower() in _CONNECTORS)
    ):
        n += 1
    if n < len(tokens) and n > 1 and tokens[n][:1].islower():
        n -= 1  # the last capitalized word starts the first sentence ("There have been")
    while n > 1 and tokens[n - 1].lower() in _CONNECTORS:
        n -= 1
    return max(n, 1)


def _section_markdown(text: str) -> list[str]:
    text = _clean(text)
    lines: list[str] = []
    head = re.match(r"^(\d{1,2}) ((?:[A-Z][A-Z/&,\-]*\s)+)", text + " ")
    if head:
        words = head.group(2).split()
        title = " ".join(w.lower() if w.lower() in _CONNECTORS else w.capitalize() for w in words)
        lines.append(f"## {head.group(1)} {title}")
        text = text[head.end() :].strip()
    elif text.upper().startswith("WARNING"):
        lines.append("## Boxed Warning")
    # Subsection headings: "<section>.<n> Title" -- only numbers belonging to *this*
    # section count, so doses like "2.5 mg" or cross-section mentions can't split it.
    major = head.group(1) if head else r"\d{1,2}"
    pieces = re.split(rf"(?<![(\d])\s(?={major}\.\d{{1,2}}\s[A-Z])", " " + text)
    for piece in (p.strip() for p in pieces):
        if not piece:
            continue
        m = re.match(r"^(\d{1,2}\.\d{1,2})\s(.*)$", piece)
        if m:
            tokens = m.group(2).split()
            n = _title_run(tokens)
            lines.append(f"### {m.group(1)} {' '.join(tokens[:n])}")
            piece = " ".join(tokens[n:])
        lines.extend(_paragraphs(piece))
    return lines


def label_markdown(label: dict, name: str) -> str:
    of = label.get("openfda", {})
    generic = (of.get("generic_name") or [name])[0].lower()
    eff = label.get("effective_time", "")
    date = f"{eff[:4]}-{eff[4:6]}-{eff[6:8]}" if len(eff) == 8 else "unknown date"
    out = [
        f"# {generic.capitalize()}: FDA prescribing information",
        f"Source: openFDA drug label, SPL set id {label.get('set_id')}, effective {date}. US government work "
        "(public domain). Converted to Markdown for the Wittgenstein demo; not for clinical use.",
    ]
    present: set[str] = set()
    for field in MAIN_SECTIONS:
        for text in label.get(field, []):
            lines = _section_markdown(text)
            present.update(re.findall(r"^### (\d{1,2}\.\d{1,2})", "\n".join(lines), flags=re.M))
            out.extend(lines)
    for field in POPULATION_SUBSECTIONS:
        for text in label.get(field, []):
            num = re.match(r"\s*(\d{1,2}\.\d{1,2})", text)
            if num and num.group(1) not in present:
                out.extend(_section_markdown(text))
                present.add(num.group(1))
    return "\n\n".join(out) + "\n"


def main() -> None:
    for folder, spec in GUTENBERG.items():
        d = ROOT / folder
        d.mkdir(parents=True, exist_ok=True)
        for name, url in spec["files"].items():
            target = d / name
            if not target.exists():
                target.write_bytes(_get(url))
                print(f"fetched {target}")
        (d / "meta.json").write_text(json.dumps({"title": spec["title"], "license": spec["license"]}, indent=2))

    for folder, labels, title in [
        ("fda-labels", FDA_LABELS, "FDA drug labels: metformin, warfarin, amoxicillin"),
        (
            "fda-labels-heldout",
            FDA_LABELS_HELDOUT,
            "FDA drug labels (held out): lisinopril, atorvastatin, levothyroxine",
        ),
    ]:
        d = ROOT / folder
        d.mkdir(parents=True, exist_ok=True)
        for name, set_id in labels.items():
            url = f'https://api.fda.gov/drug/label.json?search=set_id:"{set_id}"&limit=1'
            label = json.loads(_get(url))["results"][0]
            (d / f"{name}.md").write_text(label_markdown(label, name))
            print(f"wrote {d / name}.md")
        meta = {
            "title": title,
            "license": "US government works (openFDA), public domain. Demo only; not for clinical use.",
            "set_ids": labels,
        }
        (d / "meta.json").write_text(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
