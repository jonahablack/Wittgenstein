"""Flask blueprint for the study harness. All routes live under /study,
fully separate from the main product routes.

Admin surface (condition assignment happens ONLY here):
    POST /study/admin/sessions          create a session
    GET  /study/admin/sessions          list session ids on disk
    GET  /study/admin/sessions/<sid>    full stored session state

Participant surface (never exposes condition internals, ground truth,
or -- in the blind condition -- any risk tier/flag):
    GET  /study/sessions/<sid>/items        all items, serve order
    GET  /study/sessions/<sid>/items/next   next undecided item
    POST /study/sessions/<sid>/decisions    submit a decision

Export:
    GET  /study/sessions/<sid>/export       analysis record (also persisted)
"""

import json
import os

from flask import Blueprint, jsonify, request

from . import sessions as sess
from .config import ConfigError
from .export import build_export_record, write_export_record
from .paths import study_data_dir

study_bp = Blueprint("study", __name__, url_prefix="/study")


def _json_body():
    return request.get_json(silent=True) or {}


@study_bp.errorhandler(sess.StudyError)
@study_bp.errorhandler(ConfigError)
def _bad_request(e):
    return jsonify({"error": str(e)}), 400


@study_bp.errorhandler(sess.NotFound)
def _not_found(e):
    # KeyError str() wraps the message in quotes; unwrap for a clean body.
    return jsonify({"error": e.args[0] if e.args else "not found"}), 404


@study_bp.errorhandler(sess.Conflict)
def _conflict(e):
    return jsonify({"error": str(e)}), 409


# ---------- admin ----------

@study_bp.post("/admin/sessions")
def create_session():
    data = _json_body()
    session = sess.create_session(
        participant_id=data.get("participant_id"),
        cohort=data.get("cohort"),
        condition=data.get("condition"),
        document_id=data.get("document_id"),
        config_path=data.get("config_path"),
    )
    return jsonify({
        "session_id": session["session_id"],
        "participant_id": session["participant_id"],
        "cohort": session["cohort"],
        "condition": session["condition"],
        "document_id": session["document_id"],
        "item_count": len(session["items"]),
    }), 201


@study_bp.get("/admin/sessions")
def list_sessions():
    ids = [f[:-len(".json")] for f in sorted(os.listdir(study_data_dir()))
           if f.endswith(".json")]
    return jsonify({"session_ids": ids})


@study_bp.get("/admin/sessions/<session_id>")
def admin_get_session(session_id):
    return jsonify(sess.load_session(session_id))


# ---------- participant ----------

@study_bp.get("/sessions/<session_id>/items")
def get_items(session_id):
    return jsonify(sess.serve_all_items(session_id))


@study_bp.get("/sessions/<session_id>/items/next")
def get_next_item(session_id):
    return jsonify(sess.serve_next_item(session_id))


@study_bp.post("/sessions/<session_id>/decisions")
def post_decision(session_id):
    data = _json_body()
    if "item_id" not in data:
        raise sess.StudyError("item_id is required")
    result = sess.record_decision(
        session_id=session_id,
        item_id=data.get("item_id"),
        decision=data.get("decision"),
        confidence=data.get("confidence"),
        identified_weak_source=data.get("identified_weak_source"),
    )
    return jsonify(result), 201


# ---------- export ----------

@study_bp.get("/sessions/<session_id>/export")
def export_session(session_id):
    record = build_export_record(session_id)
    write_export_record(session_id)
    return jsonify(record)
