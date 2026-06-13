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
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "https://api.football-data.org/v4/competitions/WC/matches"

# La API usa el mismo código de 3 letras que los ids de teams.json salvo
# estas excepciones.
TLA_ALIASES = {"URY": "URU"}

# Fases eliminatorias de la API que sí están en nuestro cuadro (73-104). Se
# omite THIRD_PLACE: no se modela (no afecta a la probabilidad de campeón).
KO_STAGES = {"LAST_32", "LAST_16", "QUARTER_FINALS", "SEMI_FINALS", "FINAL"}

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


def write_fixtures(matches, ids):
    """Escribe docs/fixtures.json con TODOS los partidos (jugados y pendientes)
    para la página de calendario. Equipos como id de teams.json (o null si el
    cruce aún no tiene rival), grupo sin el prefijo, marcador si lo hay."""
    out = []
    for m in matches:
        ft = m.get("score", {}).get("fullTime", {})
        score = ([int(ft["home"]), int(ft["away"])]
                 if ft.get("home") is not None and ft.get("away") is not None
                 else None)
        def tid(side):
            t = TLA_ALIASES.get(m[side].get("tla"), m[side].get("tla"))
            return t if t in ids else None
        grp = m.get("group")
        out.append({
            "date": m.get("utcDate"),
            "stage": m.get("stage"),
            "group": grp.replace("GROUP_", "") if grp else None,
            "status": m.get("status"),
            "home": tid("homeTeam"),
            "away": tid("awayTeam"),
            "score": score,
        })
    out.sort(key=lambda x: x["date"] or "")
    path = ROOT / "docs" / "fixtures.json"
    path.write_text(json.dumps(
        {"updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
         "matches": out}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Calendario actualizado: {len(out)} partidos -> {path}")


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
    data.setdefault("knockout", [])
    have = {(r["home"], r["away"]): r["score"] for r in data["results"]}
    have.update({(a, h): s[::-1] for (h, a), s in list(have.items())})
    have_ko = {frozenset((r["home"], r["away"])) for r in data["knockout"]}

    def ids_of(m):
        """Devuelve (home_id, away_id, tla_crudos) o None si falta o no mapea."""
        ht, at = m["homeTeam"].get("tla"), m["awayTeam"].get("tla")
        h, a = TLA_ALIASES.get(ht, ht), TLA_ALIASES.get(at, at)
        return h, a, (ht, at)

    matches = fetch_matches(token)
    write_fixtures(matches, ids)            # calendario completo (siempre fresco)

    added, ko_added, conflicts, unknown = [], [], [], set()
    for m in matches:
        stage, status = m.get("stage"), m.get("status")
        if status != "FINISHED":
            continue
        ft = m["score"]["fullTime"]
        if ft.get("home") is None or ft.get("away") is None:
            continue
        h, a, (ht, at) = ids_of(m)
        if h not in ids or a not in ids:
            unknown.update(t for t in (ht, at)
                           if TLA_ALIASES.get(t, t) not in ids and t)
            continue
        date = m["utcDate"][:10]
        score = [int(ft["home"]), int(ft["away"])]

        if stage == "GROUP_STAGE":
            if group_of[h] != group_of[a]:
                continue                      # por seguridad: solo mismo grupo
            if (h, a) in have:
                if list(have[(h, a)]) != score:
                    conflicts.append((date, h, a, have[(h, a)], score))
            else:
                added.append({"date": date, "home": h, "away": a, "score": score})

        elif stage in KO_STAGES:
            w = m["score"].get("winner")      # HOME_TEAM / AWAY_TEAM (resuelto)
            winner = h if w == "HOME_TEAM" else a if w == "AWAY_TEAM" else None
            if winner is None:                # empate sin ganador definido: revisar
                print(f"AVISO eliminatoria {date} {h}-{a} sin ganador en la API "
                      f"(winner={w}); se omite hasta verificar.")
                continue
            if frozenset((h, a)) not in have_ko:
                ko_added.append({"date": date, "stage": stage, "home": h,
                                 "away": a, "score": score, "winner": winner})

    if unknown:
        print(f"AVISO equipos sin mapear (ignorados): {sorted(unknown)}")
    for c in conflicts:
        print(f"AVISO conflicto {c[0]} {c[1]}-{c[2]}: "
              f"local {c[3]} vs API {c[4]} (se mantiene el local)")

    if added:
        data["results"].extend(added)
        data["results"].sort(key=lambda x: (x["date"], x["home"]))
    if ko_added:
        data["knockout"].extend(ko_added)
        data["knockout"].sort(key=lambda x: (x["date"], x["home"]))

    if added or ko_added:
        res_path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        for m in added:
            print(f"+ grupo {m['date']} {m['home']} {m['score'][0]}-{m['score'][1]} {m['away']}")
        for m in ko_added:
            print(f"+ {m['stage']} {m['date']} {m['home']} {m['score'][0]}-{m['score'][1]} "
                  f"{m['away']} (pasa {m['winner']})")
        print(f"{len(added)+len(ko_added)} partido(s) nuevos. Ejecuta: python engine/simulate.py")
    else:
        print(f"Sin partidos nuevos ({len(data['results'])} de grupos y "
              f"{len(data['knockout'])} de eliminatorias ya fijados).")


if __name__ == "__main__":
    main()
