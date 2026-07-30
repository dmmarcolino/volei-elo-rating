"""
elo_engine.py

Motor de rating Elo para selecoes masculinas de volei.

Baseado no modelo original (2003-2011):
- Rating inicial por tier (seed manual, nao comeca todo mundo igual)
- Fator K variavel por volume de partidas na temporada (excluindo finais)
- Sem decaimento temporal (a propria dinamica do Elo se autocorrige)
- Duelo direto entre qualquer par de selecoes que se enfrentaram
  (diferente do projeto de F1: aqui nao ha restricao de "mesmo carro/equipe",
  toda partida internacional oficial conta)

Este modulo e deliberadamente independente de qualquer interface (tkinter, web).
Ele so entende de dados (partidas) e devolve dados (ratings, historico).
Tanto o app desktop quanto o gerador do site estatico podem reusar o mesmo motor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional
import math


# ---------------------------------------------------------------------------
# Configuracao
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class KTier:
    """Uma faixa do fator K: se o numero de partidas na temporada (n) cai
    entre min_matches e max_matches, o fator K usado e k_value."""
    min_matches: int
    max_matches: int
    k_value: int


@dataclass(frozen=True)
class EloConfig:
    """Todos os parametros configuraveis do modelo, reunidos num so lugar.

    Mantidos como config (nao hardcoded) para permitir ajuste empirico
    sem mexer na logica do motor -- mesmo principio usado no projeto de F1.
    """

    # Tabela de rating inicial por tier de selecao (do documento original).
    # Times fora dessas listas caem no tier_default.
    tier_2800: tuple[str, ...] = ("BRA", "ITA", "RUS", "SCG")
    tier_2700: tuple[str, ...] = ("ARG", "CUB", "FRA", "GRE", "NED", "USA")
    tier_2600: tuple[str, ...] = (
        "BUL", "CAN", "CHN", "CZE", "ESP", "GER", "JPN", "KOR", "POL", "POR",
    )
    tier_2500: tuple[str, ...] = (
        "AUS", "BEL", "CRO", "EGY", "FIN", "HUN", "SLO", "SVK", "TUN",
        "TUR", "UKR", "VEN",
    )
    rating_2800: int = 2800
    rating_2700: int = 2700
    rating_2600: int = 2600
    rating_2500: int = 2500
    rating_default: int = 2400          # "demais paises"
    rating_small_islands: int = 2200     # ilhas pequenas / selecoes minimas
    small_islands: tuple[str, ...] = ()  # preencher conforme necessario

    # Fator K por volume de partidas na temporada (excluindo finais).
    k_tiers: tuple[KTier, ...] = (
        KTier(1, 4, 30),
        KTier(5, 8, 25),
        KTier(9, 12, 20),
        KTier(13, 16, 15),
        KTier(17, 99, 10),
    )
    k_default_no_history: int = 30  # equipe sem partidas registradas na temporada ainda

    elo_divisor: int = 400  # divisor padrao da formula de Elo


DEFAULT_CONFIG = EloConfig()


# ---------------------------------------------------------------------------
# Estruturas de dados
# ---------------------------------------------------------------------------

@dataclass
class Match:
    """Uma partida internacional entre duas selecoes."""
    match_date: date
    season: int              # temporada/ano usado para o calculo de K
    team_a: str               # codigo da selecao (ex: "BRA")
    team_b: str
    sets_a: int                # sets vencidos pela equipe A
    sets_b: int                # sets vencidos pela equipe B
    event: str                  # nome do torneio (para auditoria/log)
    is_final: bool = False       # excluido da contagem de partidas p/ fator K

    def winner(self) -> str:
        if self.sets_a > self.sets_b:
            return self.team_a
        if self.sets_b > self.sets_a:
            return self.team_b
        raise ValueError(f"Partida sem vencedor (empate em sets) em {self}")


@dataclass
class RatingSnapshot:
    """Um ponto no historico de rating de uma selecao, apos uma partida."""
    match_date: date
    season: int
    team: str
    rating_before: float
    rating_after: float
    opponent: str
    event: str
    result: str  # "W" ou "L"


@dataclass
class EloEngine:
    """Mantem o estado corrente dos ratings e o historico completo.

    Uso tipico:
        engine = EloEngine(config=DEFAULT_CONFIG)
        engine.load_initial_ratings(list_of_team_codes)
        for match in matches_ordenadas_por_data:
            engine.process_match(match)
        engine.current_ratings()   -> dict {team: rating}
        engine.history_for("BRA")  -> lista de RatingSnapshot
    """

    config: EloConfig = field(default_factory=lambda: DEFAULT_CONFIG)
    ratings: dict[str, float] = field(default_factory=dict)
    history: list[RatingSnapshot] = field(default_factory=list)

    # Contagem de partidas por (temporada, selecao), excluindo finais.
    # Usada para determinar o fator K de cada selecao naquela temporada.
    _match_counts: dict[tuple[int, str], int] = field(default_factory=dict)

    # -- inicializacao ------------------------------------------------------

    def initial_rating_for(self, team: str) -> float:
        c = self.config
        if team in c.tier_2800:
            return c.rating_2800
        if team in c.tier_2700:
            return c.rating_2700
        if team in c.tier_2600:
            return c.rating_2600
        if team in c.tier_2500:
            return c.rating_2500
        if team in c.small_islands:
            return c.rating_small_islands
        return c.rating_default

    def load_initial_ratings(self, teams: list[str]) -> None:
        """Define o rating inicial (seed por tier) para cada selecao.
        Nao sobrescreve times ja carregados (idempotente)."""
        for team in teams:
            self.ratings.setdefault(team, self.initial_rating_for(team))

    # -- fator K --------------------------------------------------------

    def k_factor_for(self, season: int, team: str) -> int:
        """Fator K de uma selecao numa temporada, baseado no numero de
        partidas que ela jogou naquela temporada ate o momento (excluindo
        finais). Segue a tabela de faixas definida em EloConfig.k_tiers.
        """
        n = self._match_counts.get((season, team), 0)
        if n == 0:
            return self.config.k_default_no_history
        for tier in self.config.k_tiers:
            if tier.min_matches <= n <= tier.max_matches:
                return tier.k_value
        # acima da maior faixa definida: usa o K da ultima faixa
        return self.config.k_tiers[-1].k_value

    # -- logica central de Elo -------------------------------------------

    def _expected_score(self, rating_a: float, rating_b: float) -> float:
        return 1.0 / (1.0 + math.pow(10, (rating_b - rating_a) / self.config.elo_divisor))

    def process_match(self, match: Match) -> None:
        """Atualiza os ratings das duas selecoes com base no resultado
        da partida, e registra o snapshot no historico."""
        for team in (match.team_a, match.team_b):
            self.ratings.setdefault(team, self.initial_rating_for(team))

        rating_a = self.ratings[match.team_a]
        rating_b = self.ratings[match.team_b]

        winner = match.winner()
        score_a = 1.0 if winner == match.team_a else 0.0
        score_b = 1.0 - score_a

        expected_a = self._expected_score(rating_a, rating_b)
        expected_b = 1.0 - expected_a

        k_a = self.k_factor_for(match.season, match.team_a)
        k_b = self.k_factor_for(match.season, match.team_b)

        new_rating_a = rating_a + k_a * (score_a - expected_a)
        new_rating_b = rating_b + k_b * (score_b - expected_b)

        self.history.append(RatingSnapshot(
            match_date=match.match_date, season=match.season, team=match.team_a,
            rating_before=rating_a, rating_after=new_rating_a,
            opponent=match.team_b, event=match.event,
            result="W" if score_a == 1.0 else "L",
        ))
        self.history.append(RatingSnapshot(
            match_date=match.match_date, season=match.season, team=match.team_b,
            rating_before=rating_b, rating_after=new_rating_b,
            opponent=match.team_a, event=match.event,
            result="W" if score_b == 1.0 else "L",
        ))

        self.ratings[match.team_a] = new_rating_a
        self.ratings[match.team_b] = new_rating_b

        # Atualiza contagem de partidas (para o fator K de partidas futuras),
        # exceto se a partida for uma final.
        if not match.is_final:
            for team in (match.team_a, match.team_b):
                key = (match.season, team)
                self._match_counts[key] = self._match_counts.get(key, 0) + 1

    def process_matches(self, matches: list[Match]) -> None:
        """Processa uma lista de partidas em ordem cronologica.
        IMPORTANTE: a lista deve estar ordenada por match_date --
        o motor nao ordena sozinho, para deixar essa responsabilidade
        explicita em quem alimenta os dados (evita bugs silenciosos)."""
        for match in matches:
            self.process_match(match)

    # -- consultas ------------------------------------------------------

    def current_ratings(self) -> dict[str, float]:
        return dict(self.ratings)

    def current_ranking(self) -> list[tuple[str, float]]:
        """Ranking atual, do maior para o menor rating."""
        return sorted(self.ratings.items(), key=lambda kv: kv[1], reverse=True)

    def history_for(self, team: str) -> list[RatingSnapshot]:
        return [s for s in self.history if s.team == team]

    def ranking_at(self, as_of: date) -> list[tuple[str, float]]:
        """Reconstroi o ranking como ele estava em uma data especifica,
        varrendo o historico. Util para gerar o 'ranking anual' do site."""
        latest_by_team: dict[str, float] = {}
        for snap in self.history:
            if snap.match_date > as_of:
                continue
            latest_by_team[snap.team] = snap.rating_after
        # Times que nunca jogaram ate essa data mas ja tem rating inicial
        for team, rating in self.ratings.items():
            latest_by_team.setdefault(team, self.initial_rating_for(team))
        return sorted(latest_by_team.items(), key=lambda kv: kv[1], reverse=True)
