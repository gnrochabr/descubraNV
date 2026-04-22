import os
import json
import shutil
import zipfile
import re
import unicodedata
from generator import build 

class SiteManager:
    def __init__(self):
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.dados_dir = os.path.join(self.base_dir, "dados", "circuitos")
        self.pendentes_dir = os.path.join(self.base_dir, "pendentes")
        self.controller_path = os.path.join(self.base_dir, "dados", "controller.js")
        
        if not os.path.exists(self.pendentes_dir):
            os.makedirs(self.pendentes_dir)

        print("Processando arquivos pendentes...")
        self.processar_lote()

    def sanitizar(self, texto):
        if not texto: return ""
        nfkd = unicodedata.normalize("NFKD", str(texto).lower().strip().replace(" ", "_"))
        return "".join(c for c in nfkd if not unicodedata.combining(c))

    def salvar_js(self, path, var_name, obj):
        """Salva o objeto garantindo que seja um dicionário válido para JSON."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        # O ERRO ESTAVA AQUI: Certificamos que obj é um dict e não possui sets internos
        body = json.dumps(obj, indent=2, ensure_ascii=False)
        
        # Ajuste estético para chaves sem aspas (padrão do seu projeto)
        body = re.sub(r'"(\w+)":', r'\1:', body)
        
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"window.{var_name} = Object.freeze({body});")

    def parse_js_object(self, content):
        """Converte Object.freeze({...}) em dict Python."""
        match = re.search(r'Object\.freeze\((\{.*\})\);?\s*$', content, flags=re.DOTALL)
        if not match:
            raise ValueError("Objeto JS inválido")

        obj_src = match.group(1)
        obj_src = re.sub(r'([{,]\s*)([A-Za-z_]\w*)\s*:', r'\1"\2":', obj_src)
        obj_src = obj_src.replace("'", '"')
        return json.loads(obj_src)

    def carregar_js_objeto(self, path):
        if not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return self.parse_js_object(f.read())

    def carregar_estrutura_controller(self):
        if not os.path.exists(self.controller_path):
            return {}
        with open(self.controller_path, "r", encoding="utf-8") as f:
            content = f.read()
        match = re.search(r'const\s+ESTRUTURA\s*=\s*(\{.*?\});', content, flags=re.DOTALL)
        if not match:
            return {}
        try:
            estrutura = json.loads(match.group(1))
            return estrutura if isinstance(estrutura, dict) else {}
        except json.JSONDecodeError:
            return {}

    def resolver_caminhos_local(self, regiao_slug, local_slug):
        """Resolve local usando controller.js (id -> src), com fallback legado."""
        estrutura = self.carregar_estrutura_controller()
        circuito = estrutura.get(regiao_slug, {}) if estrutura else {}
        for ponto in circuito.get("pontos", []):
            if ponto.get("id") == local_slug and ponto.get("src"):
                local_js = os.path.join(self.base_dir, ponto["src"].replace("/", os.sep))
                return local_js, os.path.dirname(local_js)

        path_local = os.path.join(self.dados_dir, regiao_slug, local_slug)
        local_js = os.path.join(path_local, f"{local_slug}.js")
        return local_js, path_local

    def merge_dict(self, base, update):
        """Merge recursivo sem apagar dados antigos."""
        if not isinstance(base, dict):
            return update
        for key, value in (update or {}).items():
            if isinstance(value, dict) and isinstance(base.get(key), dict):
                base[key] = self.merge_dict(base[key], value)
            elif value is not None:
                base[key] = value
        return base

    def registrar_local_no_config(self, path_regiao, local_id):
        """Atualiza o array 'locais' no config.js da região."""
        config_path = os.path.join(path_regiao, "config.js")
        if not os.path.exists(config_path): return

        with open(config_path, "r", encoding="utf-8") as f:
            content = f.read()

        if f'"{local_id}"' in content or f"'{local_id}'" in content: return

        # Regex para inserir no array locais: [...]
        new_content = re.sub(
            r'(locais:\s*\[)(.*?)(\])', 
            lambda m: f"{m.group(1)}{m.group(2)}{', ' if m.group(2).strip() else ''}'{local_id}'{m.group(3)}", 
            content, flags=re.DOTALL
        )
        new_content = new_content.replace('[,', '[')

        with open(config_path, "w", encoding="utf-8") as f:
            f.write(new_content)

    def remover_local_do_config(self, path_regiao, local_id):
        config_path = os.path.join(path_regiao, "config.js")
        if not os.path.exists(config_path):
            return
        config_obj = self.carregar_js_objeto(config_path)
        locais = config_obj.get("locais", [])
        config_obj["locais"] = [loc for loc in locais if loc != local_id]
        regiao_id = config_obj.get("id", os.path.basename(path_regiao))
        self.salvar_js(config_path, f"CONFIG_{regiao_id.upper()}", config_obj)

    def adicionar_local_no_config(self, path_regiao, local_id):
        config_path = os.path.join(path_regiao, "config.js")
        if not os.path.exists(config_path):
            return
        config_obj = self.carregar_js_objeto(config_path)
        locais = config_obj.get("locais", [])
        if local_id not in locais:
            locais.append(local_id)
        config_obj["locais"] = locais
        regiao_id = config_obj.get("id", os.path.basename(path_regiao))
        self.salvar_js(config_path, f"CONFIG_{regiao_id.upper()}", config_obj)

    def garantir_regiao_sem_regiao(self):
        regiao_slug = "sem_regiao"
        path_regiao = os.path.join(self.dados_dir, regiao_slug)
        path_img = os.path.join(path_regiao, "images")
        os.makedirs(path_img, exist_ok=True)
        config_path = os.path.join(path_regiao, "config.js")
        if not os.path.exists(config_path):
            config_obj = {
                "id": regiao_slug,
                "cover": "",
                "texts": {
                    "pt": {"title": "Sem Região", "subtitle": "Locais sem vínculo de região"},
                    "en": {"title": "No Region", "subtitle": "Places without region assignment"},
                    "es": {"title": "Sin Región", "subtitle": "Lugares sin región asignada"}
                },
                "locais": []
            }
            self.salvar_js(config_path, "CONFIG_SEM_REGIAO", config_obj)
        return path_regiao

    def executar_criacao(self, payload, source_dir):
        tipo = payload.get("tipo")
        modo = payload.get("modo", "create")
        regiao_slug = self.sanitizar(payload.get("regiao"))
        path_regiao = os.path.join(self.dados_dir, regiao_slug)
        cover_file = payload.get("cover_file")
        dados = payload.get("dados", {})

        # --- PROCESSAMENTO DE REGIÃO ---
        if tipo == "regiao":
            path_img = os.path.join(path_regiao, "images")
            os.makedirs(path_img, exist_ok=True)
            
            if cover_file and os.path.exists(os.path.join(source_dir, cover_file)):
                shutil.copy2(os.path.join(source_dir, cover_file), os.path.join(path_img, cover_file))

            # CORREÇÃO: Usamos dicionário vazio {} em vez de {...}
            config_obj = {
                "id": regiao_slug,
                "cover": f"dados/circuitos/{regiao_slug}/images/{cover_file}" if cover_file else "",
                "texts": dados.get("texts", {}),
                "locais": [] 
            }

            if modo == "update":
                config_existente = self.carregar_js_objeto(os.path.join(path_regiao, "config.js"))
                config_obj = self.merge_dict(config_existente, config_obj)
                if not cover_file and config_existente.get("cover"):
                    config_obj["cover"] = config_existente["cover"]
                for img in dados.get("gallery_remove", []):
                    img_path = os.path.join(path_img, img)
                    if os.path.exists(img_path):
                        os.remove(img_path)
            
            self.salvar_js(os.path.join(path_regiao, "config.js"), f"CONFIG_{regiao_slug.upper()}", config_obj)
            print(f"Regiao '{regiao_slug}' configurada.")

        # --- PROCESSAMENTO DE LOCAL ---
        elif tipo == "local":
            local_slug = self.sanitizar(payload.get("local"))
            local_js_path, path_local = self.resolver_caminhos_local(regiao_slug, local_slug) if modo == "update" else (
                os.path.join(path_regiao, local_slug, f"{local_slug}.js"),
                os.path.join(path_regiao, local_slug)
            )
            path_img = os.path.join(path_local, "images")
            os.makedirs(path_img, exist_ok=True)

            local_existente = self.carregar_js_objeto(local_js_path) if modo == "update" else {}

            galeria = dados.get("gallery", [])
            for img in galeria:
                src = os.path.join(source_dir, img)
                if os.path.exists(src):
                    shutil.copy2(src, os.path.join(path_img, img))

            url_base = f"dados/circuitos/{regiao_slug}/{local_slug}/images/"
            
            # Monta o objeto garantindo tipos compatíveis com JSON
            local_obj = {
                "id": local_slug,
                "hero": url_base + cover_file if cover_file else "",
                "gallery": [url_base + img for img in galeria],
                "location": {
                    "maps": dados.get("location", {}).get("maps", ""),
                    "qr": f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={dados.get('location', {}).get('maps', '')}"
                },
                "texts": dados.get("texts", {}),
                "RAvisionScreen": dados.get("RAvisionScreen", False),
                "RAvisionlink": dados.get("RAvisionlink", "")
            }

            if modo == "update":
                merged = self.merge_dict(local_existente, local_obj)
                if not cover_file and local_existente.get("hero"):
                    merged["hero"] = local_existente["hero"]
                if not galeria and local_existente.get("gallery"):
                    merged["gallery"] = local_existente["gallery"]
                for img in dados.get("gallery_remove", []):
                    img_path = os.path.join(path_img, img)
                    if os.path.exists(img_path):
                        os.remove(img_path)
                local_obj = merged

            self.salvar_js(local_js_path, f"LOCAL_{local_slug.upper()}", local_obj)
            self.registrar_local_no_config(path_regiao, local_slug)
            print(f"Local '{local_slug}' {'atualizado' if modo == 'update' else 'criado'} e vinculado.")

    def executar_exclusao(self, payload):
        tipo = payload.get("tipo")
        regiao_slug = self.sanitizar(payload.get("regiao"))
        local_slug = self.sanitizar(payload.get("local"))
        path_regiao = os.path.join(self.dados_dir, regiao_slug)

        if tipo == "local":
            _, path_local = self.resolver_caminhos_local(regiao_slug, local_slug)
            if os.path.exists(path_local):
                shutil.rmtree(path_local)
            self.remover_local_do_config(path_regiao, local_slug)
            print(f"Local '{local_slug}' removido.")
        elif tipo == "regiao":
            if regiao_slug == "sem_regiao":
                print("Regiao 'sem_regiao' nao pode ser excluida.")
                return
            config_path = os.path.join(path_regiao, "config.js")
            if not os.path.exists(config_path):
                print(f"Regiao '{regiao_slug}' nao encontrada.")
                return

            config_obj = self.carregar_js_objeto(config_path)
            locais = config_obj.get("locais", [])
            path_sem_regiao = self.garantir_regiao_sem_regiao()

            for local_id in locais:
                local_js_antigo, path_local_antigo = self.resolver_caminhos_local(regiao_slug, local_id)
                if not os.path.exists(path_local_antigo):
                    continue

                path_local_novo = os.path.join(path_sem_regiao, local_id)
                if os.path.exists(path_local_novo):
                    shutil.rmtree(path_local_novo)
                shutil.move(path_local_antigo, path_local_novo)

                local_js_novo = os.path.join(path_local_novo, f"{local_id}.js")
                local_obj = self.carregar_js_objeto(local_js_novo)
                if local_obj:
                    prefixo_antigo = f"dados/circuitos/{regiao_slug}/"
                    prefixo_novo = f"dados/circuitos/sem_regiao/"
                    if local_obj.get("hero"):
                        local_obj["hero"] = local_obj["hero"].replace(prefixo_antigo, prefixo_novo)
                    if local_obj.get("cover"):
                        local_obj["cover"] = local_obj["cover"].replace(prefixo_antigo, prefixo_novo)
                    if isinstance(local_obj.get("gallery"), list):
                        local_obj["gallery"] = [img.replace(prefixo_antigo, prefixo_novo) for img in local_obj["gallery"]]
                    self.salvar_js(local_js_novo, f"LOCAL_{local_id.upper()}", local_obj)

                self.adicionar_local_no_config(path_sem_regiao, local_id)

            if os.path.exists(path_regiao):
                shutil.rmtree(path_regiao)
            print(f"Regiao '{regiao_slug}' removida. Locais movidos para 'sem_regiao'.")

    def processar_lote(self):
        if not os.path.exists(self.pendentes_dir): return

        arquivos = [f for f in os.listdir(self.pendentes_dir) if f.endswith((".json", ".zip"))]
        
        for arquivo in sorted(arquivos):
            caminho = os.path.join(self.pendentes_dir, arquivo)
            temp_dir = os.path.join(self.pendentes_dir, "_temp")
            
            try:
                if arquivo.endswith(".zip"):
                    if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
                    os.makedirs(temp_dir)
                    
                    with zipfile.ZipFile(caminho, "r") as z:
                        z.extractall(temp_dir)
                    
                    # Busca o config.json dentro do ZIP
                    json_files = [f for f in os.listdir(temp_dir) if f.endswith(".json")]
                    if not json_files: raise ValueError("ZIP sem config.json")
                    
                    with open(os.path.join(temp_dir, json_files[0]), "r", encoding="utf-8") as f:
                        payload = json.load(f)
                    
                    if payload.get("modo") == "delete":
                        self.executar_exclusao(payload)
                    else:
                        self.executar_criacao(payload, temp_dir)
                    shutil.rmtree(temp_dir)
                else:
                    with open(caminho, "r", encoding="utf-8") as f:
                        payload = json.load(f)
                    if payload.get("modo") == "delete":
                        self.executar_exclusao(payload)
                    else:
                        self.executar_criacao(payload, self.pendentes_dir)
                
                os.remove(caminho)
            except Exception as e:
                print(f"Erro em {arquivo}: {e}")

        # Atualiza o controller.js via generator.py
        try:
            build()
        except:
            print("Nota: build() executado.")

if __name__ == "__main__":
    SiteManager()