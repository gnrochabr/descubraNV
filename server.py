import os
import threading
import json
import re
import io
import zipfile

from flask import Flask, jsonify, request, send_from_directory, send_file
from werkzeug.utils import secure_filename

from manager import SiteManager

app = Flask(__name__, static_folder=".")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "pendentes")
CONTROLLER_PATH = os.path.join(BASE_DIR, "dados", "controller.js")

os.makedirs(UPLOAD_DIR, exist_ok=True)

processando = False
lock = threading.Lock()

# ==============================
# 🔓 CORS
# ==============================
@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


# ==============================
# 📦 UTIL
# ==============================
def parse_controller_estrutura():
    if not os.path.exists(CONTROLLER_PATH):
        return {}

    with open(CONTROLLER_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    try:
        start = content.find("const ESTRUTURA =")
        if start == -1:
            return {}

        start = content.find("{", start)
        end = content.rfind("}")

        estrutura_str = content[start:end+1]
        return json.loads(estrutura_str)

    except Exception as e:
        print("Erro ao ler controller:", e)
        return {}


def list_locais():
    estrutura = parse_controller_estrutura()
    locais = []

    for regiao, circuito in estrutura.items():
        for ponto in circuito.get("pontos", []):
            if ponto.get("id"):
                locais.append({
                    "id": ponto["id"],
                    "regiao": regiao
                })

    return locais


def list_regioes():
    estrutura = parse_controller_estrutura()
    return list(estrutura.keys())


# ==============================
# 📊 API
# ==============================

@app.route("/api/dashboard")
def dashboard():
    locais = list_locais()
    regioes = list_regioes()

    return jsonify({
        "total_locais": len(locais),
        "total_regioes": len(regioes),
        "status": "processando" if processando else "ok"
    })


@app.route("/api/locais")
def api_locais():
    return jsonify({"locais": list_locais()})


@app.route("/api/regioes")
def api_regioes():
    return jsonify({"regioes": list_regioes()})


# ==============================
# 📤 UPLOAD
# ==============================

@app.route("/upload", methods=["POST"])
def upload():
    global processando

    if "file" not in request.files:
        return jsonify({"error": "Arquivo não enviado"}), 400

    file = request.files["file"]
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

    return jsonify({"status": "ok"})


# ==============================
# 🔁 REBUILD
# ==============================

@app.route("/rebuild", methods=["POST"])
def rebuild():
    global processando

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


# ==============================
# 📥 DOWNLOAD ZIP
# ==============================

@app.route("/download_zip/<regiao>/<local_id>")
def download_zip(regiao, local_id):
    path = os.path.join(BASE_DIR, "dados", "circuitos", regiao, local_id)

    if not os.path.exists(path):
        return jsonify({"error": "Local não encontrado"}), 404

    memory = io.BytesIO()

    with zipfile.ZipFile(memory, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(path):
            for f in files:
                full = os.path.join(root, f)
                arc = os.path.relpath(full, path)
                zf.write(full, arc)

    memory.seek(0)

    return send_file(
        memory,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"{local_id}.zip"
    )


# ==============================
# 📊 STATUS
# ==============================

@app.route("/status")
def status():
    return jsonify({
        "processando": processando,
        "pendentes": len(os.listdir(UPLOAD_DIR))
    })


# ==============================
# 🌐 FRONTEND
# ==============================

# Página inicial
@app.route("/")
def index():
    return send_from_directory(".", "index.html")


# Admin
@app.route("/admin/<path:path>")
def admin(path):
    return send_from_directory("admin", path)


# Arquivos estáticos (imagens, dados, js...)
@app.route("/<path:path>")
def static_files(path):
    return send_from_directory(".", path)


# ==============================
# 🚀 START
# ==============================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
