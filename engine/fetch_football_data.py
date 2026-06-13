"""Actualiza data/results.json con los partidos del Mundial 2026 ya jugados,
leyendo la API de football-data.org (competición WC). Pensado para correr de
forma desatendida (GitHub Actions) varias veces al día.

Como la versión basada en martj42, solo añade partidos de la FASE DE GRUPOS y
nunca borra ni modifica entradas existentes: si la API contradice un marcador
ya fijado a mano, lo avisa y respeta lo local.

El token NO va en el código. Se lee de la variable de entorno
FOOTBALL_DATA_TOKEN (un *secret* del repositorio) o del argumento --token.

Uso:  FOOTBALL_DATA_TOKEN=xxxx python engine/fetch_football_data.py
Después: python engine/simulate.py
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "https://api.football-data.org/v4/competitions/WC/matches"

# La API usa el mismo código de 3 letras que los ids de teams.json salvo
# estas excepciones.
TLA_ALIASES = {"URY": "URU"}

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")


def fetch_matches(token):
    req = urllib.request.Request(API, headers={"X-Auth-Token": token})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            left = resp.headers.get("X-Requests-Available-Minute")
            if left is not None:
                print(f"API OK (quedan {left} peticiones este minuto)")
            return json.loads(resp.read().decode("utf-8"))["matches"]
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise SystemExit("Límite de peticiones alcanzado (HTTP 429). "
                             "Reintenta más tarde.")
        raise SystemExit(f"Error HTTP {e.code} de la API: {e.reason}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", help="token de football-data.org "
                    "(por defecto, variable FOOTBALL_DATA_TOKEN)")
    args = ap.parse_args()

    token = args.token or os.environ.get("FOOTBALL_DATA_TOKEN")
    if not token:
        raise SystemExit("Falta el token: define FOOTBALL_DATA_TOKEN o usa --token.")

    teams = json.loads((ROOT / "data" / "teams.json").read_text(encoding="utf-8"))
    group_of = {t["id"]: t["group"] for t in teams["teams"]}
    ids = set(group_of)

    res_path = ROOT / "data" / "results.json"
    data = json.loads(res_path.read_text(encoding="utf-8"))
    have = {(r["home"], r["away"]): r["score"] for r in data["results"]}
    have.update({(a, h): s[::-1] for (h, a), s in list(have.items())})

    added, conflicts, unknown = [], [], set()
    for m in fetch_matches(token):
        if m.get("stage") != "GROUP_STAGE" or m.get("status") != "FINISHED":
            continue
        ft = m["score"]["fullTime"]
        if ft.get("home") is None or ft.get("away") is None:
            continue
        ht, at = m["homeTeam"].get("tla"), m["awayTeam"].get("tla")
        h = TLA_ALIASES.get(ht, ht)
        a = TLA_ALIASES.get(at, at)
        if h not in ids or a not in ids:
            unknown.update(t for t in (ht, at)
                           if TLA_ALIASES.get(t, t) not in ids and t)
            continue
        if group_of[h] != group_of[a]:
            continue                          # por seguridad: solo mismo grupo
        date = m["utcDate"][:10]
        score = [int(ft["home"]), int(ft["away"])]
        if (h, a) in have:
            if list(have[(h, a)]) != score:
                conflicts.append((date, h, a, have[(h, a)], score))
        else:
            added.append({"date": date, "home": h, "away": a, "score": score})

    if unknown:
        print(f"AVISO equipos sin mapear (ignorados): {sorted(unknown)}")
    for c in conflicts:
        print(f"AVISO conflicto {c[0]} {c[1]}-{c[2]}: "
              f"local {c[3]} vs API {c[4]} (se mantiene el local)")
    if added:
        data["results"].extend(added)
        data["results"].sort(key=lambda x: (x["date"], x["home"]))
        res_path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        for m in added:
            print(f"+ {m['date']} {m['home']} {m['score'][0]}-{m['score'][1]} {m['away']}")
        print(f"{len(added)} partido(s) nuevos. Ejecuta: python engine/simulate.py")
    else:
        print("Sin partidos nuevos "
              f"({len(data['results'])} ya fijados localmente).")


if __name__ == "__main__":
    main()
