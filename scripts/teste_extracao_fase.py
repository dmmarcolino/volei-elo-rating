"""
teste_extracao_fase.py

Roda o extrator de fase (find_match_tables_with_phases) de verdade contra
uma pagina real, e mostra exatamente qual fase foi atribuida a cada
tabela encontrada -- para comparar com a estrutura real (visualizada
antes com o diagnostico_estrutura_pagina.py) e achar onde a extracao
esta errando.

Uso:
    python teste_extracao_fase.py "2023 Asian Men's Volleyball Championship"
"""

import sys
import requests

from wikipedia_converter import find_match_tables_with_phases

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


def main():
    if len(sys.argv) < 2:
        print('Uso: python teste_extracao_fase.py "Titulo da pagina"')
        sys.exit(1)

    titulo = sys.argv[1]
    print(f"Buscando: \"{titulo}\"\n")
    html = fetch_page_html(titulo)

    resultado = find_match_tables_with_phases(html)
    print(f"Tabelas de partidas encontradas: {len(resultado)}\n")

    for i, (fase, tabela) in enumerate(resultado, start=1):
        primeira_linha = tabela.iloc[0] if len(tabela) > 0 else None
        amostra = ""
        if primeira_linha is not None:
            amostra = f" | 1a linha: {dict(primeira_linha)}"
        fase_str = f'"{fase}"' if fase else "(VAZIA)"
        print(f"Tabela {i}: fase={fase_str}, {len(tabela)} linha(s){amostra}")


if __name__ == "__main__":
    main()
