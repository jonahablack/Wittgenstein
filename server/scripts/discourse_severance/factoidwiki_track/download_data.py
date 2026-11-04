"""Task 2: fetch a real sample of source paragraphs to test the
Propositionizer against.

chentong00/propositionizer-wiki-data's train.jsonl is confirmed small
(52,678,196 bytes per the HF API `siblings`/size check done before
writing this script -- about 50.2 MiB), so this fetches the WHOLE file
in one shot (simplest path explicitly sanctioned by the task) rather
than doing HTTP range requests, and caches it under data_cache/ so nothing
here re-downloads on every run.

Each line is a JSON object with fields:
  - "sources": str. The dataset card's PROSE documents this as "Title:
    {title}. Section: {section}. {content}" (no "Content:" label), but
    the ACTUAL data contradicts that: every single one of the 42,857
    rows in this file has ". Content: " before the paragraph text (see
    _split_sources's docstring and README.md, Task 3). So empirically,
    the real format is "Title: {title}. Section: {section}. Content:
    {content}" -- matching the MODEL README, not the dataset card's own
    prose about itself.
  - "targets": a JSON-STRING-ENCODED list of proposition strings (i.e.
    targets is itself a string that must be json.loads()'d again to get
    the list)

Usage:
    venv/bin/python server/scripts/discourse_severance/factoidwiki_track/download_data.py
"""

import json
import os
import random
import sys
import time

import requests

from env_utils import DATA_CACHE_DIR, ensure_dirs

DATASET_URL = (
    "https://huggingface.co/datasets/chentong00/propositionizer-wiki-data"
    "/resolve/main/train.jsonl"
)
LOCAL_PATH = os.path.join(DATA_CACHE_DIR, "train.jsonl")
EXPECTED_MIN_BYTES = 50_000_000  # sanity floor; confirmed actual size ~52.68MB


def download_train_jsonl(force=False):
    ensure_dirs()
    if os.path.exists(LOCAL_PATH) and not force:
        size = os.path.getsize(LOCAL_PATH)
        print(f"Already cached: {LOCAL_PATH} ({size:,} bytes). Skipping download.")
        return LOCAL_PATH

    print(f"Downloading {DATASET_URL} -> {LOCAL_PATH}")
    t0 = time.time()
    with requests.get(DATASET_URL, stream=True, timeout=120) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        written = 0
        tmp_path = LOCAL_PATH + ".part"
        with open(tmp_path, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                fh.write(chunk)
                written += len(chunk)
        os.replace(tmp_path, LOCAL_PATH)
    elapsed = time.time() - t0
    size = os.path.getsize(LOCAL_PATH)
    print(f"Downloaded {size:,} bytes in {elapsed:.1f}s ({size / elapsed / 1e6:.2f} MB/s)")

    if size < EXPECTED_MIN_BYTES:
        raise RuntimeError(
            f"FATAL: downloaded file only {size:,} bytes, expected >= "
            f"{EXPECTED_MIN_BYTES:,}. Download likely truncated or wrong URL."
        )
    if total and size != total:
        raise RuntimeError(
            f"FATAL: downloaded {size:,} bytes but Content-Length said "
            f"{total:,}. Truncated download."
        )
    return LOCAL_PATH


def load_records(path=LOCAL_PATH, limit=None):
    """Yield parsed records: {"sources": str, "title": str, "section": str,
    "content": str, "targets": list[str]}.

    "sources" is kept as the raw string, verbatim, exactly as it appears
    in train.jsonl (empirically: always WITH a "Content:" label -- see
    _split_sources). title/section/content are also parsed back out so
    callers (e.g. the prompt-format script) can cheaply build EITHER
    candidate prompt format (with or without the "Content:" label) from
    the same clean underlying fields rather than string-hacking.
    """
    records = []
    with open(path, encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            if limit is not None and i >= limit:
                break
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            sources = row["sources"]
            title, section, content = _split_sources(sources)
            targets_raw = row["targets"]
            targets = json.loads(targets_raw) if isinstance(targets_raw, str) else targets_raw
            records.append(
                {
                    "sources": sources,
                    "title": title,
                    "section": section,
                    "content": content,
                    "targets": targets,
                }
            )
    return records


def _split_sources(sources):
    """Parse a `sources` string back into (title, section, content).

    EMPIRICAL CORRECTION to this function's original docstring (left here
    for the record): the dataset card's PROSE claims the `sources` format
    is "Title: {title}. Section: {section}. {content}" with no "Content:"
    label. That prose claim does NOT match the actual data. A full scan
    of all 42,857 rows in the downloaded train.jsonl (see README.md,
    Task 3) found ". Content: " present in 100% of rows (42857/42857,
    zero exceptions) -- i.e. the real `sources` strings are actually
    "Title: {title}. Section: {section}. Content: {content}", matching
    the MODEL README's format, not the dataset card's prose description
    of its own field.

    This function therefore looks for the ". Content: " marker explicitly
    and strips it, so the returned `content` is the bare paragraph text
    with NO label baked in either way -- callers can then cheaply
    reconstruct EITHER candidate prompt format from the same clean
    (title, section, content) tuple:
      - with label:    f"Title: {title}. Section: {section}. Content: {content}"
      - without label: f"Title: {title}. Section: {section}. {content}"

    An earlier version of this function naively split on the first ". "
    after "Section: ", which left "Content: " glued onto the front of
    `content` (harmless for reconstructing the with-label format, since
    that's what was already there, but silently WRONG for the
    without-label format, which ended up with a leaked "Content: " prefix
    it should not have had). Fixed here before Task 3 depended on it.
    """
    prefix = "Title: "
    if not sources.startswith(prefix):
        raise ValueError(f"FATAL: unexpected sources format (no 'Title: ' prefix): {sources[:80]!r}")
    rest = sources[len(prefix):]
    title, sep, rest2 = rest.partition(". Section: ")
    if not sep:
        raise ValueError(f"FATAL: unexpected sources format (no '. Section: ' marker): {sources[:120]!r}")
    if ". Content: " in rest2:
        section, _, content = rest2.partition(". Content: ")
    else:
        # Not observed in any of the 42,857 real rows, but fail loudly
        # rather than silently mis-splitting if a future/different row
        # actually lacks the label.
        section, sep2, content = rest2.partition(". ")
        if not sep2:
            raise ValueError(f"FATAL: unexpected sources format (no section/content separator): {sources[:160]!r}")
    return title, section, content


SPLIT_SEED = 13  # matches DEFAULT_SEED convention in ../run_experiments.py
N_FORMAT_TEST = 10   # Task 3: prompt-format resolution
N_THROUGHPUT = 20    # Task 4: throughput measurement


def shuffled_records(path=LOCAL_PATH, seed=SPLIT_SEED):
    """Loads every record and shuffles once with a fixed seed, so Tasks
    3/4/5 can each take a disjoint slice of the SAME shuffled order
    (format-test = [0:10], throughput = [10:30], classifier pool =
    [30:]) without ever reusing a paragraph across tasks, and without
    each script needing its own ad hoc sampling logic. Deterministic and
    reproducible across runs/scripts given the same seed.
    """
    records = load_records(path)
    rng = random.Random(seed)
    rng.shuffle(records)
    return records


def get_format_test_slice(records=None):
    records = records if records is not None else shuffled_records()
    return records[:N_FORMAT_TEST]


def get_throughput_slice(records=None):
    records = records if records is not None else shuffled_records()
    return records[N_FORMAT_TEST:N_FORMAT_TEST + N_THROUGHPUT]


def get_classifier_pool(records=None):
    """Everything after the format-test and throughput slices -- Task 5
    draws its screening batch from the front of this pool.
    """
    records = records if records is not None else shuffled_records()
    return records[N_FORMAT_TEST + N_THROUGHPUT:]


if __name__ == "__main__":
    path = download_train_jsonl()
    records = load_records(path, limit=5)
    print(f"\nParsed {len(records)} sample records for a sanity check:")
    for r in records:
        print(f"  title={r['title']!r} section={r['section']!r} "
              f"content_len={len(r['content'])} n_targets={len(r['targets'])}")
    total_lines = sum(1 for _ in open(path, encoding="utf-8"))
    print(f"\nTotal rows in train.jsonl: {total_lines:,}")
