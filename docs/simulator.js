/* Réplica en JS del motor Python (engine/model.py + tournament.py).
   Usa los MISMOS parámetros, exportados por simulate.py dentro de data.json,
   para que el "¿y si...?" sea coherente con los números publicados. */

"use strict";

const Simulator = (() => {

  function expectedScore(a, b, params) {
    let dr = a.elo - b.elo;
    if (a.host) dr += params.host_bonus;
    if (b.host) dr -= params.host_bonus;
    return 1 / (1 + Math.pow(10, -dr / 400));
  }

  function matchLambdas(a, b, params) {
    if (params.mode === "ratings") {
      const la = Math.exp(params.mu + a.att - b.def + (a.host ? params.home_adv : 0));
      const lb = Math.exp(params.mu + b.att - a.def + (b.host ? params.home_adv : 0));
      const clamp = x => Math.min(Math.max(x, params.lambda_min), params.lambda_max);
      return [clamp(la), clamp(lb)];
    }
    const e = expectedScore(a, b, params);
    let share = 0.5 + (e - 0.5) * params.share_damp;
    share = Math.min(Math.max(share, params.clamp_lo), params.clamp_hi);
    return [params.base_goals * share, params.base_goals * (1 - share)];
  }

  function strengthShare(a, b, params) {
    if (params.mode === "ratings") {
      const [la, lb] = matchLambdas(a, b, params);
      return la / (la + lb);
    }
    return expectedScore(a, b, params);
  }

  function poisson(lam) {
    const limit = Math.exp(-lam);
    let k = 0, p = Math.random();
    while (p > limit) { k++; p *= Math.random(); }
    return k;
  }

  function simKnockout(a, b, params) {  // true si gana A
    const [la, lb] = matchLambdas(a, b, params);
    let ga = poisson(la), gb = poisson(lb);
    if (ga !== gb) return ga > gb;
    ga = poisson(la / 3); gb = poisson(lb / 3);
    if (ga !== gb) return ga > gb;
    const e = strengthShare(a, b, params);
    return Math.random() < 0.5 + (e - 0.5) * params.pen_tilt;
  }

  // Asignación REAL de terceros a sus huecos, leída de los dieciseisavos ya
  // jugados (igual que engine/simulate.py::derive_forced_thirds). Evita que el
  // backtracking elija una permutación válida pero distinta de la oficial y
  // contradiga el cuadro publicado. data.groups ya viene ordenado 1º..4º real.
  // Devuelve {nºcasilla: id} solo si se resuelven las 8 casillas; si no, null.
  function deriveForcedThirds(data) {
    const R32 = data.bracket.R32, order = data.groups;
    const thirdSlots = {};
    for (const m in R32) if (R32[m][1][0] === "T") thirdSlots[m] = R32[m][0];
    const seedToSlot = {};
    for (const m in thirdSlots) {
      const seed = thirdSlots[m];               // p.ej. "1E"
      seedToSlot[order[seed[1]][Number(seed[0]) - 1]] = m;
    }
    const forced = {};
    for (const r of data.knockout || []) {
      if (r.stage !== "LAST_32") continue;
      if (seedToSlot[r.home] !== undefined) forced[seedToSlot[r.home]] = r.away;
      else if (seedToSlot[r.away] !== undefined) forced[seedToSlot[r.away]] = r.home;
    }
    return Object.keys(forced).length === Object.keys(thirdSlots).length ? forced : null;
  }

  // Asignación de terceros a huecos admisibles, por backtracking.
  function assignThirds(qualified, thirdSlots) {  // qualified: [[grupo, id]]
    const slots = Object.keys(thirdSlots).sort((m1, m2) => {
      const c = m => qualified.filter(([g]) => thirdSlots[m].includes(g)).length;
      return c(m1) - c(m2);
    });
    const assignment = {}, used = new Set();
    const backtrack = i => {
      if (i === slots.length) return true;
      const m = slots[i];
      for (const [g, tid] of qualified) {
        if (thirdSlots[m].includes(g) && !used.has(tid)) {
          assignment[m] = tid; used.add(tid);
          if (backtrack(i + 1)) return true;
          delete assignment[m]; used.delete(tid);
        }
      }
      return false;
    };
    if (!backtrack(0)) {
      const rest = qualified.map(([, tid]) => tid);
      for (const m of slots) assignment[m] = rest.pop();
    }
    return assignment;
  }

  /**
   * Corre nSims Mundiales y devuelve {probs, ko, paths} con la misma forma que
   * los campos homónimos de data.json (probs = {teamId: {r32,...,win_group}}).
   * data: el data.json completo. forced: Map "HOME|AWAY" -> [gh, ga] (se añade
   * a los resultados reales; los reales no se pueden sobrescribir).
   */
  function run(data, forced, nSims) {
    const params = data.params;
    const teams = {};
    for (const t of data.teams) teams[t.id] = t;
    const groups = Object.keys(data.groups);

    // resultados fijos: reales primero, luego los forzados que no choquen
    const fixed = new Map();
    for (const r of data.results) {
      fixed.set(r.home + "|" + r.away, r.score);
      fixed.set(r.away + "|" + r.home, [r.score[1], r.score[0]]);
    }
    for (const [key, score] of forced) {
      const [h, a] = key.split("|");
      if (!fixed.has(key)) {
        fixed.set(key, score);
        fixed.set(a + "|" + h, [score[1], score[0]]);
      }
    }

    const fixtures = [];
    for (const g of groups) {
      const ids = data.groups[g];
      for (let i = 0; i < 4; i++)
        for (let j = i + 1; j < 4; j++) fixtures.push([g, ids[i], ids[j]]);
    }

    const MILESTONES = ["r32", "r16", "qf", "sf", "final", "champion", "win_group"];
    const counter = {};
    for (const id in teams) {
      counter[id] = {};
      for (const m of MILESTONES) counter[id][m] = 0;
    }

    const { R32, THIRD_SLOTS, R16, QF, SF, FINAL } = data.bracket;

    // acumuladores extra: ocupantes de cada cruce y rivales por ronda
    const slots = {};
    for (const m of [R32, R16, QF, SF, FINAL].flatMap(Object.keys))
      slots[m] = [{}, {}];
    const meet = {}, beat = {};

    // eliminatorias reales ya jugadas: se fijan por pareja (como fixed_ko en
    // Python), y la asignación real de terceros a sus casillas.
    const fixedKo = new Map();
    for (const r of data.knockout || []) {
      fixedKo.set(r.home + "|" + r.away, r.winner);
      fixedKo.set(r.away + "|" + r.home, r.winner);
    }
    const koOutcome = (a, b) => {              // true si gana a
      const w = fixedKo.get(a + "|" + b);
      return w !== undefined ? w === a : simKnockout(teams[a], teams[b], params);
    };
    const forcedThirds = deriveForcedThirds(data);

    const recordKo = (m, rnd, a, b, aWins) => {
      slots[m][0][a] = (slots[m][0][a] || 0) + 1;
      slots[m][1][b] = (slots[m][1][b] || 0) + 1;
      for (const [tid, rival, won] of [[a, b, aWins], [b, a, !aWins]]) {
        const d = (meet[tid] ??= {})[rnd] ??= {};
        d[rival] = (d[rival] || 0) + 1;
        if (won) {
          const dw = (beat[tid] ??= {})[rnd] ??= {};
          dw[rival] = (dw[rival] || 0) + 1;
        }
      }
    };

    for (let s = 0; s < nSims; s++) {
      // --- fase de grupos ---
      const st = {};
      for (const id in teams) st[id] = { pts: 0, gf: 0, ga: 0 };
      for (const [, a, b] of fixtures) {
        let ga, gb;
        const f = fixed.get(a + "|" + b);
        if (f) { [ga, gb] = f; }
        else {
          const [la, lb] = matchLambdas(teams[a], teams[b], params);
          ga = poisson(la); gb = poisson(lb);
        }
        st[a].gf += ga; st[a].ga += gb; st[b].gf += gb; st[b].ga += ga;
        if (ga > gb) st[a].pts += 3;
        else if (gb > ga) st[b].pts += 3;
        else { st[a].pts++; st[b].pts++; }
      }
      const key = {};
      for (const id in teams)
        key[id] = st[id].pts * 1e6 + (st[id].gf - st[id].ga) * 1e3 +
          st[id].gf + Math.random();
      const standings = {};
      for (const g of groups)
        standings[g] = [...data.groups[g]].sort((x, y) => key[y] - key[x]);

      const thirds = groups.map(g => [g, standings[g][2]])
        .sort((x, y) => key[y[1]] - key[x[1]]).slice(0, 8);
      const thirdOf = forcedThirds || assignThirds(thirds, THIRD_SLOTS);
      const thirdIds = forcedThirds
        ? Object.values(forcedThirds) : thirds.map(([, tid]) => tid);

      for (const g of groups) {
        counter[standings[g][0]].win_group++;
        counter[standings[g][0]].r32++;
        counter[standings[g][1]].r32++;
      }
      for (const tid of thirdIds) counter[tid].r32++;

      const resolve = slot => slot[0] === "T"
        ? thirdOf[slot.slice(1)]
        : standings[slot[1]][Number(slot[0]) - 1];

      // --- eliminatorias ---
      const winners = {};
      for (const m in R32) {
        const [sa, sb] = R32[m];
        const a = resolve(sa), b = resolve(sb);
        const aWins = koOutcome(a, b);
        winners[m] = aWins ? a : b;
        recordKo(m, "r32", a, b, aWins);
      }
      const rounds = [[R16, "r16"], [QF, "qf"], [SF, "sf"], [FINAL, "final"]];
      for (const [def, milestone] of rounds) {
        for (const m in def) {
          const a = winners[def[m][0]], b = winners[def[m][1]];
          counter[a][milestone]++; counter[b][milestone]++;
          const aWins = koOutcome(a, b);
          winners[m] = aWins ? a : b;
          recordKo(m, milestone, a, b, aWins);
        }
      }
      counter[winners[104]].champion++;
    }

    const probs = {};
    for (const id in counter) {
      probs[id] = {};
      for (const m of MILESTONES) probs[id][m] = counter[id][m] / nSims;
    }

    // mismas formas que data.json (ver serialize_ko / serialize_paths en Python)
    const ko = {};
    for (const m in slots) {
      ko[m] = slots[m].map(side => {
        const top = Object.entries(side).sort((x, y) => y[1] - x[1]).slice(0, 6);
        const kept = top.filter(([, c]) => c / nSims >= 0.01);
        return (kept.length ? kept : top.slice(0, 1))
          .map(([tid, c]) => [tid, c / nSims]);
      });
    }
    const KO_ROUNDS = ["r32", "r16", "qf", "sf", "final"];
    const paths = {};
    for (const tid in meet) {
      paths[tid] = {};
      for (const rnd of KO_ROUNDS) {
        if (!meet[tid][rnd]) continue;
        const top = Object.entries(meet[tid][rnd])
          .sort((x, y) => y[1] - x[1]).slice(0, 3)
          .filter(([, c]) => c / nSims >= 0.005);
        paths[tid][rnd] = top.map(([opp, c]) =>
          [opp, c / nSims, ((beat[tid]?.[rnd]?.[opp]) || 0) / c]);
      }
    }
    return { probs, ko, paths };
  }

  return { run, matchLambdas };
})();
