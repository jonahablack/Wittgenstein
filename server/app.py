# server/app.py
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
import os, uuid
from components.main import formalize_file

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CLIENT_DIR = os.path.join(BASE_DIR, "client", "public")   # <— your index.html lives here
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__, static_folder=CLIENT_DIR, static_url_path="")
CORS(app)

# ---------- Frontend ----------
@app.get("/")
def index():
    return send_from_directory(CLIENT_DIR, "index.html")

@app.get("/<path:path>")
def static_proxy(path):
    fp = os.path.join(CLIENT_DIR, path)
    if os.path.isfile(fp):
        return send_from_directory(CLIENT_DIR, path)
    # SPA fallback
    return send_from_directory(CLIENT_DIR, "index.html")

@app.get("/favicon.ico")
def favicon():
    return "", 204

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
        result = formalize_file(file_path, format_type, use_parallel=use_parallel, max_workers=max_workers)
        return jsonify({
            "axioms": result.get("axioms", []),
            "output_pdf_path": result.get("output_pdf", ""),
            "logic_reconstruction": result.get("logic_reconstruction", ""),
            "english_reconstruction": result.get("english_reconstruction", ""),
        })
    except Exception as e:
        print(f"/formalize error: {e}")
        return jsonify({"error": "An internal error occurred"}), 500

@app.get("/download")
def download():
    path = request.args.get("path")
    if not path:
        return jsonify({"error": "File not found"}), 404
    # allow relative file ids from uploads or absolute paths produced by pipeline
    candidate = path if os.path.isabs(path) else os.path.join(UPLOAD_DIR, os.path.basename(path))
    if not os.path.exists(candidate):
        return jsonify({"error": "File not found"}), 404
    return send_file(candidate, as_attachment=True)

@app.get("/health")
def health():
    return jsonify({"status": "healthy", "service": "wittgenstein-backend"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 3000)), debug=False)



