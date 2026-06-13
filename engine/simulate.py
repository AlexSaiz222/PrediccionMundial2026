"""Corre N simulaciones Monte Carlo del Mundial 2026 y escribe docs/data.json.

Uso:  python engine/simulate.py [--sims 20000] [--seed 42]

Flujo diario: añadir los partidos jugados a data/results.json y re-ejecutar.
"""

import argparse
import json
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from model import PARAMS
from tournament import (BRACKET, GROUPS, best_thirds, group_fixtures,
                        new_tallies, play_groups, simulate_tournament)

ROOT = Path(__file__).resolve().parent.parent
MILESTONES = ["r32", "r16", "qf", "sf", "final", "champion", "win_group"]
KO_ROUNDS = ["r32", "r16", "qf", "sf", "final"]
TOURNAMENT_EVE = "2026-06-10"   # víspera del torneo: etiqueta de la foto de salida


def serialize_ko(tallies, n):
    """Por cruce y lado, los ocupantes más probables: {id: [[tid, p], ...]}."""
    ko = {}
    for m, sides in tallies["slots"].items():
        out_sides = []
        for side in sides:
            top = sorted(side.items(), key=lambda kv: -kv[1])[:6]
            out_sides.append([[tid, round(c / n, 4)] for tid, c in top
                              if c / n >= 0.01] or
                             [[tid, round(c / n, 4)] for tid, c in top[:1]])
        ko[str(m)] = out_sides
    return ko


def serialize_paths(tallies, n):
    """Por equipo y ronda, sus 3 rivales más probables con p(cruce) y p(gana)."""
    paths = {}
    for tid, rounds in tallies["meet"].items():
        paths[tid] = {}
        for rnd in KO_ROUNDS:
            if rnd not in rounds:
                continue
            top = sorted(rounds[rnd].items(), key=lambda kv: -kv[1])[:3]
            beats = tallies["beat"].get(tid, {}).get(rnd, {})
            paths[tid][rnd] = [
                [opp, round(c / n, 4), round(beats.get(opp, 0) / c, 3)]
                for opp, c in top if c / n >= 0.005
            ]
    return paths


def save_history(data, out_teams, day=None):
    """Foto al cierre de jornada en docs/snapshots/ y serie en docs/history.json.

    La foto se etiqueta con la fecha del último partido fijado (es la jornada
    cuyo cierre representa), no con el día en que se ejecuta: así re-ejecutar
    por la mañana siguiente actualiza la misma jornada en vez de crear otra.
    Sin resultados aún, se etiqueta con la víspera del torneo.
    """
    if day is None:
        day = (max(r["date"] for r in data["results"]) if data["results"]
               else TOURNAMENT_EVE)
    today = day
    snap_dir = ROOT / "docs" / "snapshots"
    snap_dir.mkdir(exist_ok=True)
    (snap_dir / f"{today}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    hist_path = ROOT / "docs" / "history.json"
    hist = (json.loads(hist_path.read_text(encoding="utf-8"))
            if hist_path.exists() else {"days": []})
    entry = {
        "date": today,
        "results": len(data["results"]),
        "champion": {t["id"]: t["probs"]["champion"] for t in out_teams},
    }
    hist["days"] = [d for d in hist["days"] if d["date"] != today] + [entry]
    hist["days"].sort(key=lambda d: d["date"])
    hist_path.write_text(json.dumps(hist, ensure_ascii=False, indent=1),
                         encoding="utf-8")
    return today, len(hist["days"])


def load_data():
    teams_raw = json.loads((ROOT / "data" / "teams.json").read_text(encoding="utf-8"))
    results_raw = json.loads((ROOT / "data" / "results.json").read_text(encoding="utf-8"))
    teams = {t["id"]: t for t in teams_raw["teams"]}

    # Fase 2: si hay ratings entrenados (engine/train.py), sustituyen al Elo.
    ratings_path = ROOT / "data" / "ratings.json"
    if ratings_path.exists():
        r = json.loads(ratings_path.read_text(encoding="utf-8"))
        for tid, t in teams.items():
            t["att"] = r["ratings"][tid]["att"]
            t["def"] = r["ratings"][tid]["def"]
        PARAMS["mode"] = "ratings"
        PARAMS["mu"] = r["mu"]
        PARAMS["home_adv"] = r["home_adv"]
        PARAMS["method"] = r["method"]          # informativo (lo muestra la web)
        PARAMS["n_train"] = r["n_matches"]
        print(f"Modo ratings: {r['method']} ({r['n_matches']} partidos)")
    else:
        print("Modo Elo (sin data/ratings.json; ejecuta engine/train.py para fase 2)")
    group_members = {g: [t["id"] for t in teams_raw["teams"] if t["group"] == g]
                     for g in GROUPS}

    fixed = {}
    for r in results_raw["results"]:
        a, b = r["home"], r["away"]
        if a not in teams or b not in teams:
            raise SystemExit(f"results.json: equipo desconocido en {a} vs {b}")
        if teams[a]["group"] != teams[b]["group"]:
            raise SystemExit(f"results.json: {a} y {b} no comparten grupo")
        fixed[(a, b)] = tuple(r["score"])
        fixed[(b, a)] = tuple(reversed(r["score"]))

    # Eliminatorias ya jugadas: se fija el ganador (clave = pareja de equipos).
    knockout = results_raw.get("knockout", [])
    fixed_ko = {}
    for r in knockout:
        a, b, w = r["home"], r["away"], r["winner"]
        if a not in teams or b not in teams:
            raise SystemExit(f"knockout: equipo desconocido en {a} vs {b}")
        if w != a and w != b:
            raise SystemExit(f"knockout: ganador {w} no es ni {a} ni {b}")
        fixed_ko[frozenset((a, b))] = w

    return teams, group_members, fixed, fixed_ko, results_raw["results"], knockout


def real_standings(teams, group_members, results):
    """Clasificación actual de cada grupo SOLO con resultados reales."""
    stats = {tid: {"pj": 0, "pts": 0, "gf": 0, "ga": 0} for tid in teams}
    for r in results:
        a, b, (ga, gb) = r["home"], r["away"], r["score"]
        stats[a]["pj"] += 1; stats[b]["pj"] += 1
        stats[a]["gf"] += ga; stats[a]["ga"] += gb
        stats[b]["gf"] += gb; stats[b]["ga"] += ga
        if ga > gb:
            stats[a]["pts"] += 3
        elif gb > ga:
            stats[b]["pts"] += 3
        else:
            stats[a]["pts"] += 1; stats[b]["pts"] += 1
    order = {}
    for g in GROUPS:
        ids = sorted(group_members[g],
                     key=lambda t: (stats[t]["pts"],
                                    stats[t]["gf"] - stats[t]["ga"],
                                    stats[t]["gf"]),
                     reverse=True)
        order[g] = ids
    return order, stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sims", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--snapshot-date", default=None, metavar="AAAA-MM-DD",
                    help="fecha la foto del historial en un día concreto "
                         "(para reconstruir jornadas pasadas)")
    args = ap.parse_args()

    teams, group_members, fixed, fixed_ko, results, knockout = load_data()
    fixtures = group_fixtures(group_members)
    rng = random.Random(args.seed)
    counter = {tid: dict.fromkeys(MILESTONES, 0) for tid in teams}
    tallies = new_tallies()

    t0 = time.time()
    for _ in range(args.sims):
        simulate_tournament(teams, group_members, fixtures, fixed, rng,
                            counter, tallies, fixed_ko=fixed_ko)
    elapsed = time.time() - t0

    order, stats = real_standings(teams, group_members, results)
    n = args.sims
    out_teams = []
    for tid, t in teams.items():
        probs = {m: round(counter[tid][m] / n, 4) for m in MILESTONES}
        out_teams.append({**t, "probs": probs, "real": stats[tid]})
    out_teams.sort(key=lambda t: (-t["probs"]["champion"], -t["probs"]["final"],
                                  -t["probs"]["sf"], t["name"]))

    updated = (args.snapshot_date + "T22:00:00+00:00" if args.snapshot_date
               else datetime.now(timezone.utc).isoformat(timespec="seconds"))
    data = {
        "updated": updated,
        "sims": n,
        "params": PARAMS,
        "bracket": {k: ({str(m): v for m, v in d.items()} if isinstance(d, dict) else d)
                    for k, d in BRACKET.items()},
        "groups": order,
        "results": results,
        "knockout": knockout,
        "teams": out_teams,
        "ko": serialize_ko(tallies, n),
        "paths": serialize_paths(tallies, n),
    }
    out_path = ROOT / "docs" / "data.json"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    today, n_days = save_history(data, out_teams, args.snapshot_date)

    print(f"{n} simulaciones en {elapsed:.1f}s -> {out_path}")
    print(f"Foto del día guardada ({today}); historial con {n_days} día(s)")
    print("\nTop 8 favoritos:")
    for t in out_teams[:8]:
        print(f"  {t['name']:<16} campeón {t['probs']['champion']*100:5.1f}%  "
              f"final {t['probs']['final']*100:5.1f}%  "
              f"1º grupo {t['probs']['win_group']*100:5.1f}%")


if __name__ == "__main__":
    main()
