import os
import threading
import io
import json
import zipfile
from flask import Flask, request, jsonify, send_file, send_from_directory
from werkzeug.utils import secure_filename

from manager import SiteManager

# =========================
# 🔧 CONFIG
# =========================

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "pendentes")

os.makedirs(UPLOAD_DIR, exist_ok=True)

processando = False
lock = threading.Lock()

# =========================
# 🌐 CORS
# =========================

@app.after_request
def cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response

# =========================
# 🌍 SITE
# =========================

@app.route("/")
def index():
    return send_from_directory(".", "index.html")

# =========================
# 🔐 ADMIN
# =========================

@app.route("/login.html")
def login():
    return send_from_directory(".", "login.html")

@app.route("/dashboard.html")
def dashboard():
    return send_from_directory("admin", "dashboard.html")

# =========================
# 📁 ESTÁTICOS
# =========================

@app.route("/imagens/<path:path>")
def imagens(path):
    return send_from_directory("imagens", path)

@app.route("/dados/<path:path>")
def dados(path):
    return send_from_directory("dados", path)

@app.route("/admin/<path:path>")
def admin_files(path):
    return send_from_directory("admin", path)

@app.route("/layout/<path:path>")
def layout(path):
    return send_from_directory("layout", path)

@app.route("/<path:path>")
def root_files(path):
    return send_from_directory(".", path)

# =========================
# 📤 UPLOAD + PROCESSAMENTO
# =========================

@app.route("/upload", methods=["POST"])
def upload():
    global processando

    if "file" not in request.files:
        return jsonify({"error": "Arquivo não enviado"}), 400

    file = request.files["file"]

    if file.filename == "":
        return jsonify({"error": "Nome inválido"}), 400

    try:
        filename = secure_filename(file.filename)
        path = os.path.join(UPLOAD_DIR, filename)
        file.save(path)

        def executar():
            global processando
            with lock:
                processando = True
                try:
                    SiteManager()
                finally:
                    processando = False

        threading.Thread(target=executar).start()

        return jsonify({"status": "ok", "message": "Processamento iniciado"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# =========================
# 🔁 REBUILD
# =========================

@app.route("/rebuild", methods=["POST"])
def rebuild():
    global processando

    if processando:
        return jsonify({"status": "busy"})

    def executar():
        global processando
        with lock:
            processando = True
            try:
                SiteManager()
            finally:
                processando = False

    threading.Thread(target=executar).start()

    return jsonify({"status": "ok", "message": "Rebuild iniciado"})

# =========================
# 📊 STATUS
# =========================

@app.route("/status")
def status():
    pendentes = len([
        f for f in os.listdir(UPLOAD_DIR)
        if f.endswith(".zip") or f.endswith(".json")
    ])

    return jsonify({
        "processando": processando,
        "pendentes": pendentes
    })

# =========================
# 📦 DOWNLOAD ZIP
# =========================

@app.route("/download_zip/<regiao>/<local_id>")
def download_zip(regiao, local_id):
    try:
        base_path = os.path.join(BASE_DIR, "dados", "circuitos", regiao, local_id)
        image_dir = os.path.join(base_path, "images")

        if not os.path.exists(base_path):
            return jsonify({"error": "Local não encontrado"}), 404

        memory = io.BytesIO()

        with zipfile.ZipFile(memory, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(base_path):
                for f in files:
                    full = os.path.join(root, f)
                    rel = os.path.relpath(full, base_path)
                    zf.write(full, rel)

        memory.seek(0)

        return send_file(
            memory,
            mimetype="application/zip",
            as_attachment=True,
            download_name=f"{local_id}.zip"
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# =========================
# 🚀 START (RENDER)
# =========================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
