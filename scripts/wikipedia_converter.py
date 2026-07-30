"""
wikipedia_converter.py

Converte a tabela de resultados de uma pagina de torneio da Wikipedia
(extraida via pandas.read_html) para objetos Match.

Reusa a mesma tabela de mapeamento de nomes de selecao (COUNTRY_NAME_TO_CODE)
do vis_converter.py -- e o MESMO problema (nomes em texto -> codigo de 3
letras), entao faz sentido ser a mesma fonte de verdade, para nao divergir.
"""

from __future__ import annotations

import re
from datetime import date, datetime

import pandas as pd

from elo_engine import Match
from vis_converter import COUNTRY_NAME_TO_CODE, ConversionLog, normalize_and_map_team


def find_match_table(tables: list[pd.DataFrame]) -> pd.DataFrame | None:
    """Identifica, entre todas as tabelas de uma pagina, qual e a de
    resultados de partidas -- heuristica: tem colunas 'Score' e 'Set 1'."""
    for tabela in tables:
        cols = [str(c) for c in tabela.columns]
        if "Score" in cols and "Set 1" in cols:
            return tabela
    return None


# Aceita en-dash (–, usado pela Wikipedia), hifen normal (-) e til (~) por seguranca.
SCORE_PATTERN = re.compile(r"^\s*(\d+)\s*[-–—]\s*(\d+)\s*$")


def parse_score(raw: str) -> tuple[int, int] | None:
    if not isinstance(raw, str):
        return None
    m = SCORE_PATTERN.match(raw)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def parse_wiki_date(raw: str, season: int) -> date | None:
    """Datas na Wikipedia costumam vir sem ano (ex: '22 Sep'), porque o
    ano esta implicito no titulo da pagina/torneio. Usamos `season` para
    completar. Formato tolerante a 'Sep'/'September' etc via %b."""
    if not isinstance(raw, str):
        return None
    raw = raw.strip()
    for fmt in ("%d %b", "%d %B"):
        try:
            parsed = datetime.strptime(f"{raw} {season}", f"{fmt} %Y")
            return parsed.date()
        except ValueError:
            continue
    return None


def convert_wikipedia_table_to_matches(
    table: pd.DataFrame,
    season: int,
    event_name: str,
    log: ConversionLog | None = None,
) -> list[Match]:
    if log is None:
        log = ConversionLog()

    cols = list(table.columns)
    score_idx = cols.index("Score")
    team_a_col = cols[score_idx - 1]
    team_b_col = cols[score_idx + 1]

    matches: list[Match] = []

    for row_idx, row in table.iterrows():
        raw_date = row.get("Date")
        raw_score = row.get("Score")
        raw_a = row.get(team_a_col)
        raw_b = row.get(team_b_col)

        match_date = parse_wiki_date(raw_date, season)
        if match_date is None:
            log.skipped_matches.append(f"linha {row_idx}: data invalida ('{raw_date}')")
            continue

        score = parse_score(raw_score)
        if score is None:
            log.skipped_matches.append(f"linha {row_idx}: placar invalido ('{raw_score}')")
            continue
        sets_a, sets_b = score
        if sets_a == sets_b:
            log.skipped_matches.append(f"linha {row_idx}: placar empatado, pulado")
            continue

        code_a = normalize_and_map_team(str(raw_a), log)
        code_b = normalize_and_map_team(str(raw_b), log)
        if code_a is None or code_b is None:
            log.skipped_matches.append(
                f"linha {row_idx}: time nao mapeado ('{raw_a}' vs '{raw_b}')"
            )
            continue

        matches.append(Match(
            match_date=match_date, season=season, team_a=code_a, team_b=code_b,
            sets_a=sets_a, sets_b=sets_b, event=event_name,
            is_final=False,  # Wikipedia nem sempre marca fase -- ver nota no README
        ))

    return matches


if __name__ == "__main__":
    # Teste com os dados REAIS que o Daniel trouxe (Campeonato Africano 2013)
    data = {
        "Date": ["22 Sep", "22 Sep", "22 Sep"],
        "Time": ["14:00", "16:00", "18:00"],
        "Unnamed: 2": ["Egypt", "Algeria", "Tunisia"],
        "Score": ["3–0", "2–3", "3–0"],
        "Unnamed: 4": ["Cameroon", "Morocco", "Libya"],
        "Set 1": ["25–17", "25–21", "25–14"],
        "Set 2": ["25–21", "20–25", "25–19"],
        "Set 3": ["25–23", "25–22", "25–16"],
        "Set 4": [None, "18–25", None],
        "Set 5": [None, "13–15", None],
        "Total": ["75–61", "101–108", "75–49"],
        "Report": [None, None, None],
    }
    df = pd.DataFrame(data)

    log = ConversionLog()
    matches = convert_wikipedia_table_to_matches(
        df, season=2013, event_name="Campeonato Africano 2013", log=log
    )

    print(f"Partidas convertidas: {len(matches)}\n")
    for m in matches:
        print(f"  {m.match_date} | {m.team_a} {m.sets_a}x{m.sets_b} {m.team_b}")

    print(f"\nTimes nao mapeados: {log.unmapped_teams or 'nenhum'}")
    print(f"Partidas puladas: {log.skipped_matches or 'nenhuma'}")
