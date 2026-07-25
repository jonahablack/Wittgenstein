"""Local JSON-backed store for reviewer decisions (Approved/Flagged/Rejected).

No real DB needed for a proof-of-concept demo -- a single JSON file keyed by
claim id is enough, and keeps deployment friction at zero.
"""

import json
import os
import threading
from datetime import datetime, timezone

_VALID_DECISIONS = {"approved", "flagged", "rejected"}
_lock = threading.Lock()


def _read(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def record_decision(path, claim_id, decision):
    decision = (decision or "").lower()
    if decision not in _VALID_DECISIONS:
        raise ValueError(f"decision must be one of {sorted(_VALID_DECISIONS)}")
    with _lock:
        data = _read(path)
        data[claim_id] = {
            "decision": decision,
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
        }
        _write(path, data)
        return data[claim_id]


def get_all_decisions(path):
    with _lock:
        return _read(path)
