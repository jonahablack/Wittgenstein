# server/app.py
import os, uuid, shutil
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
from components.main import formalize_file
from components.review_store import record_decision, get_all_decisions

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# allow a persistent disk via DATA_DIR (e.g., /var/data on Render)
DATA_DIR   = os.environ.get("DATA_DIR", BASE_DIR)
CLIENT_DIR = os.path.join(BASE_DIR, "client", "dist")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
OUTPUT_DIR = os.path.join(DATA_DIR, "outputs")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
REVIEWS_FILE = os.path.join(OUTPUT_DIR, "reviews.json")  # lives under outputs/, already gitignored

app = Flask(__name__, static_folder=CLIENT_DIR, static_url_path="")
CORS(app)

# ---------- Frontend (Vite build) ----------
@app.get("/")
def index():
    return send_from_directory(CLIENT_DIR, "index.html")

@app.get("/assets/<path:filename>")
def vite_assets(filename):
    return send_from_directory(os.path.join(CLIENT_DIR, "assets"), filename)

@app.get("/vite.svg")
def vite_svg():
    return send_from_directory(CLIENT_DIR, "vite.svg")

@app.get("/favicon.ico")
def favicon():
    return "", 204

# SPA fallback
@app.errorhandler(404)
def spa_fallback(err):
    wants_html = "text/html" in request.headers.get("Accept", "")
    is_api = request.path.startswith(("/upload", "/formalize", "/download", "/files/", "/health", "/__debug", "/review", "/reviews"))
    if request.method == "GET" and wants_html and not is_api:
        return send_from_directory(CLIENT_DIR, "index.html")
    return err

# ---------- API ----------
@app.post("/upload")
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Empty filename"}), 400
    ext = os.path.splitext(f.filename)[1].lower()
    file_id = f"{uuid.uuid4()}{ext}"
    f.save(os.path.join(UPLOAD_DIR, file_id))
    return jsonify({"fileId": file_id})

@app.post("/formalize")
def formalize():
    data = request.get_json(silent=True) or {}
    file_id = data.get("fileId")
    format_type = data.get("formatType")
    if not file_id or not format_type:
        return jsonify({"error": "Invalid input"}), 400

    file_path = os.path.join(UPLOAD_DIR, os.path.basename(file_id))
    if not os.path.exists(file_path):
        return jsonify({"error": "File not found"}), 404

    use_parallel = data.get("useParallel", True)

    # Bounded to avoid an unbounded client-supplied value spinning up an
    # arbitrarily large thread pool (resource-exhaustion DoS from a single
    # request). 20 is comfortably above the default of 5 for any legitimate
    # use of this knob.
    max_workers = data.get("maxWorkers", 5)
    try:
        max_workers = int(max_workers)
    except (TypeError, ValueError):
        max_workers = 5
    max_workers = max(1, min(max_workers, 20))

    try:
        # Pass this app's own OUTPUT_DIR through explicitly, so the
        # pipeline's intermediate and output files land in the one
        # consistent, DATA_DIR-aware location this file already sets up --
        # rather than main.py's own hardcoded relative "outputs" default,
        # which could resolve to a different directory than UPLOAD_DIR/
        # OUTPUT_DIR depending on the process's working directory.
        result = formalize_file(file_path, format_type,
                                use_parallel=use_parallel,
                                max_workers=max_workers,
                                output_dir=OUTPUT_DIR)

        output_pdf = result.get("output_pdf") or result.get("output_pdf_path")
        download_url = None
        if output_pdf and os.path.exists(output_pdf):
            fname = os.path.basename(output_pdf)
            dest = os.path.join(OUTPUT_DIR, fname)
            if os.path.abspath(output_pdf) != os.path.abspath(dest):
                shutil.copy2(output_pdf, dest)
            download_url = f"/files/{fname}"

        return jsonify({
            "axioms": result.get("axioms", []),
            "download_url": download_url,  # <-- client should use this
            "logic_reconstruction": result.get("logic_reconstruction", ""),
            "english_reconstruction": result.get("english_reconstruction", ""),
            "warning": result.get("warning"),
        })
    except Exception as e:
        print(f"/formalize error: {e}")
        return jsonify({"error": "An internal error occurred"}), 500

@app.get("/files/<path:filename>")
def files(filename):
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=True)


@app.get("/download")
def download():
    """
    Serves a file by NAME from UPLOAD_DIR or OUTPUT_DIR only.

    Previously this accepted an arbitrary `path` query parameter and, if it
    was an absolute path that existed on the server's filesystem, served it
    directly with no sandboxing -- e.g. GET /download?path=/etc/passwd, or
    any other file the Flask process could read (server .env, source code,
    etc). That branch is removed entirely below. A caller can only ever
    request a file by its basename, resolved against UPLOAD_DIR/OUTPUT_DIR,
    exactly like the (already-safe) fallback loop below did before -- so
    there is no longer any path that can escape those two directories.
    """
    path = request.args.get("path")
    if not path:
        return jsonify({"error": "File not found"}), 404
    for base in (UPLOAD_DIR, OUTPUT_DIR):
        candidate = os.path.join(base, os.path.basename(path))
        if os.path.exists(candidate):
            return send_file(candidate, as_attachment=True)
    return jsonify({"error": "File not found"}), 404

@app.post("/review")
def review():
    data = request.get_json(silent=True) or {}
    claim_id = data.get("claimId")
    decision = data.get("decision")
    if not claim_id or not decision:
        return jsonify({"error": "claimId and decision are required"}), 400
    try:
        record = record_decision(REVIEWS_FILE, claim_id, decision)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"claimId": claim_id, **record})

@app.get("/reviews")
def reviews():
    return jsonify(get_all_decisions(REVIEWS_FILE))

@app.get("/health")
def health():
    return jsonify({"status": "healthy", "service": "wittgenstein-backend"})

# debug
@app.get("/__debug")
def __debug():
    idx = os.path.join(CLIENT_DIR, "index.html")
    assets = os.path.join(CLIENT_DIR, "assets")
    return jsonify({
        "CLIENT_DIR": CLIENT_DIR,
        "UPLOAD_DIR": UPLOAD_DIR,
        "OUTPUT_DIR": OUTPUT_DIR,
        "exists_index": os.path.exists(idx),
        "exists_assets_dir": os.path.isdir(assets),
        "uploads_count": len(os.listdir(UPLOAD_DIR)) if os.path.isdir(UPLOAD_DIR) else None,
        "outputs_count": len(os.listdir(OUTPUT_DIR)) if os.path.isdir(OUTPUT_DIR) else None,
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 3000)), debug=False)