"""
Teste rapido e manual do elo_engine.py com dados sinteticos.
Nao e uma suite formal (pytest) -- e so pra validar visualmente que
o motor calcula e nao quebra, antes de alimentar com dados reais.

Rodar com: python test_elo_engine.py
"""

from datetime import date
from elo_engine import EloEngine, Match, DEFAULT_CONFIG


def main():
    engine = EloEngine(config=DEFAULT_CONFIG)

    teams = ["BRA", "RUS", "RWA", "LUX"]  # top tier, top tier, tier baixo, tier baixo
    engine.load_initial_ratings(teams)

    print("Ratings iniciais (seed por tier):")
    for team, rating in engine.current_ranking():
        print(f"  {team}: {rating:.1f}")
    print()

    matches = [
        # Zebra: time de tier baixo vence favorito -> deve gerar ganho grande
        Match(date(2024, 1, 10), 2024, "RWA", "BRA", 3, 2, "Amistoso", is_final=False),
        # Resultado esperado: favorito vence favorito -> ganho pequeno
        Match(date(2024, 2, 5), 2024, "BRA", "RUS", 3, 1, "Liga Mundial", is_final=False),
        # Times de tier baixo se enfrentando
        Match(date(2024, 3, 1), 2024, "LUX", "RWA", 3, 0, "Torneio Regional", is_final=False),
        # Uma final -- nao deve contar para o fator K das proximas partidas
        Match(date(2024, 4, 1), 2024, "BRA", "RUS", 3, 0, "Final Liga Mundial", is_final=True),
        # Mais uma partida normal do BRA na mesma temporada -- fator K deve
        # refletir que BRA ja jogou 2 partidas nao-finais antes desta (n=2)
        Match(date(2024, 5, 1), 2024, "BRA", "LUX", 3, 0, "Amistoso", is_final=False),
    ]

    for m in matches:
        k_a_before = engine.k_factor_for(m.season, m.team_a)
        k_b_before = engine.k_factor_for(m.season, m.team_b)
        engine.process_match(m)
        print(f"{m.match_date} | {m.event}")
        print(f"  {m.team_a} {m.sets_a} x {m.sets_b} {m.team_b}  "
              f"(K_{m.team_a}={k_a_before}, K_{m.team_b}={k_b_before})")
        print(f"  Novo rating {m.team_a}: {engine.ratings[m.team_a]:.2f}  |  "
              f"Novo rating {m.team_b}: {engine.ratings[m.team_b]:.2f}")
        print()

    print("Ranking final:")
    for team, rating in engine.current_ranking():
        print(f"  {team}: {rating:.2f}")
    print()

    print("Historico completo do BRA:")
    for snap in engine.history_for("BRA"):
        print(f"  {snap.match_date} vs {snap.opponent}: "
              f"{snap.rating_before:.2f} -> {snap.rating_after:.2f} ({snap.result})")

    print()
    print("Ranking reconstruido 'como estava' em 2024-03-15:")
    for team, rating in engine.ranking_at(date(2024, 3, 15)):
        print(f"  {team}: {rating:.2f}")


if __name__ == "__main__":
    main()
