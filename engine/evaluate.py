"""Post-mortem del modelo: ¿cuánto acertó realmente?

Compara lo que el modelo predijo con lo que pasó y escribe docs/evaluacion.json,
que consume la web. Tres bloques independientes:

1. CAMPEÓN. La distribución de la víspera (snapshot 2026-06-10) frente al
   ganador real, con Brier multiclase y log-loss.
2. PARTIDOS. Probabilidad analítica (no simulada) de cada uno de los 103
   partidos del cuadro: 1X2 para los 72 de grupos, y probabilidad de pasar la
   eliminatoria para los 31 cruces. El tercer puesto queda fuera, como en el
   resto del proyecto: no se modela.
3. RONDAS. Para cada hito (octavos, cuartos...), la probabilidad que el modelo
   daba la víspera a cada selección de llegar, frente a si llegó.

Cada bloque se compara contra baselines honestos: uniforme para los partidos y
climatología (la tasa base de la ronda) para los hitos. Sin baseline, un Brier
suelto no dice nada.

Uso:  python engine/evaluate.py
"""

import json
import math
import sys
from pathlib import Path

from model import PARAMS, match_lambdas, strength_share
from simulate import load_data

ROOT = Path(__file__).resolve().parent.parent
EVE = "2026-06-10"                 # víspera: predicción sin ningún partido jugado
MAX_GOALS = 15                     # cola de la Poisson; sobra con lambda_max=3.6

# Hitos y cuántas selecciones de 48 los alcanzan (tasa base = baseline climático).
MILESTONES = [("r16", "Octavos", 16), ("qf", "Cuartos", 8),
              ("sf", "Semifinales", 4), ("final", "Final", 2),
              ("champion", "Campeón", 1)]

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")


def pmf(lam):
    """Vector de probabilidades Poisson(lam) para 0..MAX_GOALS, renormalizado."""
    out, term = [], math.exp(-lam)
    for k in range(MAX_GOALS + 1):
        out.append(term)
        term = term * lam / (k + 1)
    total = sum(out)
    return [p / total for p in out]


def result_probs(ta, tb):
    """(P gana A, P empate, P gana B) a 90 minutos, con Poisson independientes."""
    la, lb = match_lambdas(ta, tb)
    pa, pb = pmf(la), pmf(lb)
    win = sum(pa[i] * pb[j] for i in range(MAX_GOALS + 1) for j in range(i))
    draw = sum(pa[k] * pb[k] for k in range(MAX_GOALS + 1))
    return win, draw, 1.0 - win - draw


def tie_prob(ta, tb):
    """P(A supera la eliminatoria), replicando sim_knockout_match: 90' + prórroga
    (lambdas /3) + penaltis inclinados por pen_tilt."""
    w90, d90, _ = result_probs(ta, tb)
    la, lb = match_lambdas(ta, tb)
    pa, pb = pmf(la / 3.0), pmf(lb / 3.0)
    wet = sum(pa[i] * pb[j] for i in range(MAX_GOALS + 1) for j in range(i))
    det = sum(pa[k] * pb[k] for k in range(MAX_GOALS + 1))
    e = strength_share(ta, tb)
    pens = 0.5 + (e - 0.5) * PARAMS["pen_tilt"]
    return w90 + d90 * (wet + det * pens)


def logloss(p):
    return -math.log(max(p, 1e-12))


def evaluate_groups(teams, results):
    """1X2 de los 72 partidos de grupos. Brier multiclase (0..2) y log-loss."""
    rows, brier, ll, hits, b_brier, b_ll = [], 0.0, 0.0, 0, 0.0, 0.0
    for r in results:
        h, a = r["home"], r["away"]
        p = result_probs(teams[h], teams[a])
        gh, ga = r["score"]
        idx = 0 if gh > ga else 1 if gh == ga else 2
        y = [0.0, 0.0, 0.0]
        y[idx] = 1.0
        pick = max(range(3), key=lambda i: p[i])
        brier += sum((p[i] - y[i]) ** 2 for i in range(3))
        ll += logloss(p[idx])
        hits += pick == idx
        b_brier += sum((1 / 3 - y[i]) ** 2 for i in range(3))
        b_ll += logloss(1 / 3)
        rows.append({"date": r["date"], "stage": "GROUP_STAGE", "home": h,
                     "away": a, "score": r["score"],
                     "probs": [round(x, 4) for x in p],
                     "p_real": round(p[idx], 4), "hit": bool(pick == idx)})
    n = len(results)
    return rows, {"n": n, "brier": brier / n, "logloss": ll / n,
                  "accuracy": hits / n, "brier_baseline": b_brier / n,
                  "logloss_baseline": b_ll / n, "accuracy_baseline": 1 / 3}


def evaluate_knockout(teams, knockout):
    """Probabilidad de pasar cada cruce. Brier binario y log-loss."""
    rows, brier, ll, hits, b_brier, b_ll = [], 0.0, 0.0, 0, 0.0, 0.0
    for r in knockout:
        h, a, w = r["home"], r["away"], r["winner"]
        p_h = tie_prob(teams[h], teams[a])
        p_real = p_h if w == h else 1.0 - p_h
        brier += (p_real - 1.0) ** 2
        ll += logloss(p_real)
        hits += p_real >= 0.5
        b_brier += 0.25
        b_ll += logloss(0.5)
        rows.append({"date": r["date"], "stage": r["stage"], "home": h,
                     "away": a, "score": r["score"], "winner": w,
                     "p_home": round(p_h, 4), "p_real": round(p_real, 4),
                     "hit": bool(p_real >= 0.5)})
    n = len(knockout)
    return rows, {"n": n, "brier": brier / n, "logloss": ll / n,
                  "accuracy": hits / n, "brier_baseline": b_brier / n,
                  "logloss_baseline": b_ll / n, "accuracy_baseline": 0.5}


def reached_rounds(knockout):
    """Qué selecciones alcanzaron de verdad cada hito, desde las eliminatorias."""
    by_stage = {}
    for r in knockout:
        by_stage.setdefault(r["stage"], []).append(r)
    winners = lambda s: {r["winner"] for r in by_stage.get(s, [])}
    return {"r16": winners("LAST_32"), "qf": winners("LAST_16"),
            "sf": winners("QUARTER_FINALS"), "final": winners("SEMI_FINALS"),
            "champion": winners("FINAL")}


def evaluate_rounds(eve_teams, knockout):
    """Brier por hito frente al baseline climático (tasa base de la ronda)."""
    real = reached_rounds(knockout)
    n_teams = len(eve_teams)
    out = []
    for key, label, n_reach in MILESTONES:
        base = n_reach / n_teams
        brier = b_brier = 0.0
        for t in eve_teams:
            p = t["probs"][key]
            y = 1.0 if t["id"] in real[key] else 0.0
            brier += (p - y) ** 2
            b_brier += (base - y) ** 2
        out.append({"key": key, "label": label, "n_reach": n_reach,
                    "brier": brier / n_teams, "brier_baseline": b_brier / n_teams,
                    "base_rate": base})
    return out, real


def calibration(rows, bins=5):
    """Diagrama de fiabilidad: agrupa todas las probabilidades anunciadas en
    tramos y compara la media anunciada con la frecuencia observada. Si el
    modelo está bien calibrado, de lo que dice al 30% pasa ~el 30%."""
    obs = []
    for r in rows:
        if "probs" in r:                        # grupos: los tres sucesos 1X2
            gh, ga = r["score"]
            idx = 0 if gh > ga else 1 if gh == ga else 2
            obs += [(p, 1.0 if i == idx else 0.0) for i, p in enumerate(r["probs"])]
        else:                                   # cruces: el suceso "pasa el local"
            obs.append((r["p_home"], 1.0 if r["winner"] == r["home"] else 0.0))
    out = []
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        sel = [(p, y) for p, y in obs if (lo <= p < hi or (b == bins - 1 and p == 1))]
        if not sel:
            continue
        out.append({"lo": lo, "hi": hi, "n": len(sel),
                    "predicted": sum(p for p, _ in sel) / len(sel),
                    "observed": sum(y for _, y in sel) / len(sel)})
    return out


def main():
    teams, _, _, _, results, knockout = load_data()

    eve_path = ROOT / "docs" / "snapshots" / f"{EVE}.json"
    if not eve_path.exists():
        raise SystemExit(f"Falta el snapshot de la víspera: {eve_path}")
    eve_teams = json.loads(eve_path.read_text(encoding="utf-8"))["teams"]

    final = [r for r in knockout if r["stage"] == "FINAL"]
    if not final:
        raise SystemExit("No hay final en data/results.json: el torneo no está "
                         "completo, no tiene sentido evaluar.")
    champion = final[0]["winner"]

    # --- Bloque 1: campeón ---
    eve_probs = {t["id"]: t["probs"]["champion"] for t in eve_teams}
    ranking = sorted(eve_probs.items(), key=lambda kv: -kv[1])
    rank = [t for t, _ in ranking].index(champion) + 1
    n = len(eve_probs)
    champ_brier = sum((p - (1.0 if t == champion else 0.0)) ** 2
                      for t, p in eve_probs.items())
    unif = 1.0 / n
    champ_base = (unif - 1.0) ** 2 + (n - 1) * unif ** 2

    # --- Bloques 2 y 3 ---
    g_rows, g_stats = evaluate_groups(teams, results)
    k_rows, k_stats = evaluate_knockout(teams, knockout)
    r_stats, real = evaluate_rounds(eve_teams, knockout)

    all_rows = sorted(g_rows + k_rows, key=lambda r: (r["date"], r["home"]))

    # Ordenar por p_real a secas pone arriba todos los empates: el modelo nunca
    # pasa de ~34% de probabilidad de empate, así que un 0-0 siempre parece una
    # sorpresa aunque no lo sea. La sorpresa real es cuánto se equivocó respecto
    # a lo que sí anunciaba: p(su favorito) - p(lo que pasó).
    for r in all_rows:
        p_max = (max(r["probs"]) if "probs" in r
                 else max(r["p_home"], 1 - r["p_home"]))
        r["surprise"] = round(p_max - r["p_real"], 4)
    sorpresas = sorted(all_rows, key=lambda r: -r["surprise"])[:10]
    clavados = sorted(all_rows, key=lambda r: -r["p_real"])[:10]

    # El punto ciego: con Poisson independientes el empate nunca es el suceso
    # más probable, así que el modelo no predice ni un empate en todo el torneo.
    draws = [r for r in g_rows if r["score"][0] == r["score"][1]]
    decisive = [r for r in g_rows if r["score"][0] != r["score"][1]]
    blind = {
        "n_draws": len(draws),
        "n_group": len(g_rows),
        "draw_rate": len(draws) / len(g_rows),
        "max_draw_prob": max(r["probs"][1] for r in g_rows),
        "predicted_draws": sum(1 for r in g_rows
                               if max(range(3), key=lambda i: r["probs"][i]) == 1),
        "accuracy_decisive": sum(r["hit"] for r in decisive) / len(decisive),
    }

    out = {
        "champion": champion,
        "champion_eve_prob": eve_probs[champion],
        "champion_eve_rank": rank,
        "eve_top": [{"id": t, "p": round(p, 4)} for t, p in ranking[:10]],
        "champion_brier": champ_brier,
        "champion_brier_baseline": champ_base,
        "champion_logloss": logloss(eve_probs[champion]),
        "champion_logloss_baseline": logloss(unif),
        "groups": g_stats,
        "knockout": k_stats,
        "rounds": r_stats,
        "matches": all_rows,
        "biggest_upsets": sorpresas,
        "best_calls": clavados,
        "blind_spot": blind,
        "calibration": calibration(g_rows + k_rows),
        "reached": {k: sorted(v) for k, v in real.items()},
    }
    path = ROOT / "docs" / "evaluacion.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\nCampeón real: {champion} — la víspera tenía {eve_probs[champion]:.1%} "
          f"(favorito nº {rank} de {n})")
    print(f"  Brier campeón   {champ_brier:.4f}  (uniforme {champ_base:.4f})")
    print(f"  Log-loss        {logloss(eve_probs[champion]):.4f}  "
          f"(uniforme {logloss(unif):.4f})")
    for label, s in (("Grupos  ", g_stats), ("Cruces  ", k_stats)):
        print(f"\n{label} n={s['n']}  acierto {s['accuracy']:.1%} "
              f"(baseline {s['accuracy_baseline']:.1%})")
        print(f"           Brier {s['brier']:.4f} (baseline {s['brier_baseline']:.4f})"
              f"   log-loss {s['logloss']:.4f} (baseline {s['logloss_baseline']:.4f})")
    print("\nBrier por hito (víspera):")
    for r in r_stats:
        mejor = "mejor" if r["brier"] < r["brier_baseline"] else "PEOR"
        print(f"  {r['label']:12} {r['brier']:.4f}  vs climatología "
              f"{r['brier_baseline']:.4f}  -> {mejor}")
    print(f"\nPunto ciego: {blind['n_draws']} empates reales de {blind['n_group']} "
          f"({blind['draw_rate']:.1%}); el modelo predijo {blind['predicted_draws']} "
          f"(tope de prob. de empate: {blind['max_draw_prob']:.1%}). "
          f"Acierto en los NO empatados: {blind['accuracy_decisive']:.1%}")
    print("\nCalibración (anunciado -> observado):")
    for c in out["calibration"]:
        print(f"  {c['lo']:.0%}-{c['hi']:.0%}  n={c['n']:4}  "
              f"dijo {c['predicted']:.1%}  pasó {c['observed']:.1%}")
    print(f"\nEscrito {path}")


if __name__ == "__main__":
    main()
