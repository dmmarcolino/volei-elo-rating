"""
orquestrador_multi_ano.py

Versao acelerada do orquestrador: processa varios anos de uma vez (2013 a
2026 por padrao), combinando VIS (busca automatica por palavra-chave,
respeitando as mudancas de nome/formato ao longo do tempo) e Wikipedia
(padrao de titulo de pagina por ano, com tolerancia a pagina inexistente).

Ao final, imprime um RELATORIO-RESUMO com tudo que precisa de atencao
humana -- torneios vazios, times nao mapeados, paginas da Wikipedia que
nao seguiram o padrao esperado -- para revisao unica no fim, em vez de
checagem manual ano a ano.

Uso:
    python orquestrador_multi_ano.py
"""

from __future__ import annotations

import csv
import os
import time
from io import StringIO

import requests
import pandas as pd
import xml.etree.ElementTree as ET

from elo_engine import EloEngine, Match, DEFAULT_CONFIG
from vis_converter import convert_vis_matches_xml, ConversionLog
from wikipedia_converter import convert_wikipedia_table_to_matches, find_match_tables_with_phases

VIS_BASE_URL = "https://www.fivb.org/Vis2009/XmlRequest.asmx"
WIKI_API = "https://en.wikipedia.org/w/api.php"

ANO_INICIAL = 2013
ANO_FINAL = 2026

SEED_CSV = "../data/seed_ratings_2011.csv"
PARTIDAS_CSV = "../data/partidas.csv"
RATINGS_ATUAIS_CSV = "../data/ratings_atuais.csv"
HISTORICO_CSV = "../data/historico_ratings.csv"

# Torneios de 2013 ja confirmados manualmente nas sessoes anteriores --
# mantidos fixos aqui (nao passam pela busca automatica) porque ja sabemos
# exatamente quais sao os numeros certos.
TORNEIOS_2013_CONFIRMADOS: list[tuple[int, str]] = [
    (382, "Campeonato NORCECA 2013"),
    (616, "Liga Mundial 2013"),
    (618, "Grand Champions Cup 2013"),
    (541, "Liga Europeia 2013"),
    (375, "Copa Pan-Americana 2013"),
]

# Palavras-chave para busca automatica no VIS, por categoria -- ajustadas
# pela mudanca de nome real que aconteceu ao longo do tempo (ver catalogo
# de eventos montado no inicio do projeto).
def palavras_chave_vis(ano: int) -> list[tuple[str, str]]:
    """Devolve lista de (palavra-chave de busca, nome do evento em PT)
    apropriada para o ano, respeitando mudancas de calendario/formato."""
    kw = []
    if ano <= 2017:
        kw.append(("World League", f"Liga Mundial {ano}"))
    else:
        kw.append(("Nations League", f"Nations League {ano}"))
    if 2018 <= ano <= 2024:
        kw.append(("Challenger Cup", f"Challenger Cup {ano}"))
    if ano == 2017:
        kw.append(("Grand Champions Cup", f"Grand Champions Cup {ano}"))
    kw.append(("NORCECA", f"Campeonato NORCECA {ano}"))
    kw.append(("European League", f"Liga Europeia {ano}"))
    kw.append(("Pan-American Cup", f"Copa Pan-Americana {ano}"))
    # Jogos Olimpicos: buscamos em 2016, 2020 E 2021 porque a Toquio 2020
    # foi adiada para 2021 -- nao temos certeza sob qual "Season" o VIS
    # catalogou, entao tentamos os dois anos (busca extra e inofensiva
    # se nao encontrar nada).
    if ano in (2016, 2020, 2021, 2024, 2028):
        kw.append(("Olympic", f"Jogos Olimpicos {ano}"))
    # Campeonato Mundial: quadrienal ate 2022, bienal a partir de 2025.
    if ano in (2014, 2018, 2022, 2025, 2027):
        kw.append(("World Championship", f"Campeonato Mundial {ano}"))
    return kw


# Campeonatos continentais so ocorrem em anos IMPARES (confirmado no
# catalogo original). Padrao de titulo de pagina da Wikipedia, baseado
# nos 4 titulos que ja confirmamos funcionar para 2013.
def paginas_wikipedia_continentais(ano: int) -> list[tuple[list[str], str]]:
    """Devolve lista de (lista de titulos candidatos, nome do evento em PT).
    Varios candidatos por evento porque a Wikipedia mudou o padrao de nome
    de algumas paginas ao longo do tempo (ex: Africa passou a incluir
    'Nations' no titulo a partir de certo ano) -- tenta cada um em ordem
    ate um funcionar, em vez de travar no primeiro que nao bate."""
    if ano % 2 == 0:
        return []
    return [
        ([f"{ano} Men's African Volleyball Championship",
          f"{ano} Men's African Nations Volleyball Championship"],
         f"Campeonato Africano {ano}"),
        ([f"{ano} Men's European Volleyball Championship"],
         f"Campeonato Europeu {ano}"),
        ([f"{ano} Asian Men's Volleyball Championship"],
         f"Campeonato Asiatico {ano}"),
        ([f"{ano} Men's South American Volleyball Championship"],
         f"Campeonato Sul-Americano {ano}"),
    ]


def paginas_wikipedia_anuais(ano: int) -> list[tuple[list[str], str]]:
    """Eventos anuais que o VIS raramente cobre bem (Liga Europeia, Copa
    Pan-Americana -- confirmado empiricamente), buscados direto na
    Wikipedia todo ano. Tambem cobre a Liga Mundial/Nations League nos
    anos especificos em que confirmamos que o VIS veio vazio (2014-2016),
    como fonte alternativa -- sem duplicar quando o VIS ja funcionou."""
    paginas = [
        ([f"{ano} Men's European Volleyball League"], f"Liga Europeia {ano}"),
        ([f"{ano} Men's Pan-American Volleyball Cup"], f"Copa Pan-Americana {ano}"),
    ]
    if ano in (2014, 2015, 2016):
        paginas.append(([f"{ano} FIVB Volleyball World League"], f"Liga Mundial {ano}"))
    if ano == 2014:
        paginas.append((["2014 FIVB Men's Volleyball World Championship"], f"Campeonato Mundial {ano}"))
    return paginas


def get_com_retry(url: str, params: dict, headers: dict | None = None,
                   max_tentativas: int = 4) -> requests.Response:
    """GET com espera entre chamadas (para nao martelar a API) e retry com
    backoff exponencial especificamente para erro 429 (rate limit)."""
    for tentativa in range(max_tentativas):
        response = requests.get(url, params=params, timeout=30, headers=headers)
        if response.status_code == 429:
            espera = 5 * (2 ** tentativa)
            print(f"    (rate limit -- aguardando {espera}s antes de tentar de novo)")
            time.sleep(espera)
            continue
        response.raise_for_status()
        time.sleep(0.4)  # pausa educada entre chamadas, mesmo em caso de sucesso
        return response
    raise RuntimeError(f"Excedeu {max_tentativas} tentativas para {url} (rate limit persistente)")


def fetch_tournament_matches_xml(tournament_no: int) -> str:
    request_xml = (
        f"<Request Type='GetVolleyMatchList' "
        f"Fields='No NoInTournament DateTimeLocal TeamAName TeamBName "
        f"MatchPointsA MatchPointsB PoolName'>"
        f"<Filter NoTournament='{tournament_no}'/>"
        f"</Request>"
    )
    response = get_com_retry(VIS_BASE_URL, {"Request": request_xml})
    return response.text


def buscar_torneios_por_palavra(ano: int, keyword: str) -> list[tuple[int, str]]:
    """Busca torneios de um ano contendo a palavra-chave. Devolve lista de
    (No, Name). Nao filtra por 'Men' aqui -- isso fica a cargo de quem chama,
    ja que os nomes variam."""
    request_xml = (
        f"<Request Type='GetVolleyTournamentList' Fields='No Code Name Season'>"
        f"<Filter Seasons='{ano}'/></Request>"
    )
    response = get_com_retry(VIS_BASE_URL, {"Request": request_xml})
    root = ET.fromstring(response.text)
    resultado = []
    for elem in root.findall("VolleyballTournament"):
        name = elem.get("Name", "")
        no_raw = elem.get("No", "").strip()
        if not no_raw.isdigit():
            continue  # entrada sem numero valido -- ignora, nao derruba o script
        if keyword.lower() in name.lower():
            resultado.append((int(no_raw), name))
    return resultado


def fetch_wikipedia_page_html(page_title: str) -> str | None:
    """Devolve o HTML da pagina, ou None se a pagina nao existir (em vez
    de derrubar o script inteiro por causa de um titulo que nao bateu)."""
    params = {"action": "parse", "page": page_title, "format": "json", "prop": "text"}
    response = get_com_retry(WIKI_API, params,
                              headers={"User-Agent": "VoleiEloRating/0.1 (projeto pessoal)"})
    data = response.json()
    if "error" in data:
        return None
    return data["parse"]["text"]["*"]


def main():
    print(f"{'='*70}\nORQUESTRADOR MULTI-ANO -- {ANO_INICIAL} a {ANO_FINAL}\n{'='*70}\n")

    engine = EloEngine(config=DEFAULT_CONFIG)
    n_seed = engine.load_seed_from_csv(SEED_CSV)
    print(f"Seed de 2011 carregado: {n_seed} selecoes\n")

    todas_as_partidas: list[Match] = []
    log = ConversionLog()

    # Relatorio de pendencias, separado do log de conversao (esse aqui e
    # sobre TORNEIOS inteiros que precisam de atencao, nao partidas
    # individuais puladas).
    torneios_vazios: list[str] = []
    paginas_wiki_nao_encontradas: list[str] = []
    paginas_wiki_sem_tabela: list[str] = []

    for ano in range(ANO_INICIAL, ANO_FINAL + 1):
        print(f"\n--- Temporada {ano} ---")

        if ano == 2013:
            torneios_vis = [(no, nome, None) for no, nome in TORNEIOS_2013_CONFIRMADOS]
        else:
            torneios_vis = []
            for keyword, nome_evento in palavras_chave_vis(ano):
                try:
                    encontrados = buscar_torneios_por_palavra(ano, keyword)
                except Exception as e:
                    torneios_vazios.append(f"{ano}: ERRO ao buscar '{keyword}' -- {e}")
                    continue
                # Preferencia por nomes que mencionem "Men" explicitamente
                # quando houver mais de um resultado (evita pegar a versao
                # feminina por engano); senao usa o unico que apareceu.
                candidatos_m = [e for e in encontrados if "women" not in e[1].lower()]
                if candidatos_m:
                    no, nome_real = candidatos_m[0]
                    torneios_vis.append((no, nome_evento, keyword))
                else:
                    torneios_vazios.append(f"{ano}: nenhum torneio encontrado para '{keyword}'")

        # Rastreia quais palavras-chave ja tiveram sucesso via VIS nesta
        # temporada, para NAO buscar de novo na Wikipedia e duplicar
        # partidas (bug real que aconteceu com Liga Europeia 2026).
        cobertos_pelo_vis: set[str] = set()

        for tournament_no, event_name, keyword_origem in torneios_vis:
            try:
                raw_xml = fetch_tournament_matches_xml(tournament_no)
                partidas = convert_vis_matches_xml(raw_xml, season=ano, event_name=event_name, log=log)
            except Exception as e:
                torneios_vazios.append(f"{event_name} (No={tournament_no}): ERRO -- {e}")
                continue
            if not partidas:
                torneios_vazios.append(f"{event_name} (No={tournament_no}): 0 partidas no VIS")
            else:
                print(f"  VIS: {event_name} -- {len(partidas)} partidas")
                if keyword_origem:
                    cobertos_pelo_vis.add(keyword_origem)
            todas_as_partidas.extend(partidas)

        paginas_a_buscar = paginas_wikipedia_continentais(ano) + paginas_wikipedia_anuais(ano)
        for candidate_titles, event_name in paginas_a_buscar:
            # Pula Liga Europeia / Copa Pan-Americana / Liga Mundial se o
            # VIS ja trouxe essa mesma competicao nesta temporada -- evita
            # contar a mesma partida duas vezes.
            if "Liga Europeia" in event_name and "European League" in cobertos_pelo_vis:
                continue
            if "Copa Pan-Americana" in event_name and "Pan-American Cup" in cobertos_pelo_vis:
                continue
            if "Liga Mundial" in event_name and ("World League" in cobertos_pelo_vis
                                                  or "Nations League" in cobertos_pelo_vis):
                continue
            if "Campeonato Mundial" in event_name and "World Championship" in cobertos_pelo_vis:
                continue
            html = None
            titulo_usado = None
            for page_title in candidate_titles:
                try:
                    html = fetch_wikipedia_page_html(page_title)
                except Exception as e:
                    continue
                if html is not None:
                    titulo_usado = page_title
                    break
            if html is None:
                paginas_wiki_nao_encontradas.append(
                    f"{event_name}: nenhum destes titulos funcionou -- {candidate_titles} "
                    f"(pode ser que o torneio nao tenha ocorrido nesse ano por mudanca de calendario)")
                continue
            try:
                tabelas_com_fase = find_match_tables_with_phases(html)
            except Exception as e:
                paginas_wiki_sem_tabela.append(f"{event_name}: \"{titulo_usado}\" -- ERRO ao ler tabelas: {e}")
                continue
            if not tabelas_com_fase:
                paginas_wiki_sem_tabela.append(f"{event_name}: \"{titulo_usado}\"")
                continue
            total_pagina = 0
            for fase, tabela in tabelas_com_fase:
                partidas = convert_wikipedia_table_to_matches(
                    tabela, season=ano, event_name=event_name, log=log, fase=fase)
                todas_as_partidas.extend(partidas)
                total_pagina += len(partidas)
            print(f"  Wikipedia: {event_name} -- {total_pagina} partidas "
                  f"({len(tabelas_com_fase)} tabela(s))")

    # Ordem cronologica GLOBAL antes de processar.
    todas_as_partidas.sort(key=lambda m: m.match_date)
    engine.process_matches(todas_as_partidas)

    os.makedirs(os.path.dirname(PARTIDAS_CSV), exist_ok=True)
    with open(PARTIDAS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["match_date", "season", "team_a", "team_b", "sets_a", "sets_b", "event", "is_final", "fase"])
        for m in todas_as_partidas:
            writer.writerow([m.match_date.isoformat(), m.season, m.team_a, m.team_b,
                              m.sets_a, m.sets_b, m.event, m.is_final, m.fase])

    with open(RATINGS_ATUAIS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["codigo", "rating_atual"])
        for team, rating in engine.current_ranking():
            writer.writerow([team, f"{rating:.2f}"])

    with open(HISTORICO_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["match_date", "season", "team", "opponent", "rating_before",
                          "rating_after", "result", "event"])
        for snap in sorted(engine.history, key=lambda s: s.match_date):
            writer.writerow([snap.match_date.isoformat(), snap.season, snap.team, snap.opponent,
                              f"{snap.rating_before:.2f}", f"{snap.rating_after:.2f}",
                              snap.result, snap.event])

    # ---------------------------------------------------------------
    # RELATORIO-RESUMO -- e aqui que voce deve olhar primeiro.
    # ---------------------------------------------------------------
    print(f"\n\n{'#'*70}")
    print(f"# RELATORIO-RESUMO -- REVISAR ANTES DE PUBLICAR")
    print(f"{'#'*70}\n")

    print(f"Total processado: {len(todas_as_partidas)} partidas, "
          f"{ANO_FINAL - ANO_INICIAL + 1} temporadas\n")

    if torneios_vazios:
        print(f"TORNEIOS VAZIOS OU NAO ENCONTRADOS NO VIS ({len(torneios_vazios)}):")
        for t in torneios_vazios:
            print(f"  - {t}")
        print()

    if paginas_wiki_nao_encontradas:
        print(f"PAGINAS DA WIKIPEDIA NAO ENCONTRADAS -- titulo pode ter formato "
              f"diferente nesse ano ({len(paginas_wiki_nao_encontradas)}):")
        for p in paginas_wiki_nao_encontradas:
            print(f"  - {p}")
        print()

    if paginas_wiki_sem_tabela:
        print(f"PAGINAS DA WIKIPEDIA SEM TABELA DE PARTIDAS RECONHECIDA "
              f"({len(paginas_wiki_sem_tabela)}):")
        for p in paginas_wiki_sem_tabela:
            print(f"  - {p}")
        print()

    if log.unmapped_teams:
        print(f"TIMES NAO MAPEADOS -- adicionar em COUNTRY_NAME_TO_CODE "
              f"({len(log.unmapped_teams)}):")
        print(f"  {sorted(log.unmapped_teams)}")
        print()

    if log.skipped_matches:
        print(f"PARTIDAS PULADAS POR OUTROS MOTIVOS ({len(log.skipped_matches)}):")
        for s in log.skipped_matches[:30]:
            print(f"  - {s}")
        if len(log.skipped_matches) > 30:
            print(f"  ... e mais {len(log.skipped_matches) - 30}")
        print()

    if not any([torneios_vazios, paginas_wiki_nao_encontradas, paginas_wiki_sem_tabela,
                log.unmapped_teams, log.skipped_matches]):
        print("Nenhuma pendencia -- tudo processado sem avisos.")


if __name__ == "__main__":
    main()
