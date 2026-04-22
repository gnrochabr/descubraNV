import os
import threading
import io
import json
import re
import ast
import zipfile
from flask import Flask, render_template, request, jsonify, send_file, send_from_directory
from werkzeug.utils import secure_filename

from manager import SiteManager

# =========================
# 🔧 CONFIGURAÇÃO BASE
# =========================

app = Flask(__name__, template_folder="admin", static_folder=".")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "pendentes")
CIRCUITOS_DIR = os.path.join(BASE_DIR, "dados", "circuitos")
CONTROLLER_PATH = os.path.join(BASE_DIR, "dados", "controller.js")

os.makedirs(UPLOAD_DIR, exist_ok=True)

processando = False
lock = threading.Lock()

# =========================
# 🌐 HEADERS (CORS)
# =========================

@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response

# =========================
# 📄 ROTAS FRONTEND
# =========================

@app.route("/")
def index():
    return render_template("dashboard.html")

@app.route("/login.html")
def login():
    return send_from_directory(".", "login.html")

@app.route("/auth.js")
def auth_js():
    return send_from_directory(".", "auth.js")

@app.route("/user.xml")
def user_xml():
    return send_from_directory(".", "user.xml")

@app.route("/imagens/<path:path>")
def imagens(path):
    return send_from_directory("imagens", path)

@app.route("/layout/<path:path>")
def layout(path):
    return send_from_directory("layout", path)

@app.route("/dados/<path:path>")
def dados(path):
    return send_from_directory("dados", path)

@app.route("/<path:path>")
def root_files(path):
    # serve arquivos como listar_locais.html, gestao_user.html etc.
    return send_from_directory(".", path)

# =========================
# 🧠 FUNÇÕES AUXILIARES
# =========================

def _normalize_js_object_string(obj_src):
    obj_src = re.sub(r'/\*.*?\*/', '', obj_src, flags=re.DOTALL)
    obj_src = re.sub(r'^\s*//.*$', '', obj_src, flags=re.MULTILINE)
    obj_src = re.sub(r'(^|[^:])//.*$', r'\1', obj_src, flags=re.MULTILINE)
    obj_src = re.sub(r'([{,]\s*)([A-Za-z_]\w*)\s*:', r'\1"\2":', obj_src)
    obj_src = re.sub(r',(\s*[}\]])', r'\1', obj_src)
    return obj_src


def parse_js_object(path):
    if not os.path.exists(path):
        return {}

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    match = re.search(r'Object\.freeze\((\{.*\})\);?\s*$', content, flags=re.DOTALL)
    if not match:
        return {}

    obj_src = _normalize_js_object_string(match.group(1))

    try:
        return json.loads(obj_src)
    except json.JSONDecodeError:
        py_src = re.sub(r'\btrue\b', 'True', obj_src)
        py_src = re.sub(r'\bfalse\b', 'False', py_src)
        py_src = re.sub(r'\bnull\b', 'None', py_src)
        try:
            data = ast.literal_eval(py_src)
            return data if isinstance(data, dict) else {}
        except:
            return {}


def parse_controller_estrutura():
    if not os.path.exists(CONTROLLER_PATH):
        return {}

    with open(CONTROLLER_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    match = re.search(r'const\s+ESTRUTURA\s*=\s*(\{.*?\});', content, flags=re.DOTALL)
    if not match:
        return {}

    estrutura_src = _normalize_js_object_string(match.group(1))

    try:
        estrutura = json.loads(estrutura_src)
        return estrutura if isinstance(estrutura, dict) else {}
    except:
        return {}

# =========================
# 📊 DADOS (LOCAIS / REGIÕES)
# =========================

def list_locais():
    locais = []
    estrutura = parse_controller_estrutura()

    if estrutura:
        for regiao, circuito in estrutura.items():
            for ponto in circuito.get("pontos", []):
                locais.append({
                    "id": ponto.get("id"),
                    "regiao": regiao,
                    "title": ponto.get("title", ""),
                })
    return locais


def list_regioes():
    estrutura = parse_controller_estrutura()
    return [{"id": k} for k in estrutura.keys()] if estrutura else []

# =========================
# 📡 API
# =========================

@app.route("/api/dashboard")
def dashboard_data():
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


@app.route("/status")
def status():
    return jsonify({"processando": processando})

# =========================
# 🚀 START
# =========================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
