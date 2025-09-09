from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import os
import uuid
from components.main import formalize_file  # Updated import

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), '..', 'uploads')
UPLOAD_FOLDER = os.path.abspath(UPLOAD_FOLDER)

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400
    
    file = request.files['file']
    filename = file.filename
    ext = os.path.splitext(filename)[1].lower()
    saved_filename = f"{uuid.uuid4()}{ext}"
    save_path = os.path.join(UPLOAD_FOLDER, saved_filename)
    file.save(save_path)
    
    return jsonify({"fileUrl": save_path})

@app.route('/formalize', methods=['POST'])
def formalize():
    try:
        data = request.get_json()
        if not data or 'fileUrl' not in data or 'formatType' not in data:
            return jsonify({"error": "Invalid input"}), 400

        file_url = os.path.join(UPLOAD_FOLDER, data['fileUrl']) \
            if not data['fileUrl'].startswith(UPLOAD_FOLDER) else data['fileUrl']

        format_type = data['formatType']  # "logic" or "english"
        
        # Optional parallel processing parameters
        use_parallel = data.get('useParallel', True)  # Default to True
        max_workers = data.get('maxWorkers', 5)  # Default to 5 workers

        if not os.path.exists(file_url):
            print(file_url)
            return jsonify({"error": "File not found"}), 404

        result = formalize_file(file_url, format_type, use_parallel=use_parallel, max_workers=max_workers)
        # Include logic and english reconstructions if you want:
        # result["logic_reconstruction"], result["english_reconstruction"]
        
        return jsonify({
            "axioms": result["axioms"],
            "output_pdf_path": result["output_pdf"],
            "logic_reconstruction": result.get("logic_reconstruction", ""),
            "english_reconstruction": result.get("english_reconstruction", "")
        })
    except Exception as e:
        print(f"Error in /formalize: {e}")
        return jsonify({"error": "An internal error occurred"}), 500

@app.route('/download', methods=['GET'])
def download():
    path = request.args.get("path")
    if not path or not os.path.exists(path):
        return jsonify({"error": "File not found"}), 404
    return send_file(path, as_attachment=True)

if __name__ == '__main__':
    app.run(port=3000, debug=True)


