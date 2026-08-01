"""
vis_converter.py

Converte dados brutos da API FIVB VIS (XML) para objetos Match, que e o
formato que o elo_engine.py espera.

Duas responsabilidades principais que a fonte de dados NAO resolve sozinha:

1. Nomes de selecao -> codigo de 3 letras
   O VIS devolve nomes completos em ingles ("USA", "Puerto RIco" -- com erro
   de digitacao real da propria base da FIVB), enquanto o motor de Elo usa
   codigos ("USA", "PUR"). Times nao mapeados NAO sao descartados
   silenciosamente -- caem numa lista de pendencias pra voce revisar.

2. Deteccao de "final" (pra excluir da contagem do fator K)
   O campo PoolName as vezes traz "Finals", mas tambem "Quartefinals"
   (erro de digitacao da FIVB) e "Semifinals" -- que CONTEM a palavra
   "final" mas NAO sao a final. Por isso a comparacao e exata, nao "contem".
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, date
from dataclasses import dataclass, field

from elo_engine import Match


# ---------------------------------------------------------------------------
# Mapeamento nome (como vem do VIS) -> codigo de 3 letras
#
# IMPORTANTE: esta tabela esta longe de completa -- cobre os paises que
# ja apareceram nos testes ate agora, mais os tiers do modelo original.
# E para crescer aos poucos, conforme formos processando mais torneios.
# Chaves em minusculo (a normalizacao cuida do resto).
# ---------------------------------------------------------------------------

COUNTRY_NAME_TO_CODE: dict[str, str] = {
    # Tiers originais do modelo (2800/2700/2600/2500)
    "brazil": "BRA", "italy": "ITA", "russia": "RUS", "serbia": "SRB",
    "argentina": "ARG", "cuba": "CUB", "france": "FRA", "greece": "GRE",
    "netherlands": "NED", "usa": "USA", "united states": "USA",
    "bulgaria": "BUL", "canada": "CAN", "china": "CHN", "czech republic": "CZE",
    "spain": "ESP", "germany": "GER", "japan": "JPN", "south korea": "KOR",
    "korea": "KOR", "poland": "POL", "portugal": "POR",
    "australia": "AUS", "belgium": "BEL", "croatia": "CRO", "egypt": "EGY",
    "finland": "FIN", "hungary": "HUN", "slovenia": "SLO", "slovakia": "SVK",
    "tunisia": "TUN", "turkey": "TUR", "ukraine": "UKR", "venezuela": "VEN",

    # NORCECA / Caribe (apareceram no teste real do torneio 382)
    "dominican republic": "DOM", "puerto rico": "PUR", "puerto rIco": "PUR",
    "mexico": "MEX", "guatemala": "GUA", "bahamas": "BAH",
    "saint lucia": "LCA", "trinidad and tobago": "TTO",

    # Outros paises comuns em torneios continentais (para ir cobrindo aos poucos)
    "iran": "IRI", "india": "IND", "kazakhstan": "KAZ", "thailand": "THA",
    "indonesia": "INA", "chinese taipei": "TPE", "vietnam": "VIE",
    "algeria": "ALG", "cameroon": "CMR", "morocco": "MAR", "libya": "LBA",
    "colombia": "COL", "chile": "CHI", "peru": "PER", "uruguay": "URU",
    "denmark": "DEN", "sweden": "SWE", "great britain": "GBR",
    "israel": "ISR", "romania": "ROU", "estonia": "EST", "belarus": "BLR",

    # Adicionados apos o relatorio do orquestrador multi-ano (2013-2026) --
    # maioria ja tinha rating de 2011 no seed, so faltava aqui a traducao
    # do nome em ingles vindo do VIS/Wikipedia para o codigo.
    "afghanistan": "AFG", "albania": "ALB", "austria": "AUT", "azerbaijan": "AZE",
    "bahrain": "BRN", "bangladesh": "BAN", "belize": "BIZ", "bolivia": "BOL",
    "bosnia and herzegovina": "BIH", "botswana": "BOT", "costa rica": "CRC",
    "dr congo": "COD", "ecuador": "ECU", "georgia": "GEO", "ghana": "GHA",
    "honduras": "HON", "hong kong": "HKG", "iceland": "ISL", "kenya": "KEN",
    "kuwait": "KUW", "latvia": "LAT", "lebanon": "LBN", "luxembourg": "LUX",
    "mauritius": "MRI", "montenegro": "MNE", "myanmar": "MYA", "nicaragua": "NCA",
    "nigeria": "NGR", "north macedonia": "MKD", "norway": "NOR", "oman": "OMA",
    "pakistan": "PAK", "paraguay": "PAR", "qatar": "QAT", "rwanda": "RWA",
    "saint vincent and the grenadines": "VIN", "saudi arabia": "KSA",
    "sri lanka": "SRI", "suriname": "SUR", "turkmenistan": "TKM",
    "türkiye": "TUR", "turkiye": "TUR", "united arab emirates": "UAE",
    "uzbekistan": "UZB",

    # Paises genuinamente novos -- NAO estavam no seu seed de 2011 (o
    # documento original nao os incluia). Vao receber o rating padrao
    # por tier (2400) na primeira partida, ja que nao ha historico anterior.
    "burundi": "BDI", "chad": "CHA", "congo": "CGO", "guyana": "GUY",
    "iraq": "IRQ", "kosovo": "KOS", "martinique": "MTQ", "niger": "NIG",
    "switzerland": "SUI", "gambia": "GAM", "mali": "MLI", "senegal": "SEN",
    "tanzania": "TAN",
}


@dataclass
class ConversionLog:
    """Acumula pendencias durante a conversao, para revisao manual --
    nunca descartamos dado silenciosamente."""
    unmapped_teams: set[str] = field(default_factory=set)
    skipped_matches: list[str] = field(default_factory=list)


def normalize_and_map_team(raw_name: str, log: ConversionLog) -> str | None:
    """Tenta mapear um nome de selecao (como vem do VIS) para um codigo
    de 3 letras. Se nao encontrar, registra no log e devolve None --
    quem chama decide o que fazer (normalmente: pular a partida).

    Remove marcacoes de nota de rodape que a Wikipedia as vezes gruda no
    nome do time (ex: 'Morocco[a]', 'Kenya[1]') antes de tentar mapear --
    sem isso, cada variacao de nota de rodape viraria um "pais" diferente
    e nao mapeado."""
    cleaned = re.sub(r"\[.*?\]\s*$", "", raw_name).strip()
    key = cleaned.lower()
    code = COUNTRY_NAME_TO_CODE.get(key)
    if code is None:
        log.unmapped_teams.add(cleaned)
        return None
    return code


# Nomes de fase que efetivamente SAO a final (comparacao exata, nao "contem",
# para nao confundir com "Quartefinals"/"Semifinals").
FINAL_POOL_NAMES = {"final", "finals"}


def is_final_pool(pool_name: str) -> bool:
    return pool_name.strip().lower() in FINAL_POOL_NAMES


def parse_vis_datetime(raw: str) -> date:
    """Converte 'DateTimeLocal' (ex: '2013-09-23T16:00:00') para date."""
    return datetime.fromisoformat(raw).date()


def convert_vis_matches_xml(
    xml_text: str,
    season: int,
    event_name: str,
    log: ConversionLog | None = None,
) -> list[Match]:
    """Converte a resposta XML de GetVolleyMatchList numa lista de Match.

    Partidas com time nao mapeado sao PULADAS (nao inventamos codigo) e
    registradas em log.skipped_matches para voce revisar e completar o
    COUNTRY_NAME_TO_CODE.
    """
    if log is None:
        log = ConversionLog()

    root = ET.fromstring(xml_text)
    matches: list[Match] = []

    for elem in root.findall("VolleyballMatch"):
        raw_a = elem.get("TeamAName", "")
        raw_b = elem.get("TeamBName", "")
        raw_date = elem.get("DateTimeLocal")
        pts_a = elem.get("MatchPointsA")
        pts_b = elem.get("MatchPointsB")
        pool_name = elem.get("PoolName", "") or ""
        match_no = elem.get("No", "?")

        # Pendencias que impedem conversao desta partida especifica.
        if not raw_date:
            log.skipped_matches.append(f"No={match_no}: sem DateTimeLocal")
            continue
        if pts_a is None or pts_b is None or not str(pts_a).strip().isdigit() or not str(pts_b).strip().isdigit():
            log.skipped_matches.append(f"No={match_no}: sem placar valido ('{pts_a}' x '{pts_b}')")
            continue

        code_a = normalize_and_map_team(raw_a, log)
        code_b = normalize_and_map_team(raw_b, log)
        if code_a is None or code_b is None:
            log.skipped_matches.append(
                f"No={match_no}: time nao mapeado ('{raw_a}' vs '{raw_b}')"
            )
            continue

        sets_a, sets_b = int(pts_a), int(pts_b)
        if sets_a == sets_b:
            # Nao deveria acontecer no volei, mas se acontecer (dado sujo),
            # pulamos em vez de deixar o motor quebrar.
            log.skipped_matches.append(
                f"No={match_no}: placar empatado ({sets_a}x{sets_b}), pulado"
            )
            continue

        matches.append(Match(
            match_date=parse_vis_datetime(raw_date),
            season=season,
            team_a=code_a,
            team_b=code_b,
            sets_a=sets_a,
            sets_b=sets_b,
            event=event_name,
            is_final=is_final_pool(pool_name),
        ))

    return matches


if __name__ == "__main__":
    # Teste rapido com os dados REAIS trazidos do torneio No=382
    # (NORCECA's Men's Continental Championship, 2013).
    amostra_xml = """<VolleyballMatches NbItems="18" Version="56767896">
<VolleyballMatch No="4944" DateTimeLocal="2013-09-23T16:00:00" TeamAName="USA" TeamBName="Saint Lucia" MatchPointsA="3" MatchPointsB="0" PoolName="Pool A"/>
<VolleyballMatch No="4953" DateTimeLocal="2013-09-26T16:00:00" TeamAName="Guatemala" TeamBName="Bahamas" MatchPointsA="0" MatchPointsB="3" PoolName="Quartefinals"/>
<VolleyballMatch No="4957" DateTimeLocal="2013-09-27T18:00:00" TeamAName="USA" TeamBName="Puerto RIco" MatchPointsA="3" MatchPointsB="1" PoolName="Finals"/>
<VolleyballMatch No="4958" DateTimeLocal="2013-09-27T20:30:00" TeamAName="Canada" TeamBName="Cuba" MatchPointsA="3" MatchPointsB="0" PoolName="Finals"/>
<VolleyballMatch No="9999" DateTimeLocal="2013-09-28T16:00:00" TeamAName="Aruba" TeamBName="USA" MatchPointsA="3" MatchPointsB="0" PoolName=""/>
</VolleyballMatches>"""

    log = ConversionLog()
    matches = convert_vis_matches_xml(
        amostra_xml, season=2013, event_name="Campeonato NORCECA 2013", log=log
    )

    print(f"Partidas convertidas com sucesso: {len(matches)}\n")
    for m in matches:
        print(f"  {m.match_date} | {m.team_a} {m.sets_a}x{m.sets_b} {m.team_b} "
              f"| final={m.is_final} | pool_era='{'Finals' if m.is_final else '(nao-final)'}'")

    print(f"\nTimes nao mapeados (precisam entrar em COUNTRY_NAME_TO_CODE): "
          f"{log.unmapped_teams or 'nenhum'}")
    print(f"\nPartidas puladas:")
    for s in log.skipped_matches:
        print(f"  - {s}")
