"""Modelo de partido: fuerza de equipos -> goles esperados -> Poisson.

Dos modos, mismo contrato match_lambdas(team_a, team_b) -> (lambda_a, lambda_b):

- "ratings" (fase 2, por defecto si existe data/ratings.json): ataque/defensa
  propios ajustados por MLE Poisson sobre el histórico internacional
  (engine/train.py).  lambda = exp(mu + att_a - def_b + ventaja_anfitrión).
- "elo" (fase 1, fallback): Elo de eloratings.net convertido a reparto de goles.
"""

import math
import random

# Parámetros del modelo. Se exportan a docs/data.json para que el simulador JS
# del "¿y si...?" use exactamente los mismos números.
PARAMS = {
    "mode": "elo",        # simulate.py lo cambia a "ratings" si hay entrenamiento
    # — modo ratings (los rellena simulate.py desde data/ratings.json) —
    "mu": None,           # log-goles base por equipo
    "home_adv": None,     # ventaja de local entrenada (se aplica a MEX/USA/CAN)
    "lambda_min": 0.15,   # red de seguridad ante cruces extremos
    "lambda_max": 3.6,
    # — modo elo —
    "host_bonus": 60,     # puntos Elo extra para MEX/USA/CAN (juegan en casa)
    "base_goals": 2.8,    # goles totales esperados entre dos equipos parejos
    "share_damp": 0.78,   # amortigua E al repartir goles: la puntuación Elo ya
                          #   cuenta los empates como 0.5, usarla cruda infla al
                          #   favorito (calibrado para que el E implícito
                          #   del Poisson coincida con el E del Elo)
    "clamp_lo": 0.15,     # recorte del reparto para evitar lambdas degeneradas
    "clamp_hi": 0.85,     #   en cruces muy desiguales
    # — común —
    "pen_tilt": 0.25,     # cuánto inclina la fuerza la tanda de penaltis
}


def expected_score(team_a, team_b):
    """Puntuación esperada Elo del equipo A (0..1), con bonus de anfitrión."""
    dr = team_a["elo"] - team_b["elo"]
    if team_a.get("host"):
        dr += PARAMS["host_bonus"]
    if team_b.get("host"):
        dr -= PARAMS["host_bonus"]
    return 1.0 / (1.0 + 10.0 ** (-dr / 400.0))


def match_lambdas(team_a, team_b):
    """Goles esperados (lambda_a, lambda_b) del partido A vs B."""
    if PARAMS["mode"] == "ratings":
        mu, h = PARAMS["mu"], PARAMS["home_adv"]
        la = math.exp(mu + team_a["att"] - team_b["def"] +
                      (h if team_a.get("host") else 0.0))
        lb = math.exp(mu + team_b["att"] - team_a["def"] +
                      (h if team_b.get("host") else 0.0))
        lo, hi = PARAMS["lambda_min"], PARAMS["lambda_max"]
        return min(max(la, lo), hi), min(max(lb, lo), hi)
    e = expected_score(team_a, team_b)
    share = 0.5 + (e - 0.5) * PARAMS["share_damp"]
    share = min(max(share, PARAMS["clamp_lo"]), PARAMS["clamp_hi"])
    base = PARAMS["base_goals"]
    return base * share, base * (1.0 - share)


def strength_share(team_a, team_b):
    """Fuerza relativa de A (0..1); decide la inclinación de los penaltis."""
    if PARAMS["mode"] == "ratings":
        la, lb = match_lambdas(team_a, team_b)
        return la / (la + lb)
    return expected_score(team_a, team_b)


def poisson(lam, rng):
    """Muestra de una Poisson(lam) (algoritmo de Knuth; lam < 4 siempre aquí)."""
    limit = math.exp(-lam)
    k, p = 0, rng.random()
    while p > limit:
        k += 1
        p *= rng.random()
    return k


def sim_group_match(team_a, team_b, rng):
    """Marcador (goles_a, goles_b) de un partido de grupos."""
    la, lb = match_lambdas(team_a, team_b)
    return poisson(la, rng), poisson(lb, rng)


def sim_knockout_match(team_a, team_b, rng):
    """Devuelve True si gana A una eliminatoria (90' + prórroga + penaltis)."""
    la, lb = match_lambdas(team_a, team_b)
    ga, gb = poisson(la, rng), poisson(lb, rng)
    if ga != gb:
        return ga > gb
    ga, gb = poisson(la / 3.0, rng), poisson(lb / 3.0, rng)  # prórroga
    if ga != gb:
        return ga > gb
    e = strength_share(team_a, team_b)  # penaltis, casi moneda al aire
    p_a = 0.5 + (e - 0.5) * PARAMS["pen_tilt"]
    return rng.random() < p_a


__all__ = ["PARAMS", "expected_score", "strength_share", "match_lambdas",
           "poisson", "sim_group_match", "sim_knockout_match", "random"]
