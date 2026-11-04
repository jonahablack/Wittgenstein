"""Export JSON Schema for every live-pipeline payload the frontend consumes, so its
TypeScript types are generated from the backend models rather than written by hand
(docs/live-pipeline-plan.md §7). Output: ../web/src/generated/live-schema.json.

Run: uv run python scripts/export_live_schema.py   (then `npm run gen:types` in web/)
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import TypeAdapter

from wittgenstein.live.events import LiveEvent, UnitPoint
from wittgenstein.live.flags import AwarenessFlag, CheckRecord
from wittgenstein.live.generate import ProviderInfo
from wittgenstein.live.query import QueryAnalysis
from wittgenstein.live.runner import Receipt
from wittgenstein.live.select import LedgerEntry
from wittgenstein.live.verify import VerifiedSentence

TYPES = {
    "LiveEvent": LiveEvent,
    "UnitPoint": UnitPoint,
    "AwarenessFlag": AwarenessFlag,
    "CheckRecord": CheckRecord,
    "QueryAnalysis": QueryAnalysis,
    "LedgerEntry": LedgerEntry,
    "Receipt": Receipt,
    "VerifiedSentence": VerifiedSentence,
    "ProviderInfo": ProviderInfo,
}


def main() -> None:
    defs: dict[str, object] = {}
    for name, tp in TYPES.items():
        schema = TypeAdapter(tp).json_schema(ref_template="#/$defs/{model}")
        defs.update(schema.pop("$defs", {}))
        defs[name] = schema
    root = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "LiveSchema",
        "type": "object",
        "properties": {name: {"$ref": f"#/$defs/{name}"} for name in TYPES},
        "required": list(TYPES),
        "additionalProperties": False,
        "$defs": defs,
    }
    out = Path(__file__).resolve().parents[2] / "web" / "src" / "generated" / "live-schema.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(root, indent=2, sort_keys=True) + "\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
