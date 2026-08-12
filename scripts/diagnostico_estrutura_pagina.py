"""
diagnostico_estrutura_pagina.py

Inspeciona a estrutura REAL de uma pagina da Wikipedia -- todos os
cabecalhos (h2/h3/h4) e todas as tabelas (com uma amostra das primeiras
colunas/linhas), na ordem em que aparecem no HTML.

Objetivo: entender exatamente como paginas tipo a Liga Europeia e os
campeonatos continentais de 2021+ organizam os grupos, quando isso NAO
aparece como cabecalho antes de cada tabela de partidas.

Uso:
    python diagnostico_estrutura_pagina.py "2023 Asian Men's Volleyball Championship"
"""

import sys
import requests
from bs4 import BeautifulSoup

WIKI_API = "https://en.wikipedia.org/w/api.php"


def fetch_page_html(page_title: str) -> str:
    params = {"action": "parse", "page": page_title, "format": "json", "prop": "text"}
    response = requests.get(WIKI_API, params=params, timeout=30,
                             headers={"User-Agent": "VoleiEloRating/0.1 (projeto pessoal)"})
    response.raise_for_status()
    data = response.json()
    if "error" in data:
        raise ValueError(f"Erro da API: {data['error']}")
    return data["parse"]["text"]["*"]


def resumir_tabela(table_tag) -> str:
    """Amostra rapida do conteudo de uma tabela: cabecalhos de coluna e,
    se houver, o texto da primeira linha de dados."""
    headers = [th.get_text(strip=True) for th in table_tag.find_all("th")][:8]
    primeira_linha = table_tag.find("tr")
    return f"colunas={headers}"


def main():
    if len(sys.argv) < 2:
        print('Uso: python diagnostico_estrutura_pagina.py "Titulo da pagina"')
        sys.exit(1)

    titulo = sys.argv[1]
    print(f"Buscando: \"{titulo}\"\n")
    html = fetch_page_html(titulo)
    soup = BeautifulSoup(html, "html.parser")

    print(f"{'='*70}\nESTRUTURA DA PAGINA (cabecalhos e tabelas, na ordem em que aparecem)\n{'='*70}\n")

    # Percorre todos os elementos relevantes na ordem do documento.
    elementos = soup.find_all(["h2", "h3", "h4", "h5", "table", "p", "div"], recursive=True)

    contador_tabela = 0
    for elem in elementos:
        if elem.name in ("h2", "h3", "h4", "h5"):
            texto = elem.get_text(strip=True)
            if texto:
                print(f"[{elem.name.upper()}] {texto}")
        elif elem.name == "table":
            contador_tabela += 1
            classes = elem.get("class", [])
            print(f"  -> TABELA #{contador_tabela} (class={classes}) -- {resumir_tabela(elem)}")
        elif elem.name in ("p", "div"):
            texto = elem.get_text(strip=True)
            # So mostra paragrafos/divs curtos que pareçam rotulos de fase
            # (evita poluir a saida com paragrafos de texto corrido).
            if texto and len(texto) < 60 and any(
                palavra in texto.lower() for palavra in
                ["pool", "group", "golden", "silver", "preliminary", "final",
                 "round", "semifinal", "quarterfinal", "classification", "division"]
            ):
                print(f"  [P/DIV curto, possivel rotulo] \"{texto}\"")


if __name__ == "__main__":
    main()
