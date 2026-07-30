"""
buscar_torneio.py

Utilitario para localizar o numero (No) de um torneio no VIS, buscando
por palavra-chave no nome, dentro de uma temporada especifica.

Uso:
    python buscar_torneio.py 2013 "African"
    python buscar_torneio.py 2013 "European"
    python buscar_torneio.py 2013 "South American"
"""

import sys
import requests
import xml.etree.ElementTree as ET

BASE_URL = "https://www.fivb.org/Vis2009/XmlRequest.asmx"


def buscar(season: int, keyword: str) -> None:
    request_xml = (
        f"<Request Type='GetVolleyTournamentList' "
        f"Fields='No Code Name Season'>"
        f"<Filter Seasons='{season}'/>"
        f"</Request>"
    )
    response = requests.get(BASE_URL, params={"Request": request_xml}, timeout=30)
    response.raise_for_status()

    root = ET.fromstring(response.text)
    keyword_lower = keyword.lower()
    encontrados = []

    for elem in root.findall("VolleyballTournament"):
        name = elem.get("Name", "")
        if keyword_lower in name.lower():
            encontrados.append((elem.get("No"), elem.get("Code"), name))

    print(f"\nTorneios de {season} contendo '{keyword}':\n")
    if not encontrados:
        print("  (nenhum encontrado -- tente outra palavra-chave, "
              "ex: em ingles, ou uma parte menor do nome)")
    for no, code, name in encontrados:
        print(f"  No={no}  Code={code}  Name=\"{name}\"")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Uso: python buscar_torneio.py <temporada> <palavra-chave>")
        print('Exemplo: python buscar_torneio.py 2013 "African"')
        sys.exit(1)

    season = int(sys.argv[1])
    keyword = sys.argv[2]
    buscar(season, keyword)
