"""Fase 2: ratings propios ataque/defensa por máxima verosimilitud (Dixon-Coles).

Ajusta, sobre el histórico real de partidos internacionales
(data/international_results.csv, github.com/martj42/international_results):

    log lambda_home = mu + h·(no_neutral) + att_home − def_away
    log lambda_away = mu              + att_away − def_home

maximizando la log-verosimilitud Poisson ponderada con decaimiento temporal
exponencial (estilo Dixon-Coles 1997) y regularización L2, vía Adam (numpy).

Validación walk-forward honesta: se entrena solo con partidos ANTERIORES a los
Mundiales 2018 y 2022 y se mide log-loss y Brier 1X2 sobre ellos, comparando
con dos baselines. La media de log-loss elige el half-life del decaimiento.

Uso:  python engine/train.py [--skip-validation]
Salida: data/ratings.json  (lo consume engine/model.py y, vía data.json, el JS)
"""

import argparse
import csv
import json
import math
import sys
from datetime import date, datetime
from pathlib import Path

import numpy as np

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")  # consolas cp1252 de Windows

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "data" / "international_results.csv"

# id de teams.json -> nombre(s) en el dataset
ALIASES = {
    "MEX": ["Mexico"], "KOR": ["South Korea"], "RSA": ["South Africa"],
    "CZE": ["Czech Republic", "Czechia"], "CAN": ["Canada"], "QAT": ["Qatar"],
    "SUI": ["Switzerland"], "BIH": ["Bosnia and Herzegovina"],
    "BRA": ["Brazil"], "HAI": ["Haiti"], "SCO": ["Scotland"],
    "MAR": ["Morocco"], "USA": ["United States"], "PAR": ["Paraguay"],
    "AUS": ["Australia"], "TUR": ["Turkey", "Türkiye"], "GER": ["Germany"],
    "CIV": ["Ivory Coast"], "ECU": ["Ecuador"], "CUW": ["Curaçao"],
    "NED": ["Netherlands"], "JPN": ["Japan"], "TUN": ["Tunisia"],
    "SWE": ["Sweden"], "BEL": ["Belgium"], "EGY": ["Egypt"], "IRN": ["Iran"],
    "NZL": ["New Zealand"], "ESP": ["Spain"], "CPV": ["Cape Verde"],
    "KSA": ["Saudi Arabia"], "URU": ["Uruguay"], "FRA": ["France"],
    "SEN": ["Senegal"], "IRQ": ["Iraq"], "NOR": ["Norway"],
    "ARG": ["Argentina"], "ALG": ["Algeria"], "AUT": ["Austria"],
    "JOR": ["Jordan"], "POR": ["Portugal"], "COD": ["DR Congo"],
    "UZB": ["Uzbekistan"], "COL": ["Colombia"], "ENG": ["England"],
    "CRO": ["Croatia"], "GHA": ["Ghana"], "PAN": ["Panama"],
}

TRAIN_WINDOW_YEARS = 12     # ventana de datos previa al corte
FRIENDLY_WEIGHT = 0.5       # los amistosos pesan la mitad
MAX_GOALS = 10              # rejilla Poisson para probabilidades 1X2


def load_matches():
    matches = []
    with open(CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["home_score"] in ("NA", "") or r["away_score"] in ("NA", ""):
                continue  # partidos futuros del calendario
            matches.append({
                "date": date.fromisoformat(r["date"]),
                "home": r["home_team"], "away": r["away_team"],
                "gh": int(r["home_score"]), "ga": int(r["away_score"]),
                "tournament": r["tournament"],
                "neutral": r["neutral"].upper() == "TRUE",
            })
    return matches


def fit(matches, cutoff, half_life_years, l2_reg, iters=1200):
    """Ajusta el modelo con partidos en [cutoff−ventana, cutoff)."""
    start = date(cutoff.year - TRAIN_WINDOW_YEARS, cutoff.month, cutoff.day)
    rows = [m for m in matches if start <= m["date"] < cutoff]

    teams = sorted({m["home"] for m in rows} | {m["away"] for m in rows})
    idx = {t: i for i, t in enumerate(teams)}
    n = len(teams)

    hi = np.array([idx[m["home"]] for m in rows])
    ai = np.array([idx[m["away"]] for m in rows])
    gh = np.array([m["gh"] for m in rows], dtype=float)
    ga = np.array([m["ga"] for m in rows], dtype=float)
    home = np.array([0.0 if m["neutral"] else 1.0 for m in rows])
    days = np.array([(cutoff - m["date"]).days for m in rows], dtype=float)
    w = 0.5 ** (days / (half_life_years * 365.25))
    w *= np.where([m["tournament"] == "Friendly" for m in rows],
                  FRIENDLY_WEIGHT, 1.0)

    # parámetros: att[n], def[n], mu, h
    att = np.zeros(n); dfn = np.zeros(n)
    mu = math.log(1.3); h = 0.25
    m_t = np.zeros(2 * n + 2); v_t = np.zeros(2 * n + 2)  # estado Adam
    lr, b1, b2, eps = 0.05, 0.9, 0.999, 1e-8

    for it in range(1, iters + 1):
        lh = np.exp(mu + h * home + att[hi] - dfn[ai])
        la = np.exp(mu + att[ai] - dfn[hi])
        rh = w * (lh - gh)            # residuos ponderados d(NLL)/d(log lambda)
        ra = w * (la - ga)

        g_att = np.bincount(hi, rh, n) + np.bincount(ai, ra, n) + 2 * l2_reg * att
        g_def = -np.bincount(ai, rh, n) - np.bincount(hi, ra, n) + 2 * l2_reg * dfn
        g_mu = rh.sum() + ra.sum()
        g_h = (rh * home).sum()

        g = np.concatenate([g_att, g_def, [g_mu, g_h]])
        m_t = b1 * m_t + (1 - b1) * g
        v_t = b2 * v_t + (1 - b2) * g * g
        step = lr * (m_t / (1 - b1 ** it)) / (np.sqrt(v_t / (1 - b2 ** it)) + eps)
        att -= step[:n]; dfn -= step[n:2 * n]
        mu -= step[-2]; h -= step[-1]

    # recentrar para identifiabilidad (no cambia las lambdas)
    mu += att.mean() - dfn.mean()
    att -= att.mean(); dfn -= dfn.mean()
    return {"teams": teams, "att": att, "def": dfn, "mu": mu, "h": h,
            "n_matches": len(rows)}


def match_probs_1x2(model, home, away, neutral):
    """(p_local, p_empate, p_visitante) vía rejilla Poisson."""
    i, j = model["teams"].index(home), model["teams"].index(away)
    lh = math.exp(model["mu"] + (0 if neutral else model["h"]) +
                  model["att"][i] - model["def"][j])
    la = math.exp(model["mu"] + model["att"][j] - model["def"][i])
    k = np.arange(MAX_GOALS + 1)
    ph = np.exp(-lh) * lh ** k / np.array([math.factorial(x) for x in k])
    pa = np.exp(-la) * la ** k / np.array([math.factorial(x) for x in k])
    grid = np.outer(ph, pa)
    return np.tril(grid, -1).sum(), np.trace(grid), np.triu(grid, 1).sum()


def evaluate(matches, cutoff, eval_year, half_life, l2_reg):
    """Entrena hasta cutoff y mide log-loss/Brier 1X2 en el Mundial de eval_year."""
    model = fit(matches, cutoff, half_life, l2_reg)
    tests = [m for m in matches
             if m["tournament"] == "FIFA World Cup" and m["date"].year == eval_year
             and m["home"] in model["teams"] and m["away"] in model["teams"]]
    ll = br = 0.0
    freq = np.zeros(3)
    for m in tests:
        probs = match_probs_1x2(model, m["home"], m["away"], m["neutral"])
        out = 0 if m["gh"] > m["ga"] else (1 if m["gh"] == m["ga"] else 2)
        onehot = np.eye(3)[out]
        ll -= math.log(max(probs[out], 1e-12))
        br += ((np.array(probs) - onehot) ** 2).sum()
        freq[out] += 1
    n = len(tests)
    # baselines: uniforme y frecuencias observadas del propio test (cota optimista)
    p_freq = freq / n
    ll_uni = math.log(3)
    ll_freq = -sum(p_freq[k] * math.log(max(p_freq[k], 1e-12)) for k in range(3))
    return {"year": eval_year, "n": n, "logloss": ll / n, "brier": br / n,
            "ll_uniforme": ll_uni, "ll_frecuencias": ll_freq}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-validation", action="store_true")
    args = ap.parse_args()

    matches = load_matches()
    print(f"{len(matches)} partidos con marcador en el dataset")

    best_hl, best_l2 = 4.0, 1.0   # lo que ganó la última validación (12-jun-2026)
    if not args.skip_validation:
        print("\n— Validación walk-forward (entrena antes del torneo, evalúa en él) —")
        results = {}
        for hl in (2.5, 4.0):
            for l2 in (1.0, 2.5, 5.0):
                evs = [evaluate(matches, date(2018, 6, 14), 2018, hl, l2),
                       evaluate(matches, date(2022, 11, 20), 2022, hl, l2)]
                avg = sum(e["logloss"] for e in evs) / 2
                results[(hl, l2)] = avg
                print(f"  hl={hl}a L2={l2}: log-loss medio {avg:.4f}  "
                      f"(WC18 {evs[0]['logloss']:.4f} · WC22 {evs[1]['logloss']:.4f} · "
                      f"uniforme {evs[0]['ll_uniforme']:.4f})")
        best_hl, best_l2 = min(results, key=results.get)
        print(f"  → mejor combinación: half-life {best_hl}a, L2={best_l2} "
              f"(log-loss medio {results[(best_hl, best_l2)]:.4f})")

    print(f"\nEntrenando modelo final (todos los datos hasta hoy, "
          f"half-life {best_hl}a, L2={best_l2})...")
    model = fit(matches, date.today(), best_hl, best_l2)
    print(f"  {model['n_matches']} partidos · {len(model['teams'])} equipos · "
          f"mu={model['mu']:.3f} · ventaja_local={model['h']:.3f}")

    ratings, missing = {}, []
    for tid, names in ALIASES.items():
        name = next((nm for nm in names if nm in model["teams"]), None)
        if name is None:
            missing.append(tid)
            continue
        i = model["teams"].index(name)
        ratings[tid] = {"att": round(float(model["att"][i]), 4),
                        "def": round(float(model["def"][i]), 4)}
    if missing:
        raise SystemExit(f"Sin datos para: {missing}")

    out = {
        "trained": datetime.now().isoformat(timespec="seconds"),
        "method": "Poisson MLE estilo Dixon-Coles, decaimiento temporal "
                  f"half-life={best_hl}a, amistosos x{FRIENDLY_WEIGHT}, L2={best_l2}",
        "n_matches": model["n_matches"],
        "mu": round(float(model["mu"]), 4),
        "home_adv": round(float(model["h"]), 4),
        "ratings": ratings,
    }
    path = ROOT / "data" / "ratings.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"→ {path}")

    strength = sorted(ratings.items(),
                      key=lambda kv: kv[1]["att"] + kv[1]["def"], reverse=True)
    print("\nTop 10 por fuerza (att + def):")
    for tid, r in strength[:10]:
        print(f"  {tid}  att {r['att']:+.3f}  def {r['def']:+.3f}")


if __name__ == "__main__":
    main()
