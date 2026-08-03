"""
build_site.py

Gera o site completo, com varias paginas:
  docs/index.html               -> ranking atual de todas as selecoes
  docs/anos/{ano}.html          -> todos os resultados daquele ano
  docs/selecoes/{codigo}.html   -> historico completo de uma selecao (desde 2013)

Uso:
    python build_site.py
"""

from __future__ import annotations

import csv
import os
import re
from collections import defaultdict
from datetime import datetime

PARTIDAS_CSV = "../data/partidas.csv"
HISTORICO_CSV = "../data/historico_ratings.csv"
RATINGS_ATUAIS_CSV = "../data/ratings_atuais.csv"
NOMES_CSV = "../data/nomes_paises.csv"
SEED_CSV = "../data/seed_ratings_2011.csv"
DOCS_DIR = "../docs"
BASE_URL = "https://dmmarcolino.github.io/volei-elo-rating/"

MESES_PT = {
    1: "jan", 2: "fev", 3: "mar", 4: "abr", 5: "mai", 6: "jun",
    7: "jul", 8: "ago", 9: "set", 10: "out", 11: "nov", 12: "dez",
}


def load_partidas(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_rating_deltas(path: str) -> dict[tuple, tuple[float, float]]:
    index = {}
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key = (row["match_date"], row["event"], row["team"], row["opponent"])
            index[key] = (float(row["rating_before"]), float(row["rating_after"]))
    return index


def load_ratings_atuais(path: str) -> dict[str, float]:
    with open(path, encoding="utf-8") as f:
        return {row["codigo"]: float(row["rating_atual"]) for row in csv.DictReader(f)}


def load_nomes(path: str) -> dict[str, str]:
    with open(path, encoding="utf-8") as f:
        return {row["codigo"]: row["nome_pt"] for row in csv.DictReader(f)}


def format_date_pt(iso_date: str) -> str:
    d = datetime.strptime(iso_date, "%Y-%m-%d").date()
    return f"{d.day:02d} {MESES_PT[d.month]} {d.year}"


def format_date_curta_pt(iso_date: str) -> str:
    d = datetime.strptime(iso_date, "%Y-%m-%d").date()
    return f"{d.day:02d} {MESES_PT[d.month]}"


def delta_html(delta: float) -> str:
    sign = "+" if delta >= 0 else ""
    cls = "delta-pos" if delta >= 0 else "delta-neg"
    arrow = "&#9650;" if delta >= 0 else "&#9660;"
    return f'<span class="delta {cls}">{arrow} {sign}{delta:.1f}</span>'


def nome_completo(codigo: str, nomes: dict[str, str]) -> str:
    return nomes.get(codigo, codigo)


def build_nav(prefixo: str, anos: list[int]) -> str:
    links_anos = "".join(f'<a href="{prefixo}anos/{ano}.html">{ano}</a>' for ano in anos)
    return f"""<nav>
      <a href="{prefixo}index.html" class="nav-home">Elo Vôlei</a>
      <div class="nav-anos">{links_anos}</div>
    </nav>"""


def load_historico_rows(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_seed_ratings(path: str) -> dict[str, float]:
    with open(path, encoding="utf-8") as f:
        return {row["codigo"]: float(row["rating_2011"]) for row in csv.DictReader(f)}


# Confederacao dos 9 paises que entraram depois do seed original de 2011
# (nao tinham rating em 2011, entao nao aparecem no seed_ratings_2011.csv).
CONFEDERACAO_EXTRA = {
    "BDI": "Africa", "CHA": "Africa", "CGO": "Africa", "NIG": "Africa",
    "TAN": "Africa", "GAM": "Africa", "MLI": "Africa",
    "GUY": "America", "MTQ": "America",
    "IRQ": "Asia",
    "KOS": "Europa", "SUI": "Europa",
}


def load_confederacoes(seed_path: str) -> dict[str, str]:
    confederacoes = dict(CONFEDERACAO_EXTRA)
    with open(seed_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            confederacoes[row["codigo"]] = row["confederacao"]
    return confederacoes


def compute_ranking_at(historico_rows: list[dict], seed_ratings: dict[str, float],
                        cutoff_date: str) -> list[tuple[str, float]]:
    """Reconstroi o ranking como estava no fim de um ano especifico,
    percorrendo o historico cronologico (ja vem ordenado por data)."""
    atual = dict(seed_ratings)
    for row in historico_rows:
        if row["match_date"] > cutoff_date:
            break
        atual[row["team"]] = float(row["rating_after"])
    return sorted(atual.items(), key=lambda kv: kv[1], reverse=True)


def build_ranking_ano_html(ano: int, ranking: list[tuple[str, float]],
                            nomes: dict[str, str], anos: list[int]) -> str:
    linhas = []
    for pos, (codigo, rating) in enumerate(ranking, start=1):
        linhas.append(f"""
        <a class="rank-row" href="../selecoes/{codigo}.html">
          <span class="rank-pos">{pos}</span>
          <span class="rank-nome">{nome_completo(codigo, nomes)}</span>
          <span class="rank-codigo">{codigo}</span>
          <span class="rank-rating">{rating:.0f}</span>
        </a>""")

    return PAGE_TEMPLATE.format(
        titulo=f"Ranking Final {ano}",
        descricao=f"Como terminou o ranking Elo de todas as seleções masculinas de vôlei "
                   f"no fim de {ano}, do 1º ao último colocado.",
        url_completa=f"{BASE_URL}rankings/{ano}.html",
        nav=build_nav("../", anos),
        conteudo=f"""
        <div class="page-header-row">
          <h1>Ranking Final {ano}</h1>
          <a class="page-header-link" href="../anos/{ano}.html">Resultados {ano}</a>
        </div>
        <div class="ranking">{''.join(linhas)}</div>""",
        css_prefix="../",
    )


def build_continentes_html(ratings_atuais: dict[str, float], confederacoes: dict[str, str],
                            nomes: dict[str, str], anos: list[int]) -> str:
    por_confederacao: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for codigo, rating in ratings_atuais.items():
        confederacao = confederacoes.get(codigo, "Outros")
        por_confederacao[confederacao].append((codigo, rating))

    NOMES_CONFEDERACAO = {
        "Africa": "África", "Asia": "Ásia", "America": "América", "Europa": "Europa",
    }

    secoes = []
    for confederacao in sorted(por_confederacao.keys()):
        ranking = sorted(por_confederacao[confederacao], key=lambda kv: kv[1], reverse=True)
        linhas = []
        for pos, (codigo, rating) in enumerate(ranking, start=1):
            linhas.append(f"""
            <a class="rank-row" href="selecoes/{codigo}.html">
              <span class="rank-pos">{pos}</span>
              <span class="rank-nome">{nome_completo(codigo, nomes)}</span>
              <span class="rank-codigo">{codigo}</span>
              <span class="rank-rating">{rating:.0f}</span>
            </a>""")
        titulo = NOMES_CONFEDERACAO.get(confederacao, confederacao)
        secoes.append(f"""
        <section class="tournament">
          <h2>{titulo}</h2>
          <div class="ranking">{''.join(linhas)}</div>
        </section>""")

    return PAGE_TEMPLATE.format(
        titulo="Ranking por continente",
        descricao="Ranking Elo atual das seleções masculinas de vôlei, organizado "
                   "por confederação: África, Ásia, América e Europa.",
        url_completa=f"{BASE_URL}continentes.html",
        nav=build_nav("", anos),
        conteudo=f"<h1>Ranking por continente</h1>{''.join(secoes)}",
        css_prefix="",
    )


def build_index_html(ratings_atuais: dict[str, float], nomes: dict[str, str], anos: list[int],
                      ultima_atualizacao: str) -> str:
    ranking = sorted(ratings_atuais.items(), key=lambda kv: kv[1], reverse=True)
    linhas = []
    for pos, (codigo, rating) in enumerate(ranking, start=1):
        linhas.append(f"""
        <a class="rank-row" href="selecoes/{codigo}.html">
          <span class="rank-pos">{pos}</span>
          <span class="rank-nome">{nome_completo(codigo, nomes)}</span>
          <span class="rank-codigo">{codigo}</span>
          <span class="rank-rating">{rating:.0f}</span>
        </a>""")

    return PAGE_TEMPLATE.format(
        titulo="Ranking atual",
        descricao="Ranking Elo das seleções masculinas de vôlei, com histórico de "
                   "resultados internacionais desde 2013 e evolução do rating de cada país.",
        url_completa=BASE_URL,
        nav=build_nav("", anos),
        conteudo=f"""
        <section>
          <div class="page-header-row">
            <h1>Ranking atual</h1>
            <a class="page-header-link" href="continentes.html">Ranking por continente</a>
          </div>
          <p class="subtitulo">Clique numa seleção para ver o histórico completo desde 2013</p>
          <p class="ultima-atualizacao">Última atualização: {ultima_atualizacao}</p>
          <div class="ranking">{''.join(linhas)}</div>
        </section>""",
        css_prefix="",
    )


# Fases de mata-mata conhecidas -- NUNCA mostram tabela de classificacao,
# so a(s) partida(s) em si. A ordem no dicionario e a ordem de exibicao.
# Fases de mata-mata: classificacao unificada. Antes disso usava um
# dicionario de substrings simples, mas isso quebrava com variacoes de
# espaco (ex: "Quarter Final" com espaco nao batia com "quarterfinal"
# junto, e "final" sozinho capturava tudo por engano, incluindo quartas
# e semifinais). Agora cada categoria e checada de forma tolerante a
# espaco/hifen, e fases de "colocacao" (7th place, Final 1-2 etc.) tem
# o numero da colocacao extraido para ordenar corretamente.
def classify_fase(fase: str) -> tuple[str, int]:
    """Devolve (categoria, rank). categoria e uma de:
    'grupo', 'r16', 'quartas', 'semi', 'final', 'desconhecida'.
    rank so importa pra 'final': 1 = disputa do 1o lugar (mostrada por
    ultimo), 3 = disputa do 3o lugar, etc."""
    f = fase.lower().strip()

    if "round of 16" in f or "oitavas" in f or "1/8" in f:
        return ("r16", 0)
    if "quarter" in f and "final" in f or "quartas" in f or "1/4" in f:
        return ("quartas", 0)
    if ("semi" in f and "final" in f) or "semifinais" in f or "1/2" in f:
        return ("semi", 0)

    # Fases de "colocacao"/final -- tenta extrair o numero.
    m = re.search(r"(\d+)\s*[-–]\s*(\d+)", f)  # ex: "Final 1-2", "Places 5-6"
    if m:
        return ("final", min(int(m.group(1)), int(m.group(2))))
    m = re.search(r"(\d+)(?:st|nd|rd|th)\s*place", f)  # ex: "7th place"
    if m:
        return ("final", int(m.group(1)))
    if "bronze" in f or "third place" in f or "3rd place" in f or "terceiro lugar" in f:
        return ("final", 3)
    if "final" in f:
        return ("final", 1)

    if "pool" in f or "group" in f or "grupo" in f:
        return ("grupo", 0)
    return ("desconhecida", 0)


_ORDEM_CATEGORIA = {"grupo": 0, "desconhecida": 1, "r16": 2, "quartas": 3, "semi": 4, "final": 5}


def is_fase_mata_mata(fase: str) -> bool:
    categoria, _ = classify_fase(fase)
    return categoria in ("r16", "quartas", "semi", "final")


def fase_sort_key(fase: str):
    """Ordena: grupos (alfabetico/numerico) -> desconhecidas -> R16 ->
    quartas -> semis -> finais (da colocacao mais alta/menos importante
    ate a final que disputa o 1o lugar, que fica sempre por ultimo)."""
    categoria, rank = classify_fase(fase)
    ordem = _ORDEM_CATEGORIA[categoria]
    if categoria == "grupo":
        m = re.search(r"(\d+)", fase)
        return (ordem, int(m.group(1)) if m else 0, fase)
    if categoria == "final":
        return (ordem, -rank, fase)  # rank maior (7-8) primeiro, rank 1 (final) por ultimo
    return (ordem, 0, fase)


# Eventos onde a classificacao POR POOL nao importa de verdade -- so a
# classificacao geral combinando todos os pools. Ex: Nations League, onde
# os grupos so servem pra organizar o calendario, nao pra classificar.
EVENTOS_SO_CLASSIFICACAO_GERAL = ("nations league", "liga mundial", "world league")


def grupo_e_consistente(partidas_da_fase: list[dict]) -> bool:
    """Verifica se todas as selecoes da fase jogaram o MESMO numero de
    partidas -- sinal de um grupo/turno unico limpo. Se nao bater, e sinal
    de que duas fases distintas foram misturadas sob o mesmo rotulo (ex:
    fase de grupos + Final Four juntas) -- nesse caso e mais seguro NAO
    mostrar tabela do que mostrar uma classificacao enganosa."""
    contagem: dict[str, int] = defaultdict(int)
    for p in partidas_da_fase:
        contagem[p["team_a"]] += 1
        contagem[p["team_b"]] += 1
    return len(set(contagem.values())) <= 1


def compute_standings(partidas_da_fase: list[dict]) -> list[dict]:
    """Calcula vitorias, sets pro/contra e set average para cada selecao
    dentro de uma fase. So faz sentido chamar isso para fases com mais de
    2 selecoes (grupo/turno unico) -- uma fase de 2 times e so uma
    partida de mata-mata, sem necessidade de tabela."""
    stats: dict[str, dict] = {}
    for p in partidas_da_fase:
        sets_a, sets_b = int(p["sets_a"]), int(p["sets_b"])
        for team, sfor, sagainst in ((p["team_a"], sets_a, sets_b), (p["team_b"], sets_b, sets_a)):
            s = stats.setdefault(team, {"vitorias": 0, "derrotas": 0, "sets_pro": 0, "sets_contra": 0})
            s["sets_pro"] += sfor
            s["sets_contra"] += sagainst
            s["vitorias" if sfor > sagainst else "derrotas"] += 1
    linhas = []
    for team, s in stats.items():
        set_avg = s["sets_pro"] / s["sets_contra"] if s["sets_contra"] > 0 else float(s["sets_pro"])
        linhas.append({"codigo": team, "set_avg": set_avg, **s})
    linhas.sort(key=lambda l: (-l["vitorias"], -l["set_avg"]))
    return linhas


def build_standings_html(standings: list[dict], nomes: dict[str, str]) -> str:
    linhas = []
    for pos, s in enumerate(standings, start=1):
        linhas.append(f"""
        <div class="standings-row">
          <span class="standings-pos">{pos}</span>
          <a class="standings-nome" href="../selecoes/{s['codigo']}.html">{nome_completo(s['codigo'], nomes)}</a>
          <span class="standings-v">{s['vitorias']}V</span>
          <span class="standings-d">{s['derrotas']}D</span>
          <span class="standings-avg">{s['sets_pro']}-{s['sets_contra']} ({s['set_avg']:.2f})</span>
        </div>""")
    return f'<div class="standings">{"".join(linhas)}</div>'


def build_match_row_html(p: dict, evento: str, rating_index: dict,
                          nomes: dict[str, str], ratings_atuais: dict[str, float]) -> str:
    key_a = (p["match_date"], evento, p["team_a"], p["team_b"])
    key_b = (p["match_date"], evento, p["team_b"], p["team_a"])
    rating_a = rating_index.get(key_a)
    rating_b = rating_index.get(key_b)
    delta_a = delta_html(rating_a[1] - rating_a[0]) if rating_a else ""
    delta_b = delta_html(rating_b[1] - rating_b[0]) if rating_b else ""
    # Rating de CADA SELECAO NO MOMENTO DA PARTIDA (antes dela acontecer),
    # nao o rating atual -- senao um jogo de 2013 mostraria o rating de
    # 2026, o que nao faz sentido nenhum.
    rating_a_str = f'<span class="team-rating">{rating_a[0]:.0f}</span>' if rating_a else ""
    rating_b_str = f'<span class="team-rating">{rating_b[0]:.0f}</span>' if rating_b else ""

    return f"""
    <div class="match-row">
      <div class="match-date">{format_date_curta_pt(p['match_date'])}</div>
      {delta_a}
      <a class="match-team team-a" href="../selecoes/{p['team_a']}.html">
        <span class="team-nome">{nome_completo(p['team_a'], nomes)}</span>
        {rating_a_str}
      </a>
      <div class="scoreboard">{p['sets_a']}&ndash;{p['sets_b']}</div>
      <a class="match-team team-b" href="../selecoes/{p['team_b']}.html">
        {rating_b_str}
        <span class="team-nome">{nome_completo(p['team_b'], nomes)}</span>
      </a>
      {delta_b}
    </div>"""


def build_ano_html(ano: int, partidas_do_ano: list[dict], rating_index: dict,
                    nomes: dict[str, str], ratings_atuais: dict[str, float], anos: list[int]) -> str:
    eventos: dict[str, list[dict]] = defaultdict(list)
    ordem_eventos: list[str] = []
    for p in partidas_do_ano:
        evento = p["event"]
        if evento not in eventos:
            ordem_eventos.append(evento)
        eventos[evento].append(p)

    secoes_html = []
    for evento in ordem_eventos:
        # Agrupa por fase.
        fases: dict[str, list[dict]] = defaultdict(list)
        for p in eventos[evento]:
            fase = p.get("fase") or "Resultados"
            fases[fase].append(p)

        # Ordena as fases: grupos em ordem alfabetica/numerica, depois
        # mata-mata na ordem logica correta (nao alfabetica).
        ordem_fases = sorted(fases.keys(), key=fase_sort_key)

        e_evento_so_classificacao_geral = any(
            chave in evento.lower() for chave in EVENTOS_SO_CLASSIFICACAO_GERAL
        )

        # Primeira passada: junta as partidas de todas as fases de grupo
        # (nao mata-mata) para calcular a classificacao geral, se for o caso.
        partidas_fase_de_grupo: list[dict] = [
            p for fase in ordem_fases if not is_fase_mata_mata(fase) for p in fases[fase]
        ]
        classificacao_geral_html = ""
        if e_evento_so_classificacao_geral and partidas_fase_de_grupo and grupo_e_consistente(partidas_fase_de_grupo):
            standings_geral = compute_standings(partidas_fase_de_grupo)
            classificacao_geral_html = f"""
            <div class="fase-bloco">
              <h3 class="fase-titulo">Classificação Geral</h3>
              {build_standings_html(standings_geral, nomes)}
            </div>"""

        # Segunda passada: monta os blocos na ordem, inserindo a
        # classificacao geral logo APOS a ultima fase de grupo e ANTES da
        # primeira fase de mata-mata (nao no fim de tudo).
        blocos_fase = []
        geral_ja_inserida = False
        for fase in ordem_fases:
            partidas_fase = fases[fase]
            times_da_fase = {p["team_a"] for p in partidas_fase} | {p["team_b"] for p in partidas_fase}
            eh_mata_mata = is_fase_mata_mata(fase)

            if eh_mata_mata and classificacao_geral_html and not geral_ja_inserida:
                blocos_fase.append(classificacao_geral_html)
                geral_ja_inserida = True

            tabela_html = ""
            mostra_tabela_por_fase = (
                not eh_mata_mata
                and not e_evento_so_classificacao_geral
                and len(times_da_fase) > 2
                and grupo_e_consistente(partidas_fase)
            )
            if mostra_tabela_por_fase:
                standings = compute_standings(partidas_fase)
                tabela_html = build_standings_html(standings, nomes)

            linhas = "".join(build_match_row_html(p, evento, rating_index, nomes, ratings_atuais)
                              for p in partidas_fase)

            titulo_fase = f'<h3 class="fase-titulo">{fase}</h3>' if fase != "Resultados" else ""
            blocos_fase.append(f"""
            <div class="fase-bloco">
              {titulo_fase}
              {tabela_html}
              <div class="matches">{linhas}</div>
            </div>""")

        # Se nao houve nenhuma fase de mata-mata, a classificacao geral
        # ainda nao foi inserida -- bota no final, e o unico lugar possivel.
        if classificacao_geral_html and not geral_ja_inserida:
            blocos_fase.append(classificacao_geral_html)

        secoes_html.append(f"""
        <section class="tournament">
          <h2>{evento}</h2>
          {''.join(blocos_fase)}
        </section>""")

    return PAGE_TEMPLATE.format(
        titulo=f"Resultados {ano}",
        descricao=f"Todos os resultados de vôlei masculino internacional em {ano}: "
                   f"Liga das Nações, campeonatos continentais e outros torneios, "
                   f"com a variação de rating Elo de cada seleção.",
        url_completa=f"{BASE_URL}anos/{ano}.html",
        nav=build_nav("../", anos),
        conteudo=f"""
        <div class="page-header-row">
          <h1>Temporada {ano}</h1>
          <a class="page-header-link" href="../rankings/{ano}.html">Ranking Final {ano}</a>
        </div>
        {''.join(secoes_html)}""",
        css_prefix="../",
    )


def build_selecao_html(codigo: str, nome: str, rating_atual: float | None,
                        partidas_da_selecao: list[dict], rating_index: dict,
                        nomes: dict[str, str], ratings_atuais: dict[str, float], anos: list[int]) -> str:
    linhas = []
    for p in partidas_da_selecao:
        sou_a = p["team_a"] == codigo
        adversario = p["team_b"] if sou_a else p["team_a"]
        meus_sets = p["sets_a"] if sou_a else p["sets_b"]
        sets_adv = p["sets_b"] if sou_a else p["sets_a"]
        key = (p["match_date"], p["event"], codigo, adversario)
        rating = rating_index.get(key)
        delta = delta_html(rating[1] - rating[0]) if rating else ""
        rating_apos = f"{rating[1]:.1f}" if rating else "?"
        rating_adv = ratings_atuais.get(adversario)
        rating_adv_str = f'<span class="adv-rating">{rating_adv:.0f}</span>' if rating_adv is not None else ""

        linhas.append(f"""
        <div class="hist-row">
          <div class="hist-date">{format_date_pt(p['match_date'])}</div>
          <div class="hist-event">{p['event']}</div>
          <a class="hist-adv" href="{adversario}.html">
            <span class="hist-adv-nome">{nome_completo(adversario, nomes)}</span>
            {rating_adv_str}
          </a>
          <div class="scoreboard">{meus_sets}&ndash;{sets_adv}</div>
          <div class="hist-rating">{rating_apos} {delta}</div>
        </div>""")

    rating_str = f"{rating_atual:.1f}" if rating_atual is not None else "?"
    corpo_lista = "".join(linhas) if linhas else '<p class="vazio">Nenhuma partida registrada ainda.</p>'

    return PAGE_TEMPLATE.format(
        titulo=f"{nome} ({codigo})",
        descricao=f"Histórico completo de resultados e evolução do rating Elo da "
                   f"seleção masculina de vôlei de {nome} desde 2013. Rating atual: {rating_str}.",
        url_completa=f"{BASE_URL}selecoes/{codigo}.html",
        nav=build_nav("../", anos),
        conteudo=f"""
        <h1>{nome} <span class="codigo-grande">{codigo}</span></h1>
        <p class="rating-atual-label">Rating atual</p>
        <p class="rating-atual-valor">{rating_str}</p>
        <h2>Histórico de partidas</h2>
        <div class="historico">{corpo_lista}</div>""",
        css_prefix="../",
    )


PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="google-site-verification" content="mPVjAMjmJPM3mCAXwFZgy2kb1P6JmNy_UtTABBZzRbE" />
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{titulo} &mdash; Elo Vôlei</title>
<meta name="description" content="{descricao}">
<link rel="canonical" href="{url_completa}">
<meta property="og:type" content="website">
<meta property="og:title" content="{titulo} &mdash; Elo Vôlei">
<meta property="og:description" content="{descricao}">
<meta property="og:url" content="{url_completa}">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="{titulo} &mdash; Elo Vôlei">
<meta name="twitter:description" content="{descricao}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;700&family=Inter:wght@400;500&family=JetBrains+Mono:wght@500;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{css_prefix}style.css">
</head>
<body>
{nav}
<main>
{conteudo}
</main>
</body>
</html>
"""

STYLE_CSS = """
:root {
  --bg: #F7F7F4;
  --ink: #14181F;
  --ink-soft: #5A6270;
  --gold: #C98A00;
  --gold-bg: #FBEFD2;
  --blue: #1C4E80;
  --card: #FFFFFF;
  --border: #E4E2DA;
  --pos: #1F7A45;
  --pos-bg: #E3F3E9;
  --neg: #A5342A;
  --neg-bg: #FBE7E4;
  --board: #14181F;
  --board-text: #F2B705;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font-family: 'Inter', sans-serif;
  line-height: 1.5;
}
a { color: inherit; text-decoration: none; }
nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 0.75rem;
  padding: 1rem 1.5rem;
  max-width: 900px;
  margin: 0 auto;
  border-bottom: 3px solid var(--gold);
}
.nav-home {
  font-family: 'Barlow Condensed', sans-serif;
  font-weight: 700;
  font-size: 1.6rem;
  text-transform: uppercase;
  letter-spacing: 0.02em;
}
.nav-anos {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.8rem;
}
.nav-continentes {
  font-family: 'Barlow Condensed', sans-serif;
  font-weight: 500;
  text-transform: uppercase;
  font-size: 0.85rem;
  color: var(--blue);
}
.nav-anos a {
  color: var(--ink-soft);
  padding: 0.15rem 0.4rem;
  border-radius: 4px;
}
.nav-anos a:hover { background: var(--gold-bg); color: var(--gold); }
main {
  max-width: 900px;
  margin: 0 auto;
  padding: 1.5rem;
}
h1 {
  font-family: 'Barlow Condensed', sans-serif;
  font-weight: 700;
  font-size: 2rem;
  text-transform: uppercase;
  letter-spacing: 0.01em;
  margin: 0.5rem 0 0.25rem;
}
.codigo-grande {
  font-family: 'JetBrains Mono', monospace;
  color: var(--ink-soft);
  font-size: 1.2rem;
  margin-left: 0.5rem;
}
.page-header-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin: 0.5rem 0 0.25rem;
}
.page-header-row h1 { margin: 0; }
.page-header-link {
  font-family: 'Barlow Condensed', sans-serif;
  font-weight: 500;
  text-transform: uppercase;
  font-size: 0.85rem;
  color: var(--blue);
  white-space: nowrap;
}
.subtitulo { color: var(--ink-soft); margin: 0 0 1.5rem; }
.ultima-atualizacao {
  color: var(--ink-soft);
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem;
  margin: -1rem 0 1.5rem;
}
h2 {
  font-family: 'Barlow Condensed', sans-serif;
  font-weight: 700;
  font-size: 1.4rem;
  text-transform: uppercase;
  color: var(--blue);
  border-bottom: 1px solid var(--border);
  padding-bottom: 0.4rem;
  margin: 1.5rem 0 0.75rem;
}
.tournament { margin-bottom: 1.5rem; }
.fase-bloco { margin-bottom: 1.25rem; }
.fase-titulo {
  font-family: 'Barlow Condensed', sans-serif;
  font-weight: 500;
  font-size: 1rem;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  color: var(--ink-soft);
  margin: 0.75rem 0 0.5rem;
}
.standings {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  margin-bottom: 0.6rem;
}
.standings-row {
  display: grid;
  grid-template-columns: 1.5rem 1fr 2.2rem 2.2rem auto;
  align-items: center;
  gap: 0.5rem;
  background: var(--gold-bg);
  border-radius: 6px;
  padding: 0.3rem 0.7rem;
  font-size: 0.78rem;
}
.standings-pos { color: var(--ink-soft); font-family: 'JetBrains Mono', monospace; }
.standings-nome { font-weight: 500; }
.standings-nome:hover { color: var(--blue); }
.standings-v, .standings-d {
  font-family: 'JetBrains Mono', monospace;
  text-align: center;
}
.standings-avg {
  font-family: 'JetBrains Mono', monospace;
  color: var(--ink-soft);
  text-align: right;
  font-size: 0.72rem;
}
.match-row {
  display: grid;
  grid-template-columns: 3.2rem auto 1fr auto 1fr auto;
  align-items: center;
  gap: 0.5rem;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.6rem 0.9rem;
  margin-bottom: 0.5rem;
}
.match-date {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem;
  color: var(--ink-soft);
  text-transform: uppercase;
}
.match-team {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.35rem;
  font-weight: 500;
  font-size: 0.88rem;
}
.team-a { justify-content: flex-end; text-align: right; }
.team-b { justify-content: flex-start; text-align: left; }
.match-team:hover .team-nome { color: var(--blue); }
.team-rating {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.72rem;
  color: var(--ink-soft);
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 0 0.3rem;
}
.scoreboard {
  background: var(--board);
  color: var(--board-text);
  font-family: 'JetBrains Mono', monospace;
  font-weight: 700;
  font-size: 1.1rem;
  font-variant-numeric: tabular-nums;
  padding: 0.3rem 0.6rem;
  border-radius: 6px;
  min-width: 3.4rem;
  text-align: center;
}
.delta {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.72rem;
  font-weight: 500;
  padding: 0.1rem 0.4rem;
  border-radius: 4px;
  white-space: nowrap;
}
.delta-pos { color: var(--pos); background: var(--pos-bg); }
.delta-neg { color: var(--neg); background: var(--neg-bg); }
.ranking { display: flex; flex-direction: column; gap: 0.3rem; }
.rank-row {
  display: grid;
  grid-template-columns: 2.5rem 1fr 3.5rem 5rem;
  align-items: center;
  gap: 0.75rem;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.55rem 0.9rem;
}
.rank-row:hover { border-color: var(--gold); }
.rank-pos { color: var(--ink-soft); font-family: 'JetBrains Mono', monospace; font-size: 0.85rem; }
.rank-nome { font-weight: 500; }
.rank-codigo { color: var(--ink-soft); font-family: 'JetBrains Mono', monospace; font-size: 0.8rem; }
.rank-rating {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 700;
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.rating-atual-label { color: var(--ink-soft); margin: 0.5rem 0 0; font-size: 0.85rem; text-transform: uppercase; }
.rating-atual-valor {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 700;
  font-size: 2.2rem;
  margin: 0 0 1rem;
}
.historico { display: flex; flex-direction: column; gap: 0.4rem; }
.hist-row {
  display: grid;
  grid-template-columns: 5.5rem 1fr 8rem auto 6rem;
  align-items: center;
  gap: 0.6rem;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.5rem 0.8rem;
  font-size: 0.85rem;
}
.hist-date { font-family: 'JetBrains Mono', monospace; color: var(--ink-soft); font-size: 0.75rem; }
.hist-event { color: var(--ink-soft); font-size: 0.78rem; }
.hist-adv {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.1rem;
  font-weight: 500;
}
.hist-adv-nome {}
.hist-adv:hover .hist-adv-nome { color: var(--blue); }
.adv-rating {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.7rem;
  color: var(--ink-soft);
}
.hist-rating { font-family: 'JetBrains Mono', monospace; text-align: right; }
.vazio { color: var(--ink-soft); font-style: italic; }
@media (max-width: 640px) {
  .match-row { grid-template-columns: 2.4rem auto 1fr auto 1fr auto; gap: 0.3rem; padding: 0.5rem 0.6rem; }
  .match-team { font-size: 0.85rem; }
  .rank-row { grid-template-columns: 2rem 1fr 3rem; }
  .rank-codigo { display: none; }
  .hist-row { grid-template-columns: 1fr; text-align: left; gap: 0.15rem; }
  .standings-row { grid-template-columns: 1.3rem 1fr 2rem 2rem; font-size: 0.72rem; }
  .standings-avg { display: none; }
}
"""


def main():
    partidas = load_partidas(PARTIDAS_CSV)
    rating_index = load_rating_deltas(HISTORICO_CSV)
    ratings_atuais = load_ratings_atuais(RATINGS_ATUAIS_CSV)
    nomes = load_nomes(NOMES_CSV)
    historico_rows = load_historico_rows(HISTORICO_CSV)
    seed_ratings = load_seed_ratings(SEED_CSV)
    confederacoes = load_confederacoes(SEED_CSV)

    anos = sorted({int(p["season"]) for p in partidas})

    os.makedirs(DOCS_DIR, exist_ok=True)
    os.makedirs(f"{DOCS_DIR}/anos", exist_ok=True)
    os.makedirs(f"{DOCS_DIR}/selecoes", exist_ok=True)
    os.makedirs(f"{DOCS_DIR}/rankings", exist_ok=True)

    with open(f"{DOCS_DIR}/style.css", "w", encoding="utf-8") as f:
        f.write(STYLE_CSS)

    with open(f"{DOCS_DIR}/index.html", "w", encoding="utf-8") as f:
        ultima_atualizacao = datetime.now().strftime("%d/%m/%Y %H:%M")
        f.write(build_index_html(ratings_atuais, nomes, anos, ultima_atualizacao))

    with open(f"{DOCS_DIR}/continentes.html", "w", encoding="utf-8") as f:
        f.write(build_continentes_html(ratings_atuais, confederacoes, nomes, anos))

    partidas_por_ano: dict[int, list[dict]] = defaultdict(list)
    for p in partidas:
        partidas_por_ano[int(p["season"])].append(p)

    for ano in anos:
        with open(f"{DOCS_DIR}/anos/{ano}.html", "w", encoding="utf-8") as f:
            f.write(build_ano_html(ano, partidas_por_ano[ano], rating_index, nomes, ratings_atuais, anos))

        ranking_no_ano = compute_ranking_at(historico_rows, seed_ratings, f"{ano}-12-31")
        with open(f"{DOCS_DIR}/rankings/{ano}.html", "w", encoding="utf-8") as f:
            f.write(build_ranking_ano_html(ano, ranking_no_ano, nomes, anos))

    partidas_por_selecao: dict[str, list[dict]] = defaultdict(list)
    for p in partidas:
        partidas_por_selecao[p["team_a"]].append(p)
        partidas_por_selecao[p["team_b"]].append(p)

    todos_os_codigos = set(ratings_atuais.keys()) | set(partidas_por_selecao.keys())
    for codigo in todos_os_codigos:
        partidas_desc = sorted(partidas_por_selecao.get(codigo, []),
                                key=lambda p: p["match_date"], reverse=True)
        with open(f"{DOCS_DIR}/selecoes/{codigo}.html", "w", encoding="utf-8") as f:
            f.write(build_selecao_html(
                codigo, nome_completo(codigo, nomes), ratings_atuais.get(codigo),
                partidas_desc, rating_index, nomes, ratings_atuais, anos))

    todas_urls = [BASE_URL, f"{BASE_URL}continentes.html"]
    for ano in anos:
        todas_urls.append(f"{BASE_URL}anos/{ano}.html")
        todas_urls.append(f"{BASE_URL}rankings/{ano}.html")
    for codigo in sorted(todos_os_codigos):
        todas_urls.append(f"{BASE_URL}selecoes/{codigo}.html")

    urls_xml = "\n".join(f"  <url><loc>{url}</loc></url>" for url in todas_urls)
    with open(f"{DOCS_DIR}/sitemap.xml", "w", encoding="utf-8") as f:
        f.write(f'<?xml version="1.0" encoding="UTF-8"?>\n'
                 f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                 f'{urls_xml}\n</urlset>\n')

    with open(f"{DOCS_DIR}/robots.txt", "w", encoding="utf-8") as f:
        f.write(f"User-agent: *\nAllow: /\n\nSitemap: {BASE_URL}sitemap.xml\n")

    # Desativa o processamento Jekyll do GitHub Pages -- sem isso, arquivos
    # como sitemap.xml podem ser alterados de formas sutis que quebram
    # parsers estritos (ex: Google Search Console), mesmo continuando a
    # abrir normalmente num navegador comum.
    open(f"{DOCS_DIR}/.nojekyll", "w").close()

    print(f"Site gerado em {DOCS_DIR}/")
    print(f"  1 pagina inicial (ranking)")
    print(f"  {len(anos)} paginas de ano ({anos[0]}-{anos[-1]})")
    print(f"  {len(todos_os_codigos)} paginas de selecao")
    print(f"  sitemap.xml com {len(todas_urls)} URLs, robots.txt")


if __name__ == "__main__":
    main()
