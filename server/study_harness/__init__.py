"""Self-contained study harness for the within-subjects triage study.

One general-population cohort (config.COHORTS) x three conditions
("blind", "triaged", "opaque"), two task types (batch claim review,
query-answer verification). This package only *consumes* already-computed
output (pipeline output under outputs/{document_id}_final_data.json, or an
exp3 report); it never computes risk tiers or flags itself, and it is
deliberately decoupled from the main product UI/routes -- everything lives
under the /study URL prefix via the blueprint in .routes.

Registration (done in app.py by the coordinator):

    from study_harness.routes import study_bp
    app.register_blueprint(study_bp)
"""
