"""
orquestrador.py

Liga as pecas que ja construimos, ponta a ponta, para UM torneio especifico:

    VIS (coleta) -> vis_converter (conversao) -> elo_engine (calculo) -> CSVs (persistencia)

Escopo deliberadamente pequeno para o primeiro teste real: um unico
torneio ja validado (Campeonato NORCECA 2013, No=382 no VIS), antes de
generalizar para o catalogo inteiro de eventos.

Uso:
    python orquestrador.py
"""

from __future__ import annotations

import csv
import os
from io import StringIO

import requests
import pandas as pd

from elo_engine import EloEngine, Match, DEFAULT_CONFIG
from vis_converter import convert_vis_matches_xml, ConversionLog
from wikipedia_converter import convert_wikipedia_table_to_matches, find_match_tables


# ---------------------------------------------------------------------------
# Configuracao deste teste (escopo pequeno, de proposito)
# ---------------------------------------------------------------------------

VIS_BASE_URL = "https://www.fivb.org/Vis2009/XmlRequest.asmx"
WIKI_API = "https://en.wikipedia.org/w/api.php"
SEASON = 2013

# Torneios seniores masculinos de 2013 CONFIRMADOS no VIS (com partidas de
# verdade). Europa/Asia/America do Sul NAO entram aqui -- confirmamos que o
# VIS devolve NbItems=0 para esses torneios continentais em 2013 (problema
# na fonte, nao no nosso codigo). Eles vem via Wikipedia agora (ver
# WIKIPEDIA_PAGES_CSV) -- Africa tambem, que nem aparece cadastrada no VIS.
VIS_TOURNAMENTS: list[tuple[int, str]] = [
    (382, "Campeonato NORCECA 2013"),
    (616, "Liga Mundial 2013"),
]

SEED_CSV = "../data/seed_ratings_2011.csv"
WIKIPEDIA_PAGES_CSV = "../data/wikipedia_pages.csv"
PARTIDAS_CSV = "../data/partidas.csv"
RATINGS_ATUAIS_CSV = "../data/ratings_atuais.csv"
HISTORICO_CSV = "../data/historico_ratings.csv"


# ---------------------------------------------------------------------------
# Passo 1: coleta
# ---------------------------------------------------------------------------

def fetch_tournament_matches_xml(tournament_no: int) -> str:
    """Busca as partidas de um torneio no VIS. Levanta excecao clara se
    a requisicao falhar (nao engole erro silenciosamente)."""
    request_xml = (
        f"<Request Type='GetVolleyMatchList' "
        f"Fields='No NoInTournament DateTimeLocal TeamAName TeamBName "
        f"MatchPointsA MatchPointsB PoolName'>"
        f"<Filter NoTournament='{tournament_no}'/>"
        f"</Request>"
    )
    response = requests.get(VIS_BASE_URL, params={"Request": request_xml}, timeout=30)
    response.raise_for_status()
    return response.text


def fetch_wikipedia_page_html(page_title: str) -> str:
    """Busca o HTML renderizado de uma pagina da Wikipedia via API oficial."""
    params = {"action": "parse", "page": page_title, "format": "json", "prop": "text"}
    response = requests.get(WIKI_API, params=params, timeout=30,
                             headers={"User-Agent": "VoleiEloRating/0.1 (projeto pessoal)"})
    response.raise_for_status()
    data = response.json()
    if "error" in data:
        raise ValueError(f"Erro da API da Wikipedia para '{page_title}': {data['error']}")
    return data["parse"]["text"]["*"]


def load_wikipedia_pages_catalog(csv_path: str, season: int) -> list[tuple[str, str]]:
    """Le o catalogo manual de paginas da Wikipedia, filtrando pela temporada.
    Devolve lista de (page_title, event_name_pt)."""
    result = []
    with open(csv_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if int(row["season"]) == season:
                result.append((row["page_title"], row["event_name_pt"]))
    return result


# ---------------------------------------------------------------------------
# Passo 2: persistencia (CSV)
# ---------------------------------------------------------------------------

def save_partidas_csv(matches: list[Match], path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["match_date", "season", "team_a", "team_b",
                          "sets_a", "sets_b", "event", "is_final"])
        for m in matches:
            writer.writerow([m.match_date.isoformat(), m.season, m.team_a,
                              m.team_b, m.sets_a, m.sets_b, m.event, m.is_final])


def save_ratings_atuais_csv(engine: EloEngine, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["codigo", "rating_atual"])
        for team, rating in engine.current_ranking():
            writer.writerow([team, f"{rating:.2f}"])


def save_historico_csv(engine: EloEngine, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["match_date", "season", "team", "opponent",
                          "rating_before", "rating_after", "result", "event"])
        for snap in sorted(engine.history, key=lambda s: s.match_date):
            writer.writerow([snap.match_date.isoformat(), snap.season, snap.team,
                              snap.opponent, f"{snap.rating_before:.2f}",
                              f"{snap.rating_after:.2f}", snap.result, snap.event])


# ---------------------------------------------------------------------------
# Orquestracao
# ---------------------------------------------------------------------------

def main():
    print(f"{'='*70}\nORQUESTRADOR -- temporada {SEASON} "
          f"({len(VIS_TOURNAMENTS)} torneios VIS + fonte Wikipedia)\n{'='*70}\n")

    # 1. Seed real de 2011
    engine = EloEngine(config=DEFAULT_CONFIG)
    n_seed = engine.load_seed_from_csv(SEED_CSV)
    print(f"[1/5] Seed de 2011 carregado: {n_seed} selecoes\n")

    todas_as_partidas: list[Match] = []
    log = ConversionLog()

    # 2. Fonte VIS
    for tournament_no, event_name in VIS_TOURNAMENTS:
        print(f"[2/5] VIS: {event_name} (No={tournament_no})...")
        raw_xml = fetch_tournament_matches_xml(tournament_no)
        partidas = convert_vis_matches_xml(raw_xml, season=SEASON, event_name=event_name, log=log)
        print(f"        {len(partidas)} partidas convertidas")
        todas_as_partidas.extend(partidas)

    # 3. Fonte Wikipedia (catalogo manual de paginas)
    wiki_pages = load_wikipedia_pages_catalog(WIKIPEDIA_PAGES_CSV, SEASON)
    for page_title, event_name in wiki_pages:
        print(f"[3/5] Wikipedia: {event_name} (\"{page_title}\")...")
        html = fetch_wikipedia_page_html(page_title)
        tabelas = pd.read_html(StringIO(html))
        tabelas_de_partidas = find_match_tables(tabelas)
        if not tabelas_de_partidas:
            print(f"        ATENCAO -- nenhuma tabela de partidas reconhecida "
                  f"nesta pagina (formato pode ser diferente do esperado)")
            continue
        total_pagina = 0
        for tabela_partidas in tabelas_de_partidas:
            partidas = convert_wikipedia_table_to_matches(
                tabela_partidas, season=SEASON, event_name=event_name, log=log)
            todas_as_partidas.extend(partidas)
            total_pagina += len(partidas)
        print(f"        {total_pagina} partidas convertidas "
              f"({len(tabelas_de_partidas)} tabela(s) de resultados encontrada(s))")

    print()
    if log.unmapped_teams:
        print(f"ATENCAO -- times nao mapeados em alguma fonte "
              f"(precisam entrar em COUNTRY_NAME_TO_CODE): {log.unmapped_teams}\n")
    if log.skipped_matches:
        print(f"Partidas puladas no total ({len(log.skipped_matches)}):")
        for s in log.skipped_matches:
            print(f"  - {s}")
        print()

    # IMPORTANTE: ordem cronologica GLOBAL (entre TODAS as fontes juntas).
    todas_as_partidas.sort(key=lambda m: m.match_date)

    # 4. Calculo + persistencia
    engine.process_matches(todas_as_partidas)
    save_partidas_csv(todas_as_partidas, PARTIDAS_CSV)
    save_ratings_atuais_csv(engine, RATINGS_ATUAIS_CSV)
    save_historico_csv(engine, HISTORICO_CSV)

    print(f"[4/5] Total processado: {len(todas_as_partidas)} partidas")
    print(f"       Salvo em: {PARTIDAS_CSV}, {RATINGS_ATUAIS_CSV}, {HISTORICO_CSV}")

    print(f"\n{'='*70}\n[5/5] Ranking final das selecoes envolvidas "
          f"(seed 2011 -> apos temporada 2013):\n{'='*70}")
    teams_involved = {m.team_a for m in todas_as_partidas} | {m.team_b for m in todas_as_partidas}
    for team in sorted(teams_involved, key=lambda t: -engine.ratings.get(t, 0)):
        seed = engine._seed_ratings.get(team)
        atual = engine.ratings.get(team, "?")
        if seed is not None:
            print(f"  {team}: {seed:.2f} -> {atual:.2f}")
        else:
            print(f"  {team}: (sem seed 2011) -> {atual}")


if __name__ == "__main__":
    main()
