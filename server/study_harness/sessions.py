"""Session state: creation, participant-facing item serving, decisions.

A session is one participant x cohort x condition x document. Its full
state lives in a single JSON file, study_data/{session_id}.json -- the
session_id is a uuid4, so concurrent sessions can never collide on disk.
Writes are atomic (tmp file + os.replace) so a reader never sees a
half-written session.

Blinding is applied at *serve* time only: the stored session always keeps
the pipeline's full axiom records (including risk_tier/risk_flags) and the
ground-truth labels, and participant_view() strips or includes fields per
the session's condition. The condition itself is fixed at creation by the
admin endpoint -- nothing participant-facing can set or change it.

Three conditions, two corpus-sourcing paths:
  - blind/triaged: batch items are individual claims (one item per claim),
    exactly as before. Sourced either from a pipeline document's axioms
    (claim_index-keyed) or -- new -- from exp3_report.json's pooled repair-
    arm cases (config.load_exp3_cases; one case per (record, repair arm)
    pair), flattened one item per claim with a session-local sequential
    claim_index. triaged additionally sorts by risk signal and shows it;
    blind never shows risk fields.
  - opaque: batch items are one continuous passage per "case" (one item
    per (exp3 record, repair arm) pair, or one item for the whole document
    on the pipeline path, which has no finer natural grouping) with no
    per-claim breakdown and no risk fields at all -- there is only one
    decision point per case, not one per claim.
"""

import json
import os
import time
import uuid

from . import config as cfg
from .paths import study_data_dir

DECISIONS = ("approved", "flagged", "rejected")

# Serve order in the triaged condition: most attention-worthy first.
# These labels come from the pipeline; unknown tiers sort last.
TIER_ORDER = {"Unformalized": 0, "High": 1, "Medium": 2, "Low": 3}

# Risk presentation fields stripped in the blind (and opaque) conditions
# ("flag" is the pipeline's legacy single-flag field -- same information
# channel).
RISK_FIELDS = ("risk_tier", "risk_flags", "flag")

# Item types that carry the review payload participants act on ("batch"
# items, as opposed to query_verification items). batch_claim is one
# individual claim; batch_passage (opaque only) is one merged passage
# standing in for a whole case with no per-claim breakdown.
BATCH_ITEM_TYPES = ("batch_claim", "batch_passage")


class StudyError(ValueError):
    """Client-correctable request error (HTTP 400)."""


class NotFound(KeyError):
    """Unknown session or item (HTTP 404)."""


class Conflict(RuntimeError):
    """Valid request at the wrong time, e.g. deciding an unseen or
    already-decided item (HTTP 409)."""


# ---------------------------------------------------------------------------
# persistence

def _session_path(session_id: str) -> str:
    return os.path.join(study_data_dir(), f"{os.path.basename(session_id)}.json")


def save_session(session: dict) -> None:
    path = _session_path(session["session_id"])
    tmp = f"{path}.tmp.{os.getpid()}.{uuid.uuid4().hex[:8]}"
    with open(tmp, "w") as f:
        json.dump(session, f, indent=2)
    os.replace(tmp, path)


def load_session(session_id: str) -> dict:
    path = _session_path(session_id)
    if not os.path.isfile(path):
        raise NotFound(f"unknown session: {session_id}")
    with open(path, "r") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# creation

def _new_item_shell():
    return {
        "first_viewed_at": None,
        "decision": None,
        "confidence": None,
        "decided_at": None,
        "time_to_decision": None,
        "identified_weak_source": None,
    }


def _build_pipeline_items(cohort_cfg, condition, document_id):
    """Original corpus-sourcing path: a pipeline document's axioms
    (claim_index-keyed) plus pre-written queries. Returns (items, doc_id).
    """
    docs = cohort_cfg["documents"]
    if document_id is None:
        doc = docs[0]
    else:
        matches = [d for d in docs if d["document_id"] == document_id]
        if not matches:
            raise StudyError(
                f"document_id {document_id!r} is not configured for this "
                "cohort"
            )
        doc = matches[0]

    axioms = cfg.load_document_axioms(doc["document_id"])
    by_claim = {}
    for ax in axioms:
        by_claim[ax["claim_index"]] = ax

    seeded = cfg.load_ground_truth(doc["ground_truth_file"])
    unknown = seeded - set(by_claim)
    if unknown:
        raise cfg.ConfigError(
            f"ground-truth file for document '{doc['document_id']}' marks "
            f"claim_indices not present in the pipeline output: "
            f"{sorted(unknown)}"
        )

    items = []
    if condition == "opaque":
        # No finer natural grouping than "the whole document" exists on
        # this corpus-sourcing path (unlike the exp3 path's per-record
        # grouping -- see _build_exp3_items), so opaque collapses every
        # claim in the document into a single passage: one case, one
        # decision point, the same invariant as the exp3 path below.
        # Joined with a plain space, same as _build_exp3_items -- see that
        # function's comment on why reconstruction.py's bullet-list
        # convention is deliberately NOT reused here.
        passage = " ".join(by_claim[ci].get("english", "")
                           for ci in sorted(by_claim))
        item = {
            "item_id": "passage_0",
            "item_type": "batch_passage",
            "ground_truth_label": "seeded_error" if seeded else "clean",
            "payload": {"passage": passage},
        }
        item.update(_new_item_shell())
        items.append(item)
    else:
        for ci in sorted(by_claim):
            item = {
                "item_id": f"claim_{ci}",
                "item_type": "batch_claim",
                "claim_index": ci,
                "ground_truth_label": "seeded_error" if ci in seeded else "clean",
                "payload": by_claim[ci],
            }
            item.update(_new_item_shell())
            items.append(item)

    for q in cohort_cfg["queries"]:
        # A query may be scoped to one of the cohort's documents; unscoped
        # queries apply to every session in the cohort.
        if q.get("document_id") not in (None, doc["document_id"]):
            continue
        missing = [ci for ci in q["source_claim_indices"] if ci not in by_claim]
        if missing:
            raise cfg.ConfigError(
                f"query {q['query_id']!r} references source claim_indices "
                f"not in document '{doc['document_id']}': {missing}"
            )
        item = {
            "item_id": f"query_{q['query_id']}",
            "item_type": "query_verification",
            "query_id": str(q["query_id"]),
            "ground_truth_label": q["classification"],
            "payload": {
                "query": q["query"],
                "answer": q["answer"],
                "source_claim_indices": list(q["source_claim_indices"]),
                "sources": [by_claim[ci] for ci in q["source_claim_indices"]],
                "weak_source_claim_index": q.get("weak_source_claim_index"),
            },
        }
        item.update(_new_item_shell())
        items.append(item)

    return items, doc["document_id"]


def _build_exp3_items(cohort_cfg, cohort, condition, document_id):
    """New corpus-sourcing path: the FactoidWiki exp3 report's already-
    computed, pooled-repair-arm cases (see config.EXP3_REPAIR_ARMS). Every
    record in the report belongs to this cohort (see config.load_exp3_cases
    -- unlike the CFR-track report, there is no per-record field to filter
    on). Returns (items, doc_id). No queries on this path (see
    load_study_config, which rejects 'queries' for an exp3-sourced cohort).
    """
    doc_id = cfg.EXP3_DOCUMENT_IDS[cohort]
    if document_id is not None and document_id != doc_id:
        raise StudyError(
            f"document_id {document_id!r} is not applicable for cohort "
            f"{cohort!r} (sourced from exp3_report_file, whose document_id "
            f"is fixed at {doc_id!r})"
        )

    cases = cfg.load_exp3_cases(cohort_cfg["exp3_report_file"], cohort)

    items = []
    if condition == "opaque":
        for case in cases:
            # Simple space-join, not reconstruction.py's "- claim" bullet
            # list convention: a bulleted list would still show claim
            # boundaries one per line, which defeats the point of opaque
            # (no per-claim breakdown at all) even though it's the
            # existing precedent for joining claim text elsewhere.
            passage = " ".join(case["claims"])
            item = {
                "item_id": f"case_{case['record_id']}__{case['arm']}",
                "item_type": "batch_passage",
                "pool_index": case["pool_index"],
                "ground_truth_label": case["ground_truth_label"],
                "arm": case["arm"],
                "payload": {"passage": passage},
            }
            item.update(_new_item_shell())
            items.append(item)
    else:
        n = 0
        for case in cases:
            # Every claim in one case shares that case's flags list --
            # arm_6_flagged_deferral is genuinely case-level (computed once
            # per record, before any repair arm ran; see
            # config._exp3_record_level_flags), not really per-claim for
            # this corpus, so there is no finer-grained signal to split
            # across claims here.
            for claim_text in case["claims"]:
                item = {
                    "item_id": f"claim_{n}",
                    "item_type": "batch_claim",
                    "claim_index": n,
                    "ground_truth_label": case["ground_truth_label"],
                    "arm": case["arm"],
                    "payload": {
                        "claim_index": n,
                        "english": claim_text,
                        "risk_flags": case["flags"],
                    },
                }
                item.update(_new_item_shell())
                items.append(item)
                n += 1

    return items, doc_id


def create_session(participant_id, cohort, condition,
                   document_id=None, config_path=None) -> dict:
    if not isinstance(participant_id, str) or not participant_id.strip():
        raise StudyError("participant_id (non-empty string) is required")
    if condition not in cfg.CONDITIONS:
        raise StudyError(
            f"condition must be one of {cfg.CONDITIONS}, got {condition!r}"
        )
    study = cfg.load_study_config(config_path)
    if cohort not in study["cohorts"]:
        raise StudyError(
            f"cohort must be one of {sorted(study['cohorts'])}, got {cohort!r}"
        )
    cohort_cfg = study["cohorts"][cohort]

    if cohort_cfg["source_type"] == "exp3":
        items, doc_id = _build_exp3_items(cohort_cfg, cohort, condition,
                                          document_id)
    else:
        items, doc_id = _build_pipeline_items(cohort_cfg, condition,
                                              document_id)

    session = {
        "session_id": str(uuid.uuid4()),
        "participant_id": participant_id.strip(),
        "cohort": cohort,
        "condition": condition,
        "document_id": doc_id,
        "created_at": time.time(),
        "items": items,
    }
    save_session(session)
    return session


# ---------------------------------------------------------------------------
# participant-facing views

def _tier_rank(axiom: dict) -> int:
    tier = axiom.get("risk_tier")
    if tier is not None:
        return TIER_ORDER.get(tier, len(TIER_ORDER))
    # No pipeline-style tier at all -- exp3-sourced claims carry only
    # arm_6_flagged_deferral's per-claim {type, reason} flags, with no
    # High/Medium/Low tier computed anywhere for them. Rank purely on
    # whether any flag fired so triaged still surfaces flagged claims
    # first, without inventing a tier the shipped classifier never
    # computed for this corpus (axiom.get("risk_tier") would silently be
    # None forever here, which is the signal this branch acts on).
    return 0 if axiom.get("risk_flags") else len(TIER_ORDER)


def _axiom_view(axiom: dict, condition: str) -> dict:
    """The pipeline's (or exp3's) claim record, blinded or not. Never
    invents risk data -- triaged passes the fields through verbatim; every
    other condition (blind, and opaque's whole-case passage never reaches
    this function at all) strips risk fields the same way."""
    if condition == "triaged":
        return dict(axiom)
    return {k: v for k, v in axiom.items() if k not in RISK_FIELDS}


def _batch_sort_key(item):
    # batch_claim items carry claim_index; batch_passage items (opaque)
    # have no claim to index, so they fall back to pool_index (exp3) or,
    # on the pipeline path's single whole-document passage, the implicit
    # default -- either way a stable, non-risk-revealing order.
    return item.get("claim_index", item.get("pool_index", 0))


def ordered_items(session: dict) -> list:
    """Session items in the order they are served to the participant.

    blind:   batch items in claim_index order (undifferentiated list),
    triaged: batch claims sorted Unformalized, High, Medium, Low first
             (claim_index breaks ties); see _tier_rank for how this
             extends to exp3-sourced claims, which have flags but no tier.
    opaque:  batch items are one passage per case; there is nothing to
             sort within an item, so this only orders across cases.
    Query items always follow the batch, in config order.
    """
    batch = [it for it in session["items"] if it["item_type"] in BATCH_ITEM_TYPES]
    queries = [it for it in session["items"]
               if it["item_type"] == "query_verification"]
    if session["condition"] == "triaged":
        batch.sort(key=lambda it: (_tier_rank(it["payload"]),
                                   _batch_sort_key(it)))
    else:
        batch.sort(key=_batch_sort_key)
    return batch + queries


def participant_view(item: dict, condition: str) -> dict:
    """What the participant sees. Never includes ground_truth_label, arm,
    query classification, or the compromised query's weak-source answer;
    outside the triaged condition, never includes risk tiers/flags anywhere
    (including inside query sources). opaque never includes a per-claim
    breakdown at all -- only the merged passage."""
    if item["item_type"] == "batch_claim":
        view = {
            "item_id": item["item_id"],
            "item_type": item["item_type"],
        }
        view.update(_axiom_view(item["payload"], condition))
        return view

    if item["item_type"] == "batch_passage":
        # No risk_tier/risk_flags/segment breakdown, no sort-order concept
        # -- there is exactly one merged passage and one decision point.
        return {
            "item_id": item["item_id"],
            "item_type": item["item_type"],
            "passage": item["payload"]["passage"],
        }

    sources = [_axiom_view(ax, condition) for ax in item["payload"]["sources"]]
    if condition == "triaged":
        # Risk-tier the retrieved sources the same way the batch is sorted.
        order = {ci: _tier_rank(ax)
                 for ci, ax in zip(item["payload"]["source_claim_indices"],
                                   item["payload"]["sources"])}
        sources.sort(key=lambda s: (order.get(s.get("claim_index"),
                                              len(TIER_ORDER)),
                                    s.get("claim_index", 0)))
    else:
        sources.sort(key=lambda s: s.get("claim_index", 0))
    return {
        "item_id": item["item_id"],
        "item_type": item["item_type"],
        "query_id": item["query_id"],
        "query": item["payload"]["query"],
        "answer": item["payload"]["answer"],
        "sources": sources,
    }


def _stamp_first_view(item: dict, now: float) -> None:
    if item["first_viewed_at"] is None:
        item["first_viewed_at"] = now


def serve_all_items(session_id: str) -> dict:
    """All items for the session, participant view, in serve order.
    Records the first-view timestamp for every item not yet viewed."""
    session = load_session(session_id)
    now = time.time()
    items = ordered_items(session)
    for it in items:
        _stamp_first_view(it, now)
    save_session(session)
    return {
        "session_id": session["session_id"],
        "condition": session["condition"],
        "items": [participant_view(it, session["condition"]) for it in items],
    }


def serve_next_item(session_id: str) -> dict:
    """The first undecided item in serve order (stamping its first view),
    or {"done": true} when every item has a decision."""
    session = load_session(session_id)
    for it in ordered_items(session):
        if it["decision"] is None:
            _stamp_first_view(it, time.time())
            save_session(session)
            return {
                "session_id": session["session_id"],
                "done": False,
                "item": participant_view(it, session["condition"]),
            }
    return {"session_id": session["session_id"], "done": True, "item": None}


# ---------------------------------------------------------------------------
# decisions

def _find_item(session: dict, item_id):
    for it in session["items"]:
        if it["item_id"] == item_id:
            return it
    raise NotFound(f"unknown item_id: {item_id}")


def record_decision(session_id, item_id, decision, confidence,
                    identified_weak_source=None) -> dict:
    session = load_session(session_id)
    item = _find_item(session, item_id)

    if decision not in DECISIONS:
        raise StudyError(f"decision must be one of {DECISIONS}, "
                         f"got {decision!r}")
    if not isinstance(confidence, int) or isinstance(confidence, bool) \
            or not 1 <= confidence <= 5:
        raise StudyError("confidence must be an integer from 1 to 5")
    if item["decision"] is not None:
        raise Conflict(f"item {item_id} already has a decision")
    if item["first_viewed_at"] is None:
        raise Conflict(
            f"item {item_id} has not been served yet -- fetch it before "
            "submitting a decision (time_to_decision needs a first view)"
        )

    is_flagged_query = (decision == "flagged"
                        and item["item_type"] == "query_verification")
    if is_flagged_query:
        # The participant must identify which retrieved source is the
        # weak link. Required only here, per protocol.
        if identified_weak_source is None:
            raise StudyError(
                "identified_weak_source is required when flagging a "
                "query item"
            )
        if identified_weak_source not in item["payload"]["source_claim_indices"]:
            raise StudyError(
                "identified_weak_source must be the claim_index of one of "
                f"the item's sources "
                f"({item['payload']['source_claim_indices']})"
            )

    now = time.time()
    item["decision"] = decision
    item["confidence"] = confidence
    item["decided_at"] = now
    item["time_to_decision"] = now - item["first_viewed_at"]
    item["identified_weak_source"] = (identified_weak_source
                                      if identified_weak_source is not None
                                      else None)
    save_session(session)
    return {
        "item_id": item["item_id"],
        "decision": item["decision"],
        "confidence": item["confidence"],
        "time_to_decision": item["time_to_decision"],
        "identified_weak_source": item["identified_weak_source"],
    }
