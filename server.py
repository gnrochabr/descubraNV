import os
import re
import json
from flask import Flask, jsonify, request, send_from_directory
from manager import SiteManager
from generator import build

app = Flask(__name__, static_folder=".", static_url_path="")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DADOS_DIR = os.path.join(BASE_DIR, "dados")
PENDENTES_DIR = os.path.join(BASE_DIR, "pendentes")


# =========================
# 🔧 UTIL: carregar controller.js
# =========================
def carregar_estrutura():
    controller_path = os.path.join(DADOS_DIR, "controller.js")

    if not os.path.exists(controller_path):
        return {}

    with open(controller_path, "r", encoding="utf-8") as f:
        content = f.read()

    match = re.search(r'const ESTRUTURA = (\{.*?\});', content, re.DOTALL)

    if not match:
        return {}

    try:
        return json.loads(match.group(1))
    except Exception as e:
        print("Erro ao parsear controller:", e)
        return {}


# =========================
# 📊 DADOS
# =========================
def list_regioes():
    estrutura = carregar_estrutura()
    return [
        {
            "id": slug,
            "total_locais": len(dados.get("pontos", []))
        }
        for slug, dados in estrutura.items()
    ]


def list_locais():
    estrutura = carregar_estrutura()
    locais = []

    for regiao, dados in estrutura.items():
        for ponto in dados.get("pontos", []):
            locais.append({
                "id": ponto["id"],
                "regiao": regiao,
                "src": ponto["src"]
            })

    return locais


# =========================
# 🌐 ROTAS API
# =========================
@app.route("/api/dashboard")
def api_dashboard():
    try:
        estrutura = carregar_estrutura()

        total_regioes = len(estrutura)
        total_locais = sum(
            len(c.get("pontos", [])) for c in estrutura.values()
        )

        return jsonify({
            "total_locais": total_locais,
            "total_regioes": total_regioes,
            "status": "ok"
        })

    except Exception as e:
        print("Erro dashboard:", e)
        return jsonify({
            "total_locais": 0,
            "total_regioes": 0,
            "status": "erro"
        })


@app.route("/api/locais")
def api_locais():
    return jsonify({"locais": list_locais()})


@app.route("/api/regioes")
def api_regioes():
    return jsonify({"regioes": list_regioes()})


# =========================
# 📦 UPLOAD (ZIP / JSON)
# =========================
@app.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify({"error": "Arquivo não enviado"}), 400

    file = request.files["file"]

    if file.filename == "":
        return jsonify({"error": "Nome inválido"}), 400

    os.makedirs(PENDENTES_DIR, exist_ok=True)

    caminho = os.path.join(PENDENTES_DIR, file.filename)
    file.save(caminho)

    return jsonify({"message": "Arquivo enviado com sucesso"})


# =========================
# 🔁 REBUILD
# =========================
@app.route("/rebuild", methods=["POST"])
def rebuild():
    try:
        SiteManager()  # processa pendentes
        build()        # gera controller.js

        return jsonify({"message": "Rebuild concluído com sucesso"})
    except Exception as e:
        print("Erro rebuild:", e)
        return jsonify({"error": str(e)}), 500


# =========================
# 🌍 SERVIR FRONTEND
# =========================

# Página inicial
@app.route("/")
def index():
    return send_from_directory(BASE_DIR, "index.html")


# Admin
@app.route("/admin/")
@app.route("/admin/<path:path>")
def admin(path="login.html"):
    return send_from_directory(os.path.join(BASE_DIR, "admin"), path)


# Arquivos estáticos (CSS, JS, imagens, dados...)
@app.route("/<path:path>")
def static_files(path):
    return send_from_directory(BASE_DIR, path)


# =========================
# 🚀 START
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
