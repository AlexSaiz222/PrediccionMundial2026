"""Reglas del Mundial 2026 (48 equipos) y simulación de una edición completa.

Fase de grupos: 12 grupos de 4 (A..L), round-robin. Avanzan 1º, 2º y los 8
mejores terceros. Desempate simplificado: puntos > dif. goles > goles a favor
> azar (se omite el head-to-head completo de FIFA; impacto marginal).

Eliminatorias: cuadro oficial FIFA, partidos 73-104. Los terceros se asignan
a sus huecos permitidos (tabla de contingencia FIFA) por backtracking.
"""

from model import sim_group_match, sim_knockout_match

GROUPS = "ABCDEFGHIJKL"

# Dieciseisavos oficiales. ("1A" = ganador del grupo A, "2A" = segundo,
# "T74" = tercero asignado al hueco del partido 74.)
R32 = {
    73: ("2A", "2B"), 74: ("1E", "T74"), 75: ("1F", "2C"), 76: ("1C", "2F"),
    77: ("1I", "T77"), 78: ("2E", "2I"), 79: ("1A", "T79"), 80: ("1L", "T80"),
    81: ("1D", "T81"), 82: ("1G", "T82"), 83: ("2K", "2L"), 84: ("1H", "2J"),
    85: ("1B", "T85"), 86: ("1J", "2H"), 87: ("1K", "T87"), 88: ("2D", "2G"),
}

# Grupos admisibles en cada hueco de tercero (reglamento FIFA).
THIRD_SLOTS = {
    74: "ABCDF", 77: "CDFGH", 79: "CEFHI", 80: "EHIJK",
    81: "BEFIJ", 82: "AEHIJ", 85: "EFGIJ", 87: "DEIJL",
}

# Rondas siguientes: id de partido -> (partido_local, partido_visitante).
R16 = {89: (74, 77), 90: (73, 75), 91: (76, 78), 92: (79, 80),
       93: (83, 84), 94: (81, 82), 95: (86, 88), 96: (85, 87)}
QF = {97: (89, 90), 98: (93, 94), 99: (91, 92), 100: (95, 96)}
SF = {101: (97, 98), 102: (99, 100)}
FINAL = {104: (101, 102)}

# Estructura completa exportable (la usa también el simulador JS).
BRACKET = {"R32": R32, "THIRD_SLOTS": THIRD_SLOTS, "R16": R16,
           "QF": QF, "SF": SF, "FINAL": FINAL}


def group_fixtures(group_members):
    """Los 6 emparejamientos de cada grupo: [(grupo, id_a, id_b), ...]."""
    fixtures = []
    for g in GROUPS:
        ids = group_members[g]
        for i in range(4):
            for j in range(i + 1, 4):
                fixtures.append((g, ids[i], ids[j]))
    return fixtures


def play_groups(teams, group_members, fixtures, fixed_results, rng):
    """Juega la fase de grupos (respetando resultados reales fijados).

    group_members: {grupo: [ids]}. Devuelve {grupo: [ids ordenados 1º..4º]}
    y la tabla de stats por equipo.
    """
    stats = {tid: {"pts": 0, "gf": 0, "ga": 0} for tid in teams}
    for g, a, b in fixtures:
        key = (a, b)
        if key in fixed_results:
            ga, gb = fixed_results[key]
        else:
            ga, gb = sim_group_match(teams[a], teams[b], rng)
        stats[a]["gf"] += ga; stats[a]["ga"] += gb
        stats[b]["gf"] += gb; stats[b]["ga"] += ga
        if ga > gb:
            stats[a]["pts"] += 3
        elif gb > ga:
            stats[b]["pts"] += 3
        else:
            stats[a]["pts"] += 1; stats[b]["pts"] += 1

    standings = {}
    for g in GROUPS:
        ids = list(group_members[g])
        ids.sort(key=lambda t: (stats[t]["pts"], stats[t]["gf"] - stats[t]["ga"],
                                stats[t]["gf"], rng.random()), reverse=True)
        standings[g] = ids
    return standings, stats


def best_thirds(standings, stats, rng):
    """Los 8 mejores terceros, mismo criterio de orden que en los grupos."""
    thirds = [(g, standings[g][2]) for g in GROUPS]
    thirds.sort(key=lambda gt: (stats[gt[1]]["pts"],
                                stats[gt[1]]["gf"] - stats[gt[1]]["ga"],
                                stats[gt[1]]["gf"], rng.random()), reverse=True)
    return thirds[:8]  # [(grupo, id_equipo), ...]


def assign_thirds(qualified_thirds):
    """Asigna cada tercero clasificado a un hueco admisible (backtracking).

    qualified_thirds: [(grupo, id)] -> {match_id: id_equipo}
    """
    slots = sorted(THIRD_SLOTS,
                   key=lambda m: sum(1 for g, _ in qualified_thirds
                                     if g in THIRD_SLOTS[m]))
    assignment, used = {}, set()

    def backtrack(i):
        if i == len(slots):
            return True
        m = slots[i]
        for g, tid in qualified_thirds:
            if g in THIRD_SLOTS[m] and tid not in used:
                assignment[m] = tid
                used.add(tid)
                if backtrack(i + 1):
                    return True
                del assignment[m]
                used.discard(tid)
        return False

    if not backtrack(0):  # no debería ocurrir con la tabla FIFA; red de seguridad
        assignment.clear(); used.clear()
        rest = [tid for _, tid in qualified_thirds]
        for m in slots:
            assignment[m] = rest.pop()
    return assignment


def new_tallies():
    """Acumuladores opcionales para el cuadro y los caminos por selección."""
    ko_matches = list(R32) + list(R16) + list(QF) + list(SF) + list(FINAL)
    return {
        "slots": {m: ({}, {}) for m in ko_matches},  # ocupantes de cada lado
        "meet": {},   # meet[tid][ronda][rival] = veces que se cruzan
        "beat": {},   # beat[tid][ronda][rival] = veces que tid gana ese cruce
    }


def _record_ko(tallies, match_id, rnd, a, b, a_wins):
    sa, sb = tallies["slots"][match_id]
    sa[a] = sa.get(a, 0) + 1
    sb[b] = sb.get(b, 0) + 1
    for tid, rival, won in ((a, b, a_wins), (b, a, not a_wins)):
        d = tallies["meet"].setdefault(tid, {}).setdefault(rnd, {})
        d[rival] = d.get(rival, 0) + 1
        if won:
            dw = tallies["beat"].setdefault(tid, {}).setdefault(rnd, {})
            dw[rival] = dw.get(rival, 0) + 1


def simulate_tournament(teams, group_members, fixtures, fixed_results, rng,
                        counter, tallies=None):
    """Una edición completa del Mundial; acumula hitos por equipo en counter."""
    standings, stats = play_groups(teams, group_members, fixtures,
                                   fixed_results, rng)
    thirds = best_thirds(standings, stats, rng)
    third_of = assign_thirds(thirds)

    qualified = set()
    for g in GROUPS:
        counter[standings[g][0]]["win_group"] += 1
        qualified.update(standings[g][:2])
    qualified.update(tid for _, tid in thirds)
    for tid in qualified:
        counter[tid]["r32"] += 1

    def resolve(slot):
        if slot[0] == "T":
            return third_of[int(slot[1:])]
        return standings[slot[1]][int(slot[0]) - 1]

    winners = {}
    for m, (sa, sb) in R32.items():
        a, b = resolve(sa), resolve(sb)
        a_wins = sim_knockout_match(teams[a], teams[b], rng)
        winners[m] = a if a_wins else b
        if tallies is not None:
            _record_ko(tallies, m, "r32", a, b, a_wins)

    for round_def, milestone in ((R16, "r16"), (QF, "qf"), (SF, "sf"),
                                 (FINAL, "final")):
        for m, (ma, mb) in round_def.items():
            a, b = winners[ma], winners[mb]
            counter[a][milestone] += 1
            counter[b][milestone] += 1
            a_wins = sim_knockout_match(teams[a], teams[b], rng)
            winners[m] = a if a_wins else b
            if tallies is not None:
                _record_ko(tallies, m, milestone, a, b, a_wins)

    counter[winners[104]]["champion"] += 1
