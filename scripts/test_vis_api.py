"""
test_vis_api.py

Script de teste manual para a API publica FIVB VIS (Volleyball Information
System). Objetivo: trazer uma amostra REAL de dados, pra calibrarmos o
conversor de dados -> Match com o formato exato que a API devolve
(em vez de confiar cegamente na documentacao, que pode estar desatualizada
ou incompleta).

Requisitos:
    pip install requests

Uso:
    python test_vis_api.py
"""

import requests

BASE_URL = "https://www.fivb.org/Vis2009/XmlRequest.asmx"


def fetch(request_xml: str) -> str:
    """Envia uma requisicao ao VIS e devolve o texto bruto da resposta."""
    response = requests.get(BASE_URL, params={"Request": request_xml}, timeout=30)
    response.raise_for_status()
    return response.text


def passo_1_listar_torneios(season: int) -> None:
    """Lista os torneios de volei masculino (selecoes) de uma temporada."""
    print(f"\n{'='*70}")
    print(f"PASSO 1: Listando torneios da temporada {season}")
    print(f"{'='*70}\n")

    request_xml = (
        f"<Request Type='GetVolleyTournamentList' "
        f"Fields='No Code Name Season StartDateResult EndDateResult'>"
        f"<Filter Seasons='{season}'/>"
        f"</Request>"
    )

    try:
        raw = fetch(request_xml)
        print(raw[:4000])  # limita a exibicao pra nao poluir o terminal
        if len(raw) > 4000:
            print(f"\n... (resposta truncada, total de {len(raw)} caracteres)")
    except requests.RequestException as e:
        print(f"ERRO ao consultar: {e}")


def passo_2_listar_partidas_do_torneio(tournament_no: int) -> None:
    """Lista as partidas de um torneio especifico (pegue o 'No' do passo 1)."""
    print(f"\n{'='*70}")
    print(f"PASSO 2: Listando partidas do torneio No={tournament_no}")
    print(f"{'='*70}\n")

    request_xml = (
        f"<Request Type='GetVolleyMatchList' "
        f"Fields='No NoInTournament DateTimeLocal TeamAName TeamBName "
        f"MatchPointsA MatchPointsB PoolName'>"
        f"<Filter NoTournament='{tournament_no}'/>"
        f"</Request>"
    )

    try:
        raw = fetch(request_xml)
        print(raw[:4000])
        if len(raw) > 4000:
            print(f"\n... (resposta truncada, total de {len(raw)} caracteres)")
    except requests.RequestException as e:
        print(f"ERRO ao consultar: {e}")


if __name__ == "__main__":
    # Ja confirmamos que o torneio No=382 e o Campeonato NORCECA 2013.
    # Vamos buscar as partidas dele agora.
    passo_2_listar_partidas_do_torneio(382)
