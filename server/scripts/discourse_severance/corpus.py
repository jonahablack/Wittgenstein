"""Corpus acquisition for the discourse-severance experiments.

Fetches real, public-domain U.S. Code of Federal Regulations text from
the eCFR versioner API (no auth needed), strips XML markup down to plain
prose, and sentence-segments it for sampling.

Why CFR text: 21 CFR Part 201 (FDA labeling) and 29 CFR Part 1910 (OSHA
general industry safety) are both known to be dense with conditional/
exception/concession regulatory language ("unless", "except", "provided
that", "in the case of", "although"). This is real government text, not
synthetic examples written to order -- CFR text is a U.S. government
work and is public domain (not copyrightable).

Source: https://www.ecfr.gov/api/versioner/v1/full/{date}/title-{title}.xml?part={part}

Integrity: if the eCFR API is unreachable, this module raises
RuntimeError rather than substituting synthetic text -- same policy as
server/scripts/external_robustness_check.py. Successful fetches are
cached to disk (corpus_cache/) so re-runs don't re-hit the network.
"""

import datetime
import os
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SERVER_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from components.text_extraction import segment_text  # noqa: E402

CACHE_DIR = os.path.join(SCRIPT_DIR, "corpus_cache")

ECFR_FULL_BASE = "https://www.ecfr.gov/api/versioner/v1/full"
DEFAULT_DATE = "2026-08-01"

CFR_PARTS = [
    {
        "title": 21,
        "part": 201,
        "label": "21 CFR Part 201 (FDA, Labeling)",
    },
    {
        "title": 29,
        "part": 1910,
        "label": "29 CFR Part 1910 (OSHA, General Industry Safety Standards)",
    },
]

# Stopwords excluded when comparing "content keyword overlap" between a
# nucleus clause and an atomized claim (used by severance_detection.py,
# defined here since both corpus filtering and severance detection need a
# lightweight "is this word informative" notion).
_STOPWORDS = set(
    """
    the a an of to in on for and or but if unless is are was were be been
    being that this these those which who whom whose with without as at
    by from into onto upon shall must may might should would could will
    not no nor per under over than then also such any all each every
    other another its their his her they them it he she we you your our
    section subpart part paragraph
    """.split()
)


def content_keywords(text, min_len=5):
    """Lowercased alphabetic words of at least `min_len` chars, minus a
    small stopword list. Used as a cheap "did this claim keep talking
    about the same thing" proxy -- see severance_detection.py.
    """
    words = re.findall(r"[A-Za-z]+", text.lower())
    return {w for w in words if len(w) >= min_len and w not in _STOPWORDS}


# --- fetch -------------------------------------------------------------------


def _cache_path(title, part, date):
    return os.path.join(CACHE_DIR, f"title{title}_part{part}_{date}.xml")


def fetch_cfr_part_xml(title, part, date=DEFAULT_DATE, force=False, max_retries=5):
    """Fetch one CFR title/part as raw XML from the eCFR versioner API.

    Caches to disk on first success. Raises RuntimeError (no synthetic
    substitute) if every retry fails -- eCFR is known to occasionally
    return a small HTML "under heavy load" page instead of the real XML,
    which this function detects (real CFR XML is large and begins with
    an XML declaration or a <DIV...> root) and retries rather than
    silently caching garbage.
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_path = _cache_path(title, part, date)
    if os.path.exists(cache_path) and not force:
        with open(cache_path, "r", encoding="utf-8") as fh:
            text = fh.read()
        return text, f"loaded from local cache {cache_path}"

    url = f"{ECFR_FULL_BASE}/{date}/title-{title}.xml?part={part}"
    last_exc = None
    for attempt in range(max_retries):
        req = urllib.request.Request(
            url, headers={"User-Agent": "wittgenstein-discourse-severance/1.0"}
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = resp.read()
            text = raw.decode("utf-8", errors="replace")
            looks_like_cfr_xml = text.strip().startswith("<?xml") or "<DIV" in text[:200]
            if not looks_like_cfr_xml or len(text) < 2000:
                raise RuntimeError(
                    f"non-CFR-XML response (transient eCFR failure?): "
                    f"{text[:200]!r}"
                )
            with open(cache_path, "w", encoding="utf-8") as fh:
                fh.write(text)
            return text, f"downloaded {len(text)} bytes from {url}"
        except (urllib.error.URLError, OSError, TimeoutError, RuntimeError) as exc:
            last_exc = exc
            if attempt < max_retries - 1:
                time.sleep(5 * (attempt + 1))

    raise RuntimeError(
        f"Could not fetch {url} after {max_retries} attempts ({last_exc!r}). "
        "No synthetic substitute is used; re-run when eCFR is reachable, or "
        "fall back to govinfo.gov bulk CFR data and document that source "
        "explicitly if eCFR remains unreachable."
    )


# --- strip markup --------------------------------------------------------


# eCFR's DTD wraps prose in <HEAD> (section/subpart headings) and <P>
# (body paragraphs, which contain nested <PSPACE>, <E>, etc. -- itertext()
# below picks up all nested text regardless of the exact nesting).
_PROSE_TAGS = {"HEAD", "HED", "P", "PSPACE"}


def strip_xml_to_text(xml_text):
    """Parse eCFR XML and return plain prose text, one paragraph/heading
    per line. Uses the standard-library ElementTree parser -- eCFR XML
    uses only numeric/standard XML entities (verified against both parts
    fetched for this experiment), so no external XML/HTML library is
    needed for this step.
    """
    root = ET.fromstring(xml_text)
    lines = []
    for elem in root.iter():
        if elem.tag in _PROSE_TAGS:
            text = "".join(elem.itertext())
            text = re.sub(r"\s+", " ", text).strip()
            if text:
                lines.append(text)
    return "\n".join(lines)


# --- sentence segmentation + prose filtering --------------------------------


def segment_and_filter(text, min_words=6, min_alpha_ratio=0.55):
    """Sentence-segment `text` (via components.text_extraction.segment_text,
    i.e. nltk's sent_tokenize -- reused, not reimplemented) and drop
    sentences that are not really prose: CFR text is full of citation
    lists, "[Reserved]" placeholders, and bare section-number lines that
    nltk still tokenizes as "sentences" but that no reasonable reader
    would call a candidate for discourse-relation analysis.

    This filter is purely a prose/junk screen -- it does NOT look for
    discourse connectives (if/unless/etc.), so it does not bias the
    relation-elicitation yield measurement one way or the other. It only
    removes sentences that are mostly digits/punctuation or too short to
    contain a clause structure at all.

    Returns a list of (original_index, sentence) tuples, index referring
    to nltk's sentence order within `text` (not globally unique across
    parts -- callers tag part/title themselves).
    """
    indexed = segment_text(text)
    kept = []
    seen = set()
    for idx, sentence in indexed:
        sentence = sentence.strip()
        if "[Reserved]" in sentence or "[Removed" in sentence:
            continue
        words = sentence.split()
        if len(words) < min_words:
            continue
        alpha_chars = sum(1 for c in sentence if c.isalpha())
        if len(sentence) == 0 or alpha_chars / len(sentence) < min_alpha_ratio:
            continue
        # Drop exact-duplicate boilerplate (e.g. repeated standard-citation
        # sentences in incorporation-by-reference lists).
        if sentence in seen:
            continue
        seen.add(sentence)
        kept.append((idx, sentence))
    return kept


def load_cfr_part_sentences(title, part, label, date=DEFAULT_DATE, force=False):
    """End-to-end: fetch -> strip -> segment -> filter for one CFR part.

    Returns (kept_sentences, stats) where stats records the raw sentence
    count and how many survived the prose filter, for honest reporting.
    """
    xml_text, source_note = fetch_cfr_part_xml(title, part, date=date, force=force)
    text = strip_xml_to_text(xml_text)
    raw_sentences = segment_text(text)
    kept = segment_and_filter(text)
    stats = {
        "title": title,
        "part": part,
        "label": label,
        "date": date,
        "source_note": source_note,
        "raw_char_count": len(text),
        "raw_sentence_count": len(raw_sentences),
        "prose_filtered_sentence_count": len(kept),
    }
    return kept, stats


if __name__ == "__main__":
    # Quick manual check: fetch both parts and print corpus stats.
    for spec in CFR_PARTS:
        sentences, stats = load_cfr_part_sentences(**spec)
        print(f"{stats['label']}: {stats['raw_sentence_count']} raw sentences, "
              f"{stats['prose_filtered_sentence_count']} after prose filter "
              f"({stats['source_note']})")
