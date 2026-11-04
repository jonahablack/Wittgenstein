#!/usr/bin/env python
"""Export JSON Schema files for every public interchange schema.

Usage: uv run python scripts/export_json_schemas.py [output_dir]
"""

from __future__ import annotations

import sys
from pathlib import Path

from wittgenstein.exports.json_schema import export_all


def main(output_dir: Path = Path("schemas/generated")) -> None:
    written = export_all(output_dir)
    for path in written:
        print(f"wrote {path}")
    print(f"Exported {len(written)} schema file(s) to {output_dir}")


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("schemas/generated")
    main(out)
