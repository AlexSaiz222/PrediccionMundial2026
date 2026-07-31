/* Balance: carga evaluacion.json (métricas del post-mortem) + data.json (nombres
   y banderas) y pinta el veredicto, la tarjeta de resultados, la calibración,
   el acierto por ronda, el punto ciego y los extremos de sorpresa/acierto. */

"use strict";

const STAGE_LABELS = {
  GROUP_STAGE: "Grupos", LAST_32: "Dieciseisavos", LAST_16: "Octavos",
  QUARTER_FINALS: "Cuartos", SEMI_FINALS: "Semifinal", FINAL: "Final",
};

const $ = sel => document.querySelector(sel);
const pct = p => (p * 100).toFixed(p >= 0.095 ? 0 : 1).replace(".", ",") + "%";
// Para las cifras que se citan en titulares (11,7% y no 12%): siempre un decimal.
const pct1 = p => (p * 100).toFixed(1).replace(".", ",") + "%";
const num = (x, d = 4) => x.toFixed(d).replace(".", ",");
const fmtDate = iso => new Date(iso + "T12:00:00").toLocaleDateString("es",
  { day: "numeric", month: "long" });

let teams = {};

init();

async function init() {
  try {
    const [ev, data] = await Promise.all([
      fetch("evaluacion.json").then(r => r.json()),
      fetch("data.json").then(r => r.json()),
    ]);
    teams = Object.fromEntries(data.teams.map(t => [t.id, t]));
    render(ev);
  } catch (err) {
    $("#load-error").hidden = false;
    console.error(err);
  }
}

function name(id) { return teams[id] ? teams[id].name : id; }

function flag(id, cls = "flag") {
  const t = teams[id];
  return t
    ? `<img class="${cls}" src="https://flagcdn.com/w40/${t.flag}.png" alt=""
         width="40" height="27" loading="lazy">`
    : "";
}

function render(ev) {
  $("#updated").textContent = "Torneo finalizado el 19 de julio de 2026";
  renderVerdict(ev);
  renderScorecard(ev);
  renderCalibration(ev.calibration);
  renderRounds(ev.rounds);
  renderBlind(ev.blind_spot);
  renderRank("#upsets", ev.biggest_upsets, true);
  renderRank("#calls", ev.best_calls, false);
}

/* ---------- veredicto ---------- */

function renderVerdict(ev) {
  const c = ev.champion;
  const fin = ev.matches.find(m => m.stage === "FINAL");
  const sub = fin.home === c ? fin.away : fin.home;
  $("#verdict").innerHTML = `
    <div class="verdict-card verdict-main">
      <div class="vc-label">Campeona</div>
      <div class="vc-team">${flag(c, "flag flag-lg")}<strong>${name(c)}</strong></div>
      <div class="vc-sub">Ganó la final a ${name(sub)}
        (${fin.score[0]}–${fin.score[1]}) el ${fmtDate(fin.date)}</div>
    </div>
    <div class="verdict-card">
      <div class="vc-label">Probabilidad que le daba la víspera</div>
      <div class="vc-big">${pct1(ev.champion_eve_prob)}</div>
      <div class="vc-sub">antes de jugarse un solo partido</div>
    </div>
    <div class="verdict-card">
      <div class="vc-label">Puesto en el ranking del modelo</div>
      <div class="vc-big">${ev.champion_eve_rank}.º</div>
      <div class="vc-sub">de 48 selecciones</div>
    </div>`;

  const top = ev.eve_top.slice(0, 5)
    .map(t => `${name(t.id)} ${pct(t.p)}`).join(" · ");
  $("#verdict-note").innerHTML =
    `Así estaba el ranking del modelo la víspera: ${top}. Es decir, la campeona
     salía tercera y la finalista, primera: <strong>los dos finalistas eran el
     nº 1 y el nº 3</strong> de la lista. Acertar el campeón exacto con un
     ${pct1(ev.champion_eve_prob)} habría sido suerte; lo que sí se puede juzgar
     es si el reparto de probabilidades era razonable, y eso es lo que miden las
     secciones siguientes.`;
}

/* ---------- tarjeta de resultados ---------- */

function metricCard(title, hint, rows) {
  const body = rows.map(r => {
    const mejor = r.lowerIsBetter ? r.model < r.base : r.model > r.base;
    const delta = r.lowerIsBetter
      ? (r.base - r.model) / r.base
      : (r.model - r.base) / r.base;
    return `<tr>
      <th scope="row">${r.label}</th>
      <td class="mono">${r.fmt(r.model)}</td>
      <td class="mono dim">${r.fmt(r.base)}</td>
      <td class="mono ${mejor ? "better" : "worse"}">
        ${mejor ? "▼" : "▲"} ${Math.abs(delta * 100).toFixed(0)}%</td>
    </tr>`;
  }).join("");
  return `<div class="score-card">
    <h3>${title}</h3>
    <p class="score-hint">${hint}</p>
    <table class="score-table">
      <thead><tr><th></th><th>Modelo</th><th>Baseline</th><th>Mejora</th></tr></thead>
      <tbody>${body}</tbody>
    </table>
  </div>`;
}

function renderScorecard(ev) {
  const acc = { label: "Acierto", fmt: pct, lowerIsBetter: false };
  const bri = { label: "Brier score", fmt: x => num(x, 3), lowerIsBetter: true };
  const log = { label: "Log-loss", fmt: x => num(x, 3), lowerIsBetter: true };

  $("#scorecard").innerHTML = [
    metricCard("Campeón",
      "Una sola predicción, 48 resultados posibles. Baseline: dar 1/48 a cada una.",
      [{ ...bri, model: ev.champion_brier, base: ev.champion_brier_baseline },
       { ...log, model: ev.champion_logloss, base: ev.champion_logloss_baseline }]),
    metricCard(`Fase de grupos <span class="n">(${ev.groups.n} partidos)</span>`,
      "Victoria, empate o derrota. Baseline: un tercio a cada opción.",
      [{ ...acc, model: ev.groups.accuracy, base: ev.groups.accuracy_baseline },
       { ...bri, model: ev.groups.brier, base: ev.groups.brier_baseline },
       { ...log, model: ev.groups.logloss, base: ev.groups.logloss_baseline }]),
    metricCard(`Eliminatorias <span class="n">(${ev.knockout.n} cruces)</span>`,
      "Quién pasa, sin empate posible. Baseline: moneda al aire.",
      [{ ...acc, model: ev.knockout.accuracy, base: ev.knockout.accuracy_baseline },
       { ...bri, model: ev.knockout.brier, base: ev.knockout.brier_baseline },
       { ...log, model: ev.knockout.logloss, base: ev.knockout.logloss_baseline }]),
  ].join("");
}

/* ---------- calibración ---------- */

function renderCalibration(bins) {
  const rows = bins.map(b => {
    const p = b.predicted * 100, o = b.observed * 100;
    return `<div class="cal-row">
      <div class="cal-label">${(b.lo * 100).toFixed(0)}–${(b.hi * 100).toFixed(0)}%
        <span class="cal-n">n=${b.n}</span></div>
      <div class="cal-bars">
        <div class="cal-bar cal-pred" style="inline-size:${p}%">
          <span>dijo ${pct(b.predicted)}</span></div>
        <div class="cal-bar cal-obs" style="inline-size:${o}%">
          <span>pasó ${pct(b.observed)}</span></div>
      </div>
    </div>`;
  }).join("");
  $("#calibration").innerHTML = rows + `
    <div class="cal-legend">
      <span><i class="sw sw-pred"></i> lo que anunció el modelo</span>
      <span><i class="sw sw-obs"></i> lo que ocurrió de verdad</span>
    </div>`;
}

/* ---------- acierto por ronda ---------- */

function renderRounds(rounds) {
  $("#rounds-table tbody").innerHTML = rounds.map(r => {
    const mejora = (r.brier_baseline - r.brier) / r.brier_baseline;
    return `<tr>
      <th scope="row" class="sticky-col">${r.label}</th>
      <td class="mono">${r.n_reach} de 48</td>
      <td class="mono">${num(r.brier, 4)}</td>
      <td class="mono dim">${num(r.brier_baseline, 4)}</td>
      <td class="mono ${mejora > 0 ? "better" : "worse"}">
        ${mejora > 0 ? "▼" : "▲"} ${Math.abs(mejora * 100).toFixed(0)}%</td>
    </tr>`;
  }).join("");
}

/* ---------- punto ciego ---------- */

function renderBlind(b) {
  $("#blind").innerHTML = `
    <p><strong>El modelo no predijo ni un solo empate en todo el Mundial.</strong>
      No por casualidad: con dos Poisson independientes, la probabilidad de empate
      nunca sube de ${pct1(b.max_draw_prob)}, así que <em>nunca</em> puede ser el
      resultado más probable de un partido. Y sin embargo hubo
      <strong>${b.n_draws} empates en ${b.n_group} partidos</strong> de grupos
      (${pct(b.draw_rate)}).</p>
    <p>Eso pone su ${pct(b.accuracy_decisive)} de acierto en los partidos con
      ganador bajo una luz distinta: cuando el partido se decidía, el modelo
      elegía bien; su ${pct(1 - b.draw_rate)} de techo teórico en grupos venía
      dado de antemano. Corregirlo pide un término de correlación entre goles
      —lo que hace el ajuste de Dixon-Coles para marcadores bajos— o modelar el
      empate como suceso propio. Es la mejora más clara pendiente.</p>`;
}

/* ---------- rankings de partidos ---------- */

function renderRank(sel, rows, upset) {
  $(sel).innerHTML = rows.slice(0, 8).map(m => {
    const [gh, ga] = m.score;
    const win = gh > ga ? m.home : ga > gh ? m.away : null;
    const dicho = upset
      ? `el modelo le daba ${pct(m.p_real)} a este resultado`
      : `el modelo le daba ${pct(m.p_real)}`;
    return `<li class="rank-row">
      <div class="rank-head">
        <span class="rank-stage">${STAGE_LABELS[m.stage] || m.stage}</span>
        <span class="rank-date">${fmtDate(m.date)}</span>
      </div>
      <div class="rank-match">
        <span class="rank-team ${win === m.home ? "won" : ""}">
          ${flag(m.home, "flag flag-sm")} ${name(m.home)}</span>
        <span class="rank-score">${gh}–${ga}</span>
        <span class="rank-team ${win === m.away ? "won" : ""}">
          ${name(m.away)} ${flag(m.away, "flag flag-sm")}</span>
      </div>
      <div class="rank-prob ${upset ? "bad" : "good"}">${dicho}</div>
    </li>`;
  }).join("");
}
