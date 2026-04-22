import os
import threading
import io
import json
import re
import ast
import zipfile
from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename

from manager import SiteManager

app = Flask(__name__, template_folder="admin", static_folder=".")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "pendentes")
CIRCUITOS_DIR = os.path.join(BASE_DIR, "dados", "circuitos")
CONTROLLER_PATH = os.path.join(BASE_DIR, "dados", "controller.js")

os.makedirs(UPLOAD_DIR, exist_ok=True)

# 🔒 Controle de execução (evita rodar 2x ao mesmo tempo)
processando = False
lock = threading.Lock()


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


# 🌐 Página admin
@app.route("/")
def index():
    return render_template("dashboard.html")


def _normalize_js_object_string(obj_src):
    # Remove comentários JS para evitar quebra do json.loads
    obj_src = re.sub(r'/\*.*?\*/', '', obj_src, flags=re.DOTALL)
    obj_src = re.sub(r'^\s*//.*$', '', obj_src, flags=re.MULTILINE)
    # Remove comentários inline (sem afetar URLs como https://)
    obj_src = re.sub(r'(^|[^:])//.*$', r'\1', obj_src, flags=re.MULTILINE)
    # Converte chaves sem aspas para JSON válido
    obj_src = re.sub(r'([{,]\s*)([A-Za-z_]\w*)\s*:', r'\1"\2":', obj_src)
    # Remove vírgulas finais inválidas em objetos/arrays
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
        # Fallback para objetos JS com aspas simples e outros detalhes
        py_src = re.sub(r'\btrue\b', 'True', obj_src)
        py_src = re.sub(r'\bfalse\b', 'False', py_src)
        py_src = re.sub(r'\bnull\b', 'None', py_src)
        try:
            data = ast.literal_eval(py_src)
            return data if isinstance(data, dict) else {}
        except (SyntaxError, ValueError):
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
    except json.JSONDecodeError:
        return {}


def _resolve_local_paths(regiao, local_id):
    # Prioriza o mapeamento do controller.js, que já contém id -> src.
    estrutura = parse_controller_estrutura()
    circuito = estrutura.get(regiao, {}) if estrutura else {}
    for ponto in circuito.get("pontos", []):
        if ponto.get("id") == local_id:
            src_rel = ponto.get("src", "")
            if src_rel:
                local_js = os.path.join(BASE_DIR, src_rel.replace("/", os.sep))
                local_dir = os.path.dirname(local_js)
                return local_js, local_dir

    # Fallback para estrutura legada: /regiao/<local_id>/<local_id>.js
    local_dir = os.path.join(CIRCUITOS_DIR, regiao, local_id)
    local_js = os.path.join(local_dir, f"{local_id}.js")
    return local_js, local_dir


def list_locais():
    locais = []
    estrutura = parse_controller_estrutura()
    # Prioriza config.js (array locais) como fonte da lista de IDs.
    # controller.js é usado para resolver caminhos quando pasta != id.
    if estrutura:
        for regiao, circuito in sorted(estrutura.items()):
            cfg_rel = circuito.get("config", "")
            cfg_path = os.path.join(BASE_DIR, cfg_rel.replace("/", os.sep)) if cfg_rel else ""
            regiao_cfg = parse_js_object(cfg_path) if cfg_path else {}
            regiao_title = regiao_cfg.get("texts", {}).get("pt", {}).get("title", regiao)

            ids_locais = regiao_cfg.get("locais", [])
            if not ids_locais:
                # Fallback para quando config.js não trouxer o array locais.
                ids_locais = [p.get("id") for p in circuito.get("pontos", []) if p.get("id")]

            for local_id in ids_locais:
                local_js, _ = _resolve_local_paths(regiao, local_id)
                local_data = parse_js_object(local_js)
                if not local_data:
                    continue
                locais.append({
                    "id": local_id,
                    "regiao": regiao,
                    "regiao_nome": regiao_title,
                    "title": local_data.get("texts", {}).get("pt", {}).get("title", local_id),
                    "subtitle": local_data.get("texts", {}).get("pt", {}).get("subtitle", ""),
                    "hero": local_data.get("hero", ""),
                    "gallery_count": len(local_data.get("gallery", []))
                })
        return locais

    # Fallback: varredura por config.js da região.
    if not os.path.exists(CIRCUITOS_DIR):
        return locais

    for regiao in sorted(os.listdir(CIRCUITOS_DIR)):
        regiao_path = os.path.join(CIRCUITOS_DIR, regiao)
        if not os.path.isdir(regiao_path):
            continue
        regiao_cfg = parse_js_object(os.path.join(regiao_path, "config.js"))
        regiao_title = regiao_cfg.get("texts", {}).get("pt", {}).get("title", regiao)

        for local_id in regiao_cfg.get("locais", []):
            local_js = os.path.join(regiao_path, local_id, f"{local_id}.js")
            local_data = parse_js_object(local_js)
            if not local_data:
                continue
            locais.append({
                "id": local_id,
                "regiao": regiao,
                "regiao_nome": regiao_title,
                "title": local_data.get("texts", {}).get("pt", {}).get("title", local_id),
                "subtitle": local_data.get("texts", {}).get("pt", {}).get("subtitle", ""),
                "hero": local_data.get("hero", ""),
                "gallery_count": len(local_data.get("gallery", []))
            })
    return locais


def list_regioes():
    regioes = []
    estrutura = parse_controller_estrutura()

    if estrutura:
        for regiao, circuito in sorted(estrutura.items()):
            cfg_rel = circuito.get("config", "")
            cfg_path = os.path.join(BASE_DIR, cfg_rel.replace("/", os.sep)) if cfg_rel else ""
            regiao_cfg = parse_js_object(cfg_path) if cfg_path else {}
            ids_locais = regiao_cfg.get("locais", [])
            if not ids_locais:
                ids_locais = [p.get("id") for p in circuito.get("pontos", []) if p.get("id")]

            regioes.append({
                "id": regiao,
                "title": regiao_cfg.get("texts", {}).get("pt", {}).get("title", regiao),
                "subtitle": regiao_cfg.get("texts", {}).get("pt", {}).get("subtitle", ""),
                "cover": regiao_cfg.get("cover", ""),
                "total_locais": len(ids_locais)
            })
        return regioes

    if not os.path.exists(CIRCUITOS_DIR):
        return regioes

    for regiao in sorted(os.listdir(CIRCUITOS_DIR)):
        regiao_path = os.path.join(CIRCUITOS_DIR, regiao)
        if not os.path.isdir(regiao_path):
            continue
        regiao_cfg = parse_js_object(os.path.join(regiao_path, "config.js"))
        ids_locais = regiao_cfg.get("locais", [])
        regioes.append({
            "id": regiao,
            "title": regiao_cfg.get("texts", {}).get("pt", {}).get("title", regiao),
            "subtitle": regiao_cfg.get("texts", {}).get("pt", {}).get("subtitle", ""),
            "cover": regiao_cfg.get("cover", ""),
            "total_locais": len(ids_locais)
        })
    return regioes


# 📤 Upload e processamento
@app.route("/upload", methods=["POST"])
def upload():
    global processando

    if "file" not in request.files:
        return jsonify({"error": "Arquivo não enviado"}), 400

    file = request.files["file"]

    if file.filename == "":
        return jsonify({"error": "Nome de arquivo inválido"}), 400

    try:
        filename = secure_filename(file.filename)
        path = os.path.join(UPLOAD_DIR, filename)
        file.save(path)

        # 🔥 Executa em thread separada
        def executar():
            global processando
            with lock:
                processando = True
                try:
                    SiteManager()
                finally:
                    processando = False

        threading.Thread(target=executar).start()

        return jsonify({
            "status": "ok",
            "message": "Arquivo enviado. Processamento iniciado."
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/dashboard")
def dashboard_data():
    locais = list_locais()
    estrutura = parse_controller_estrutura()
    if estrutura:
        total_regioes = len(estrutura.keys())
    else:
        total_regioes = 0
        if os.path.exists(CIRCUITOS_DIR):
            total_regioes = len([d for d in os.listdir(CIRCUITOS_DIR) if os.path.isdir(os.path.join(CIRCUITOS_DIR, d))])
    return jsonify({
        "total_locais": len(locais),
        "total_regioes": total_regioes,
        "status": "processando" if processando else "ok"
    })


@app.route("/api/locais")
def api_locais():
    return jsonify({"locais": list_locais()})


@app.route("/api/regioes")
def api_regioes():
    return jsonify({"regioes": list_regioes()})


@app.route("/api/local/<regiao>/<local_id>")
def api_local(regiao, local_id):
    local_path, _ = _resolve_local_paths(regiao, local_id)
    data = parse_js_object(local_path)
    if not data:
        return jsonify({"error": "Local não encontrado"}), 404
    return jsonify({
        "regiao": regiao,
        "local": local_id,
        "data": data
    })


@app.route("/api/regiao/<regiao>")
def api_regiao(regiao):
    regiao_path = os.path.join(CIRCUITOS_DIR, regiao)
    cfg_path = os.path.join(regiao_path, "config.js")
    data = parse_js_object(cfg_path)
    if not data:
        return jsonify({"error": "Região não encontrada"}), 404

    image_dir = os.path.join(regiao_path, "images")
    image_files = []
    if os.path.exists(image_dir):
        image_files = sorted([
            f for f in os.listdir(image_dir)
            if os.path.isfile(os.path.join(image_dir, f))
        ])

    return jsonify({
        "regiao": regiao,
        "data": data,
        "images": image_files
    })


@app.route("/delete", methods=["POST"])
def delete_local():
    body = request.get_json(silent=True) or {}
    tipo = body.get("tipo", "local")
    regiao = body.get("regiao")
    local_id = body.get("local")
    if tipo == "local":
        if not regiao or not local_id:
            return jsonify({"error": "regiao e local são obrigatórios"}), 400
    elif tipo == "regiao":
        if not regiao:
            return jsonify({"error": "regiao é obrigatória"}), 400
    else:
        return jsonify({"error": "tipo inválido"}), 400

    payload = {
        "modo": "delete",
        "tipo": tipo,
        "regiao": regiao
    }
    if tipo == "local":
        payload["local"] = local_id
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    pendente_name = f"delete_{regiao}_{local_id}.json" if tipo == "local" else f"delete_regiao_{regiao}.json"
    pendente_path = os.path.join(UPLOAD_DIR, pendente_name)
    with open(pendente_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)

    def executar():
        global processando
        with lock:
            processando = True
            try:
                SiteManager()
            finally:
                processando = False

    threading.Thread(target=executar).start()
    if tipo == "regiao":
        return jsonify({"status": "ok", "message": "Exclusão de região agendada. Locais serão movidos para sem_regiao."})
    return jsonify({"status": "ok", "message": "Exclusão agendada."})


@app.route("/download_zip/<regiao>/<local_id>")
def download_zip(regiao, local_id):
    local_js, local_dir = _resolve_local_paths(regiao, local_id)
    local_data = parse_js_object(local_js)
    if not local_data:
        return jsonify({"error": "Local não encontrado"}), 404

    image_dir = os.path.join(local_dir, "images")
    image_files = []
    if os.path.exists(image_dir):
        image_files = [f for f in os.listdir(image_dir) if os.path.isfile(os.path.join(image_dir, f))]

    hero_file = ""
    if local_data.get("hero"):
        hero_file = os.path.basename(local_data["hero"])

    payload = {
        "modo": "update",
        "tipo": "local",
        "regiao": regiao,
        "local": local_id,
        "cover_file": hero_file,
        "dados": {
            "location": local_data.get("location", {}),
            "texts": local_data.get("texts", {}),
            "gallery": image_files,
            "RAvisionScreen": local_data.get("RAvisionScreen", False),
            "RAvisionlink": local_data.get("RAvisionlink", "")
        }
    }

    memory = io.BytesIO()
    with zipfile.ZipFile(memory, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("config.json", json.dumps(payload, ensure_ascii=False))
        for img in image_files:
            zf.write(os.path.join(image_dir, img), arcname=img)
    memory.seek(0)

    return send_file(
        memory,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"pacote_{local_id}.zip"
    )


# 🔁 Rebuild manual (executa generator/manager sem upload)
@app.route("/rebuild", methods=["POST"])
def rebuild():
    global processando

    if processando:
        return jsonify({"status": "busy", "message": "Sistema já está processando."})

    def executar():
        global processando
        with lock:
            processando = True
            try:
                SiteManager()
            finally:
                processando = False

    threading.Thread(target=executar).start()

    return jsonify({
        "status": "ok",
        "message": "Rebuild iniciado."
    })


# 📊 Status do sistema
@app.route("/status")
def status():
    return jsonify({
        "processando": processando,
        "pendentes": len([
            f for f in os.listdir(UPLOAD_DIR)
            if f.endswith(".zip") or f.endswith(".json")
        ])
    })


# 🧹 Limpar pendentes (opcional)
@app.route("/limpar", methods=["POST"])
def limpar():
    try:
        for f in os.listdir(UPLOAD_DIR):
            path = os.path.join(UPLOAD_DIR, f)
            if os.path.isfile(path):
                os.remove(path)

        return jsonify({"status": "ok", "message": "Pendentes limpos."})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# 🚀 Start
if __name__ == "__main__":
    import os

    try:
        port = int(os.environ.get("PORT", 10000))
    except Exception:
        port = 10000

    try:
        app.run(host="0.0.0.0", port=port)
    except Exception as e:
        print("Erro ao subir o Flask:", e)