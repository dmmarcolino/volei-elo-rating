"""
test_wikipedia_api.py

Teste pontual: buscar os resultados do Campeonato Africano 2013 (que o VIS
NAO tem) via API oficial da Wikipedia, e tentar extrair a tabela de
partidas de forma estruturada.

Uso legal: o conteudo textual da Wikipedia e licenciado sob CC BY-SA, que
permite reuso e extracao de dados com atribuicao -- bem diferente da
proibicao de scraping que encontramos no Volleybox.

Requisitos:
    pip install requests pandas lxml

Uso:
    python test_wikipedia_api.py
"""

import requests
import pandas as pd
from io import StringIO

WIKI_API = "https://en.wikipedia.org/w/api.php"
PAGE_TITLE = "2013 Men's African Volleyball Championship"


def fetch_page_html(title: str) -> str:
    """Busca o HTML renderizado de uma pagina da Wikipedia via API oficial
    (nao e scraping de HTML bruto do site -- e uma chamada de API documentada)."""
    params = {
        "action": "parse",
        "page": title,
        "format": "json",
        "prop": "text",
    }
    response = requests.get(WIKI_API, params=params, timeout=30,
                             headers={"User-Agent": "VoleiEloRating/0.1 (projeto pessoal)"})
    response.raise_for_status()
    data = response.json()
    if "error" in data:
        raise ValueError(f"Erro da API da Wikipedia: {data['error']}")
    return data["parse"]["text"]["*"]


def main():
    print(f"Buscando: \"{PAGE_TITLE}\"\n")
    html = fetch_page_html(PAGE_TITLE)
    print(f"HTML recebido ({len(html)} caracteres)\n")

    # pandas consegue extrair TODAS as tabelas HTML da pagina de uma vez.
    tabelas = pd.read_html(StringIO(html))
    print(f"Tabelas encontradas na pagina: {len(tabelas)}\n")

    for i, tabela in enumerate(tabelas):
        print(f"--- Tabela {i} (colunas: {list(tabela.columns)}) ---")
        print(tabela.head(3))
        print()


if __name__ == "__main__":
    main()
