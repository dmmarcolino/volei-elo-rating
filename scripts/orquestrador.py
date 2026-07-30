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
import requests

from elo_engine import EloEngine, Match, DEFAULT_CONFIG
from vis_converter import convert_vis_matches_xml, ConversionLog


# ---------------------------------------------------------------------------
# Configuracao deste teste (escopo pequeno, de proposito)
# ---------------------------------------------------------------------------

VIS_BASE_URL = "https://www.fivb.org/Vis2009/XmlRequest.asmx"
TOURNAMENT_NO = 382                                  # ja confirmado: NORCECA 2013
SEASON = 2013
EVENT_NAME = "Campeonato NORCECA 2013"

SEED_CSV = "../data/seed_ratings_2011.csv"
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
    print(f"{'='*70}\nORQUESTRADOR -- teste com escopo pequeno: {EVENT_NAME}\n{'='*70}\n")

    # 1. Seed real de 2011
    engine = EloEngine(config=DEFAULT_CONFIG)
    n_seed = engine.load_seed_from_csv(SEED_CSV)
    print(f"[1/4] Seed de 2011 carregado: {n_seed} selecoes")

    # 2. Coleta
    print(f"[2/4] Buscando partidas do torneio No={TOURNAMENT_NO} no VIS...")
    raw_xml = fetch_tournament_matches_xml(TOURNAMENT_NO)
    print(f"       Resposta recebida ({len(raw_xml)} caracteres)")

    # 3. Conversao
    log = ConversionLog()
    matches = convert_vis_matches_xml(raw_xml, season=SEASON, event_name=EVENT_NAME, log=log)
    print(f"[3/4] Partidas convertidas: {len(matches)}")
    if log.unmapped_teams:
        print(f"       ATENCAO -- times nao mapeados (precisam entrar em "
              f"COUNTRY_NAME_TO_CODE): {log.unmapped_teams}")
    if log.skipped_matches:
        print(f"       Partidas puladas ({len(log.skipped_matches)}):")
        for s in log.skipped_matches:
            print(f"         - {s}")

    # IMPORTANTE: processar em ordem cronologica.
    matches.sort(key=lambda m: m.match_date)

    # 4. Calculo + persistencia
    engine.process_matches(matches)
    save_partidas_csv(matches, PARTIDAS_CSV)
    save_ratings_atuais_csv(engine, RATINGS_ATUAIS_CSV)
    save_historico_csv(engine, HISTORICO_CSV)
    print(f"[4/4] Processado e salvo em:")
    print(f"       {PARTIDAS_CSV}")
    print(f"       {RATINGS_ATUAIS_CSV}")
    print(f"       {HISTORICO_CSV}")

    print(f"\n{'='*70}\nRanking das selecoes envolvidas neste torneio (antes -> depois):\n{'='*70}")
    teams_involved = {m.team_a for m in matches} | {m.team_b for m in matches}
    for team in sorted(teams_involved):
        seed = engine._seed_ratings.get(team, "?")
        atual = engine.ratings.get(team, "?")
        print(f"  {team}: {seed:.2f} -> {atual:.2f}" if isinstance(seed, float)
              else f"  {team}: seed nao encontrado -> {atual}")


if __name__ == "__main__":
    main()
