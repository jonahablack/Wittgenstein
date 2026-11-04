"""Analysis export: one JSON record per session.

Shape (downstream analysis scripts key on this -- EXPORT_ITEM_KEYS below
are required and present on every item; OPTIONAL_EXPORT_ITEM_KEYS are
additive and only present where the source data actually has them, never
replacing or crowding out a required key):

    {
      "participant_id": str,
      "cohort": str (currently always "general", see config.COHORTS),
      "condition": "blind" | "triaged" | "opaque",
      "document_id": str,
      "items": [
        {
          "item_id": str,
          "item_type": "batch_claim" | "batch_passage" | "query_verification",
          "decision": "approved" | "flagged" | "rejected" | null,
          "confidence": 1-5 | null,
          "time_to_decision": seconds (float) | null,
          "ground_truth_label":
              "seeded_error" | "clean" | "compromised"   (pipeline-sourced)
            | "correct" | "dangerous_failure"            (exp3-sourced),
          "identified_weak_source": claim_index | null,
          "arm": str           -- OPTIONAL, exp3-sourced items only: which
                                  of config.EXP3_REPAIR_ARMS produced this
                                  item's claims/passage (e.g. "disco_rag");
                                  omitted entirely (not even null) for the
                                  original pipeline-sourced corpus, so its
                                  export shape is unchanged
        }, ...
      ]
    }

Undecided items appear with null decision fields so partial sessions are
still analyzable (and visibly partial). Items are exported in the order
they were served to the participant.
"""

import json
import os

from .paths import study_data_dir
from .sessions import load_session, ordered_items

EXPORT_ITEM_KEYS = ("item_id", "item_type", "decision", "confidence",
                    "time_to_decision", "ground_truth_label",
                    "identified_weak_source")

# Present only when the item itself carries the key -- currently set only
# on items sourced from the exp3 report (see sessions.py's
# _build_exp3_items): arm, which of config.EXP3_REPAIR_ARMS produced the
# item. Additive on top of EXPORT_ITEM_KEYS, never replacing any of its
# required keys.
OPTIONAL_EXPORT_ITEM_KEYS = ("arm",)


def build_export_record(session_id: str) -> dict:
    session = load_session(session_id)
    return {
        "participant_id": session["participant_id"],
        "cohort": session["cohort"],
        "condition": session["condition"],
        "document_id": session["document_id"],
        "items": [
            {
                **{key: item[key] for key in EXPORT_ITEM_KEYS},
                **{key: item[key] for key in OPTIONAL_EXPORT_ITEM_KEYS
                   if key in item},
            }
            for item in ordered_items(session)
        ],
    }


def write_export_record(session_id: str) -> str:
    """Persist the export next to the session data, scoped by session_id
    (uuid) so concurrent sessions never share a filename."""
    record = build_export_record(session_id)
    export_dir = os.path.join(study_data_dir(), "exports")
    os.makedirs(export_dir, exist_ok=True)
    path = os.path.join(export_dir,
                        f"{os.path.basename(session_id)}_export.json")
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "w") as f:
        json.dump(record, f, indent=2)
    os.replace(tmp, path)
    return path
