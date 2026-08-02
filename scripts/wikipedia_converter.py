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
from bs4 import BeautifulSoup
from io import StringIO

from elo_engine import Match
from vis_converter import COUNTRY_NAME_TO_CODE, ConversionLog, normalize_and_map_team, is_final_pool


def find_match_tables(tables: list[pd.DataFrame]) -> list[pd.DataFrame]:
    """Identifica TODAS as tabelas de resultados de partidas numa pagina --
    heuristica: tem colunas 'Score' e 'Set 1'. Torneios com fase de grupos
    costumam ter uma tabela de partidas POR GRUPO, entao pegar so a
    primeira perderia a maioria dos jogos silenciosamente."""
    return [t for t in tables
            if "Score" in [str(c) for c in t.columns] and "Set 1" in [str(c) for c in t.columns]]


# Marcadores de nota de rodape/edicao que a Wikipedia as vezes deixa
# junto do texto do cabecalho (ex: 'Pool A[edit]').
_HEADING_CLEANUP = re.compile(r"\[.*?\]")


def _is_match_table_html(table_tag) -> bool:
    """Mesma heuristica de find_match_tables, mas direto na tag do BeautifulSoup
    (sem precisar re-parsear com pandas so pra checar as colunas)."""
    header_cells = [th.get_text(strip=True) for th in table_tag.find_all("th")]
    return "Score" in header_cells and "Set 1" in header_cells


def _nearest_preceding_heading(table_tag) -> str:
    """Sobe pelos irmaos anteriores (e, se preciso, pelos pais) ate achar
    o cabecalho (h2/h3/h4) mais proximo antes da tabela -- essa e a "fase"
    da tabela (ex: 'Pool A', 'Semifinals'). Se nao achar nada, devolve
    string vazia (quem chama decide o rotulo generico)."""
    node = table_tag
    while node is not None:
        sibling = node.find_previous_sibling()
        while sibling is not None:
            if sibling.name in ("h2", "h3", "h4", "h5"):
                texto = sibling.get_text(strip=True)
                return _HEADING_CLEANUP.sub("", texto).strip()
            sibling = sibling.find_previous_sibling()
        node = node.parent
    return ""


def find_match_tables_with_phases(html: str) -> list[tuple[str, pd.DataFrame]]:
    """Versao com rotulo de fase: devolve lista de (fase, tabela) para
    cada tabela de resultados de partidas na pagina. A fase e o texto do
    cabecalho (h2/h3/h4) mais proximo ANTES da tabela na pagina."""
    soup = BeautifulSoup(html, "html.parser")
    resultado = []
    for table_tag in soup.find_all("table"):
        if not _is_match_table_html(table_tag):
            continue
        fase = _nearest_preceding_heading(table_tag)
        try:
            dfs = pd.read_html(StringIO(str(table_tag)))
        except Exception:
            continue
        if dfs:
            resultado.append((fase, dfs[0]))
    return resultado


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
    completar. Formato tolerante a 'Sep'/'September' etc via %b.
    Tambem remove marcacoes de nota de rodape (ex: '11 Jun*') pelo mesmo
    motivo que fazemos com nomes de time."""
    if not isinstance(raw, str):
        return None
    raw = raw.strip().rstrip("*").strip()
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
    fase: str = "",
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
        if max(sets_a, sets_b) != 3:
            log.skipped_matches.append(
                f"linha {row_idx}: partida em andamento ou placar incompleto ({sets_a}x{sets_b})"
            )
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
            is_final=is_final_pool(fase),
            fase=fase,
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
