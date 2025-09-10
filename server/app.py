# server/app.py
import os, uuid, shutil  # <-- add shutil
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
from components.main import formalize_file

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# allow a persistent disk via DATA_DIR (e.g., /var/data on Render)
DATA_DIR   = os.environ.get("DATA_DIR", BASE_DIR)
CLIENT_DIR = os.path.join(BASE_DIR, "client", "dist")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
OUTPUT_DIR = os.path.join(DATA_DIR, "outputs")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

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
    is_api = request.path.startswith(("/upload", "/formalize", "/download", "/files/", "/health", "/__debug"))
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
    max_workers = data.get("maxWorkers", 5)

    try:
        result = formalize_file(file_path, format_type,
                                use_parallel=use_parallel,
                                max_workers=max_workers)

        # normalize/copy output into OUTPUT_DIR and return a public URL
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
            "english_reconstruction": result.get("english_reconstruction", "")
        })
    except Exception as e:
        print(f"/formalize error: {e}")
        return jsonify({"error": "An internal error occurred"}), 500

@app.get("/files/<path:filename>")
def files(filename):
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=True)

# (Optional) keep /download but look in both uploads and outputs
@app.get("/download")
def download():
    path = request.args.get("path")
    if not path:
        return jsonify({"error": "File not found"}), 404
    if os.path.isabs(path) and os.path.exists(path):
        return send_file(path, as_attachment=True)
    # try both known dirs
    for base in (UPLOAD_DIR, OUTPUT_DIR):
        candidate = os.path.join(base, os.path.basename(path))
        if os.path.exists(candidate):
            return send_file(candidate, as_attachment=True)
    return jsonify({"error": "File n




