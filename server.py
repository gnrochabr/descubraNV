import os
import re
import json
import zipfile
import shutil
from flask import Flask, jsonify, send_from_directory, request

app = Flask(__name__, static_folder=".", static_url_path="")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DADOS_DIR = os.path.join(BASE_DIR, "dados", "circuitos")
PENDENTES_DIR = os.path.join(BASE_DIR, "pendentes")

# garante pasta
os.makedirs(PENDENTES_DIR, exist_ok=True)


# ==============================
# 🔧 UTIL
# ==============================
def parse_js_object(content):
    match = re.search(r'Object\.freeze\((\{.*\})\);?', content, re.DOTALL)
    if not match:
        return {}

    obj = match.group(1)
    obj = re.sub(r'([{,]\s*)([A-Za-z_]\w*)\s*:', r'\1"\2":', obj)
    obj = obj.replace("'", '"')

    try:
        return json.loads(obj)
    except:
        return {}


# ==============================
# 📍 LISTAGEM
# ==============================
def list_locais():
    locais = []

    for regiao in os.listdir(DADOS_DIR):
        path_regiao = os.path.join(DADOS_DIR, regiao)

        if not os.path.isdir(path_regiao):
            continue

        for root, _, files in os.walk(path_regiao):
            for f in files:
                if f.endswith(".js") and f != "config.js":
                    local_id = f.replace(".js", "")
                    full_path = os.path.join(root, f)

                    try:
                        with open(full_path, "r", encoding="utf-8") as file:
                            data = parse_js_object(file.read())
                    except:
                        data = {}

                    locais.append({
                        "id": local_id,
                        "title": data.get("texts", {}).get("pt", {}).get("title", local_id),
                        "regiao": regiao,
                        "regiao_nome": regiao.replace("_", " ").title(),
                        "src": os.path.relpath(full_path).replace("\\", "/")
                    })

    return locais


def list_regioes():
    regioes = []

    for regiao in os.listdir(DADOS_DIR):
        config_path = os.path.join(DADOS_DIR, regiao, "config.js")

        if not os.path.exists(config_path):
            continue

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = parse_js_object(f.read())
        except:
            data = {}

        regioes.append({
            "id": regiao,
            "title": data.get("texts", {}).get("pt", {}).get("title", regiao)
        })

    return regioes


# ==============================
# 📡 API
# ==============================
@app.route("/api/locais")
def api_locais():
    return jsonify({"locais": list_locais()})

#Página do leo
@app.route("/ra")
def ra():
    return send_from_directory(".", "ra.html")


@app.route("/api/regioes")
def api_regioes():
    return jsonify({"regioes": list_regioes()})


@app.route("/api/dashboard")
def api_dashboard():
    locais = list_locais()
    regioes = list_regioes()

    return jsonify({
        "total_locais": len(locais),
        "total_regioes": len(regioes),
        "status": "ok"
    })


@app.route("/api/local/<regiao>/<local_id>")
def get_local(regiao, local_id):
    path = os.path.join(DADOS_DIR, regiao, local_id, f"{local_id}.js")

    if not os.path.exists(path):
        return jsonify({"error": "Local não encontrado"}), 404

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = parse_js_object(f.read())
    except:
        return jsonify({"error": "Erro ao ler local"}), 500

    return jsonify({"data": data})


# ==============================
# 📦 UPLOAD ZIP (manager)
# ==============================
@app.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify({"status": "erro", "error": "Arquivo não enviado"}), 400

    file = request.files["file"]
    path = os.path.join(PENDENTES_DIR, file.filename)
    file.save(path)

    return jsonify({"status": "ok", "message": "Arquivo enviado para processamento"})


# ==============================
# 🔁 REBUILD
# ==============================
@app.route("/rebuild", methods=["POST"])
def rebuild():
    try:
        from manager import SiteManager
        SiteManager()
        return jsonify({"status": "ok", "message": "Rebuild executado"})
    except Exception as e:
        return jsonify({"status": "erro", "error": str(e)}), 500


# ==============================
# 📥 DOWNLOAD ZIP LOCAL
# ==============================
@app.route("/download_zip/<regiao>/<local_id>")
def download_zip(regiao, local_id):
    path_local = os.path.join(DADOS_DIR, regiao, local_id)

    if not os.path.exists(path_local):
        return jsonify({"error": "Local não encontrado"}), 404

    zip_path = os.path.join(BASE_DIR, f"{local_id}.zip")

    with zipfile.ZipFile(zip_path, "w") as z:
        for root, _, files in os.walk(path_local):
            for f in files:
                full = os.path.join(root, f)
                arc = os.path.relpath(full, path_local)
                z.write(full, arc)

    return send_from_directory(BASE_DIR, f"{local_id}.zip", as_attachment=True)


# ==============================
# 🌐 FRONTEND
# ==============================
@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.route("/admin/<path:path>")
def admin(path):
    return send_from_directory("admin", path)


# ==============================
# ▶️ RUN
# ==============================
if __name__ == "__main__":
    app.run(debug=True)
