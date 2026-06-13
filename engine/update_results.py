"""Actualiza data/results.json con los partidos del Mundial 2026 ya jugados,
leyendo la recopilación pública martj42/international_results (sin clave de API).

Solo añade partidos de la FASE DE GRUPOS (ambos equipos en el mismo grupo):
las eliminatorias reales se tratarán aparte. Nunca borra ni modifica entradas
existentes; si el dataset contradice un marcador ya fijado, lo avisa y respeta
lo local. El dataset suele actualizarse con horas o algún día de retraso:
para resultados al minuto, añade el partido a mano y este script lo respetará.

Uso:  python engine/update_results.py [--no-download]
Después de añadir partidos: python engine/simulate.py
"""

import argparse
import csv
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from train import ALIASES

URL = ("https://raw.githubusercontent.com/martj42/international_results/"
       "master/results.csv")
ROOT = Path(__file__).resolve().parent.parent

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-download", action="store_true",
                    help="usa el CSV local sin descargar la última versión")
    args = ap.parse_args()

    csv_path = ROOT / "data" / "international_results.csv"
    if not args.no_download:
        print("Descargando el histórico actualizado...")
        urllib.request.urlretrieve(URL, csv_path)

    name2id = {nm: tid for tid, names in ALIASES.items() for nm in names}
    teams = json.loads((ROOT / "data" / "teams.json").read_text(encoding="utf-8"))
    group_of = {t["id"]: t["group"] for t in teams["teams"]}

    res_path = ROOT / "data" / "results.json"
    data = json.loads(res_path.read_text(encoding="utf-8"))
    have = {(r["home"], r["away"]): r["score"] for r in data["results"]}
    have.update({(a, h): s[::-1] for (h, a), s in list(have.items())})

    added, conflicts = [], []
    with open(csv_path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["tournament"] != "FIFA World Cup" or r["date"] < "2026-06-01":
                continue
            if r["home_score"] in ("NA", "") or r["away_score"] in ("NA", ""):
                continue                      # aún sin marcador en el dataset
            h = name2id.get(r["home_team"])
            a = name2id.get(r["away_team"])
            if h is None or a is None or group_of[h] != group_of[a]:
                continue                      # eliminatorias o equipo no mapeado
            score = [int(float(r["home_score"])), int(float(r["away_score"]))]
            if (h, a) in have:
                if list(have[(h, a)]) != score:
                    conflicts.append((r["date"], h, a, have[(h, a)], score))
            else:
                added.append({"date": r["date"], "home": h, "away": a,
                              "score": score})

    for c in conflicts:
        print(f"AVISO conflicto {c[0]} {c[1]}-{c[2]}: "
              f"local {c[3]} vs dataset {c[4]} (se mantiene el local)")
    if added:
        data["results"].extend(added)
        data["results"].sort(key=lambda x: (x["date"], x["home"]))
        res_path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        for m in added:
            print(f"+ {m['date']} {m['home']} {m['score'][0]}-{m['score'][1]} {m['away']}")
        print(f"{len(added)} partido(s) añadidos. Ejecuta: python engine/simulate.py")
    else:
        print("Sin partidos nuevos en el dataset "
              f"({len(data['results'])} ya fijados localmente).")


if __name__ == "__main__":
    main()
