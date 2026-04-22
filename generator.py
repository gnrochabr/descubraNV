import os
import json

def build():
    caminho_script = os.path.dirname(os.path.abspath(__file__))
    base_dir = os.path.join(caminho_script, "dados", "circuitos")
    output_file = os.path.join(caminho_script, "dados", "controller.js")
    
    estrutura_total = {}

    for nome_circuito in os.listdir(base_dir):
        caminho_circuito = os.path.join(base_dir, nome_circuito)
        if os.path.isdir(caminho_circuito):
            # Região técnica usada para fallback administrativo; não deve aparecer no index.
            if nome_circuito == "sem_regiao":
                continue
            config_rel = f"dados/circuitos/{nome_circuito}/config.js"
            estrutura_total[nome_circuito] = {
                "config": config_rel,
                "pontos": []
            }
            for root, dirs, files in os.walk(caminho_circuito):
                for f in files:
                    if f.endswith('.js') and f != 'config.js':
                        nome_id = f.replace('.js', '')
                        abs_path = os.path.join(root, f)
                        rel_path = os.path.relpath(abs_path, caminho_script).replace("\\", "/")
                        estrutura_total[nome_circuito]["pontos"].append({
                            "id": nome_id,
                            "src": rel_path,
                            "var": f"LOCAL_{nome_id.upper()}"
                        })

    js_content = f"""
(function () {{
    const path = window.location.pathname;
    const isLayout = path.includes('/layout/');
    const isAdmin = path.includes('/admin/');
    
    // Define o prefixo relativo para subir pastas se necessário
    const prefixo = (isAdmin || isLayout) ? "../" : "";

    const ESTRUTURA = {json.dumps(estrutura_total, indent=2)};
    let carregados = 0;
    let total = 0;

    Object.values(ESTRUTURA).forEach(c => {{
        total += 1; 
        total += c.pontos.length; 
    }});

    function montarSistema() {{
        window.LOCAIS = {{}};
        window.LISTA_CIRCUITOS = [];

        Object.entries(ESTRUTURA).forEach(([key, circuito]) => {{
            const varConfig = "CONFIG_" + key.toUpperCase();
            if(window[varConfig]) {{
                let cfg = JSON.parse(JSON.stringify(window[varConfig]));
                // Normaliza caminho da capa da região
                cfg.cover = prefixo + cfg.cover;
                window.LISTA_CIRCUITOS.push(cfg);
            }}

            circuito.pontos.forEach(ponto => {{
                if(window[ponto.var]) {{
                    let d = JSON.parse(JSON.stringify(window[ponto.var]));
                    // Normaliza todos os caminhos de imagem do local
                    if(d.hero) d.hero = prefixo + d.hero;
                    if(d.cover) d.cover = prefixo + d.cover;
                    if(d.gallery) d.gallery = d.gallery.map(img => prefixo + img);
                    
                    window.LOCAIS[ponto.id] = d;
                }}
            }});
        }});
        
        console.log("🚀 Sistema Pronto | Prefixo Aplicado: " + (prefixo || "Raiz"));
        window.dispatchEvent(new Event('locais-ready'));
    }}

    Object.values(ESTRUTURA).forEach(circuito => {{
        const sConf = document.createElement('script');
        sConf.src = prefixo + circuito.config;
        sConf.onload = () => {{ if(++carregados === total) montarSistema(); }};
        document.head.appendChild(sConf);

        circuito.pontos.forEach(ponto => {{
            const sLoc = document.createElement('script');
            sLoc.src = prefixo + ponto.src;
            sLoc.onload = () => {{ if(++carregados === total) montarSistema(); }};
            document.head.appendChild(sLoc);
        }});
    }});
}})();
"""
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(js_content)
    print("controller.js atualizado com normalizacao centralizada.")

if __name__ == "__main__":
    build()