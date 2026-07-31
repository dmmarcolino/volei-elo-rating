"""
build_site.py

Le partidas.csv + historico_ratings.csv (ja gerados pelo orquestrador) e
gera uma pagina HTML estatica com os resultados, agrupados por torneio,
com a variacao de rating de cada selecao em cada partida.

O arquivo gerado fica em docs/index.html -- essa e a pasta que o GitHub
Pages vai publicar quando ativarmos isso mais pra frente.

Uso:
    python build_site.py
"""

from __future__ import annotations

import csv
import os
from collections import defaultdict
from datetime import datetime

PARTIDAS_CSV = "../data/partidas.csv"
HISTORICO_CSV = "../data/historico_ratings.csv"
OUTPUT_PATH = "../docs/index.html"

MESES_PT = {
    1: "jan", 2: "fev", 3: "mar", 4: "abr", 5: "mai", 6: "jun",
    7: "jul", 8: "ago", 9: "set", 10: "out", 11: "nov", 12: "dez",
}


def load_partidas(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_rating_deltas(path: str) -> dict[tuple, tuple[float, float]]:
    """Indexa o historico por (data, evento, time, adversario) ->
    (rating_before, rating_after), para consulta rapida ao montar as linhas."""
    index = {}
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key = (row["match_date"], row["event"], row["team"], row["opponent"])
            index[key] = (float(row["rating_before"]), float(row["rating_after"]))
    return index


def format_date_pt(iso_date: str) -> str:
    d = datetime.strptime(iso_date, "%Y-%m-%d").date()
    return f"{d.day:02d} {MESES_PT[d.month]}"


def delta_html(delta: float) -> str:
    sign = "+" if delta >= 0 else ""
    cls = "delta-pos" if delta >= 0 else "delta-neg"
    arrow = "&#9650;" if delta >= 0 else "&#9660;"
    return f'<span class="delta {cls}">{arrow} {sign}{delta:.1f}</span>'


def build_html(partidas: list[dict], rating_index: dict) -> str:
    # Agrupa por evento, preservando a ordem de primeira aparicao (cronologica,
    # ja que partidas.csv ja vem ordenado assim).
    eventos: dict[str, list[dict]] = defaultdict(list)
    ordem_eventos: list[str] = []
    for p in partidas:
        evento = p["event"]
        if evento not in eventos:
            ordem_eventos.append(evento)
        eventos[evento].append(p)

    secoes_html = []
    for evento in ordem_eventos:
        linhas = []
        for p in eventos[evento]:
            key_a = (p["match_date"], evento, p["team_a"], p["team_b"])
            key_b = (p["match_date"], evento, p["team_b"], p["team_a"])
            rating_a = rating_index.get(key_a)
            rating_b = rating_index.get(key_b)
            delta_a = delta_html(rating_a[1] - rating_a[0]) if rating_a else ""
            delta_b = delta_html(rating_b[1] - rating_b[0]) if rating_b else ""

            linhas.append(f"""
            <div class="match-row">
              <div class="match-date">{format_date_pt(p['match_date'])}</div>
              <div class="match-team team-a">
                <span class="team-code">{p['team_a']}</span>{delta_a}
              </div>
              <div class="scoreboard">{p['sets_a']}&ndash;{p['sets_b']}</div>
              <div class="match-team team-b">
                <span class="team-code">{p['team_b']}</span>{delta_b}
              </div>
            </div>""")

        secoes_html.append(f"""
        <section class="tournament">
          <h2>{evento}</h2>
          <div class="matches">{''.join(linhas)}</div>
        </section>""")

    return HTML_TEMPLATE.format(secoes="".join(secoes_html))


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Elo Vôlei &mdash; Resultados</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;700&family=Inter:wght@400;500&family=JetBrains+Mono:wght@500;700&display=swap" rel="stylesheet">
<style>
  :root {{
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
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    background: var(--bg);
    color: var(--ink);
    font-family: 'Inter', sans-serif;
    line-height: 1.5;
  }}
  header {{
    padding: 2.5rem 1.5rem 1.5rem;
    max-width: 720px;
    margin: 0 auto;
    border-bottom: 3px solid var(--gold);
  }}
  header h1 {{
    font-family: 'Barlow Condensed', sans-serif;
    font-weight: 700;
    font-size: 2.5rem;
    letter-spacing: 0.02em;
    text-transform: uppercase;
    margin: 0;
  }}
  header p {{
    color: var(--ink-soft);
    margin: 0.25rem 0 0;
    font-size: 0.95rem;
  }}
  main {{
    max-width: 720px;
    margin: 0 auto;
    padding: 1.5rem;
  }}
  .tournament {{
    margin-bottom: 2.5rem;
  }}
  .tournament h2 {{
    font-family: 'Barlow Condensed', sans-serif;
    font-weight: 700;
    font-size: 1.4rem;
    text-transform: uppercase;
    letter-spacing: 0.01em;
    color: var(--blue);
    border-bottom: 1px solid var(--border);
    padding-bottom: 0.4rem;
    margin: 0 0 0.75rem;
  }}
  .match-row {{
    display: grid;
    grid-template-columns: 3.2rem 1fr auto 1fr;
    align-items: center;
    gap: 0.75rem;
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 0.6rem 0.9rem;
    margin-bottom: 0.5rem;
  }}
  .match-date {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.75rem;
    color: var(--ink-soft);
    text-transform: uppercase;
  }}
  .match-team {{
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-weight: 500;
    font-size: 0.95rem;
  }}
  .team-a {{ justify-content: flex-end; text-align: right; }}
  .team-b {{ justify-content: flex-start; text-align: left; }}
  .team-code {{
    font-weight: 500;
  }}
  .scoreboard {{
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
  }}
  .delta {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.72rem;
    font-weight: 500;
    padding: 0.1rem 0.4rem;
    border-radius: 4px;
    white-space: nowrap;
  }}
  .delta-pos {{ color: var(--pos); background: var(--pos-bg); }}
  .delta-neg {{ color: var(--neg); background: var(--neg-bg); }}
  @media (max-width: 560px) {{
    .match-row {{ grid-template-columns: 2.6rem 1fr auto 1fr; gap: 0.4rem; padding: 0.5rem 0.6rem; }}
    .match-team {{ font-size: 0.85rem; }}
    .scoreboard {{ font-size: 0.95rem; min-width: 2.8rem; }}
  }}
</style>
</head>
<body>
<header>
  <h1>Elo Vôlei</h1>
  <p>Rating histórico das seleções masculinas &mdash; resultados desde 2013</p>
</header>
<main>
{secoes}
</main>
</body>
</html>
"""


def main():
    partidas = load_partidas(PARTIDAS_CSV)
    rating_index = load_rating_deltas(HISTORICO_CSV)

    html = build_html(partidas, rating_index)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Site gerado: {OUTPUT_PATH}")
    print(f"  {len(partidas)} partidas, {len(set(p['event'] for p in partidas))} torneios")


if __name__ == "__main__":
    main()
