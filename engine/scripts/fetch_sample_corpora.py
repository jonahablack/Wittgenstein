"""Fetch public-domain sample documents into data/live_corpora/ (gitignored), one folder
per corpus with a meta.json title. Run: uv run python scripts/fetch_sample_corpora.py
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "data" / "live_corpora"
SAMPLES = {
    "austen": {
        "title": "Pride and Prejudice (Jane Austen)",
        "files": {"pride-and-prejudice.txt": "https://www.gutenberg.org/cache/epub/1342/pg1342.txt"},
        "license": "Public domain in the USA (Project Gutenberg eBook #1342).",
    },
}


def main() -> None:
    for folder, spec in SAMPLES.items():
        d = ROOT / folder
        d.mkdir(parents=True, exist_ok=True)
        for name, url in spec["files"].items():
            target = d / name
            if not target.exists():
                req = urllib.request.Request(url, headers={"User-Agent": "wittgenstein-sample-fetch"})
                with urllib.request.urlopen(req, timeout=60) as r:
                    target.write_bytes(r.read())
                print(f"fetched {target}")
        (d / "meta.json").write_text(json.dumps({"title": spec["title"], "license": spec["license"]}, indent=2))


if __name__ == "__main__":
    main()
