/* Dashboard: carga data.json (o la foto de un día pasado vía ?dia=AAAA-MM-DD),
   pinta termómetro/grupos/cuadro/tabla, el cara a cara y el camino por
   selección, y gestiona el modo hipotético (re-simulación via simulator.js). */

"use strict";

const WHATIF_SIMS = 10000;
const ROUND_LABELS = {
  r32: "Dieciseisavos", r16: "Octavos", qf: "Cuartos",
  sf: "Semifinal", final: "Final", champion: "Campeón",
};
const state = {
  data: null,
  forced: new Map(),   // "HOME|AWAY" -> [gh, ga]
  probs: null,         // probs activas (oficiales o hipotéticas)
  ko: null,            // ocupantes de cada cruce (id partido -> [ladoA, ladoB])
  paths: null,         // rivales por ronda por equipo
  allRounds: false,    // tabla de rondas: false = solo las 24 primeras
};

const $ = sel => document.querySelector(sel);
const pct = p => (p * 100).toFixed(p >= 0.095 ? 0 : 1).replace(".", ",") + "%";
const flagImg = (t, cls = "flag") =>
  `<img class="${cls}" src="https://flagcdn.com/w40/${t.flag}.png" alt="" width="40" height="27" loading="lazy">`;
const fmtDate = iso => new Date(iso + "T12:00:00").toLocaleDateString("es",
  { day: "numeric", month: "long", year: "numeric" });

init();

async function init() {
  const dia = new URLSearchParams(location.search).get("dia");
  const snapshot = dia && /^\d{4}-\d{2}-\d{2}$/.test(dia) ? dia : null;
  if (!await fetchDay(snapshot)) {
    $("#load-error").hidden = false;
    return;
  }
  useOfficial();
  updateMeta(snapshot);

  renderAll();
  setupWhatIf();
  setupPathDialog();
  setupH2H();
  setupToc();
  setupTocCalendar(snapshot);
  $("#rounds-toggle").addEventListener("click", () => {
    state.allRounds = !state.allRounds;
    renderRoundsTable();
    if (!state.allRounds) $("#rondas").scrollIntoView({ block: "start" });
  });
  // atrás/adelante del navegador: misma carga en sitio, sin recargar la página
  window.addEventListener("popstate", () => {
    const d = new URLSearchParams(location.search).get("dia");
    loadDay(d && /^\d{4}-\d{2}-\d{2}$/.test(d) ? d : null);
  });
  // "Volver a la actual" del aviso, también sin recarga
  $("#snapshot-banner a").addEventListener("click", e => {
    e.preventDefault();
    history.pushState({}, "", "index.html");
    loadDay(null);
  });
}

/* descarga los datos del día indicado (o los actuales) en state.data */
async function fetchDay(dia) {
  try {
    // no-store: los datos cambian cada día y el navegador no debe cachearlos
    const res = await fetch(dia ? `snapshots/${dia}.json` : "data.json",
      { cache: "no-store" });
    if (!res.ok) throw new Error(res.statusText);
    state.data = await res.json();
    return true;
  } catch {
    return false;
  }
}

/* cabecera y pie: franja de jornada (altura constante para no desplazar
   el contenido al comparar días), fecha, nº de partidos, modelo */
function updateMeta(dia) {
  const banner = $("#snapshot-banner");
  if (dia) {
    $("#snapshot-msg").innerHTML =
      `Estás viendo la predicción al cierre del <strong>${fmtDate(dia)}</strong>.`;
    banner.classList.add("is-past");
    $("#snapshot-back").classList.remove("ghost");
  } else {
    $("#snapshot-msg").textContent = "Estás viendo la predicción más reciente.";
    banner.classList.remove("is-past");
    $("#snapshot-back").classList.add("ghost");
  }
  const d = new Date(state.data.updated);
  $("#updated").textContent = "Actualizado: " +
    d.toLocaleDateString("es", { day: "numeric", month: "long", year: "numeric" });
  $("#sims-count").textContent = state.data.sims.toLocaleString("es");
  $("#results-count").textContent =
    `${state.data.results.length} partidos reales fijados`;
  if (state.data.params.mode === "ratings") {
    $("#model-info").textContent =
      `la fuerza ofensiva y defensiva de cada selección se estima por máxima ` +
      `verosimilitud sobre ${state.data.params.n_train.toLocaleString("es")} ` +
      `partidos internacionales (modelo Dixon-Coles con decaimiento temporal, ` +
      `validado en los Mundiales 2018 y 2022)`;
  }
}

/* cambia de jornada en la misma página, con fundido suave (View Transitions) */
async function loadDay(dia) {
  if (!await fetchDay(dia)) return;      // datos descargados ANTES de la transición
  const apply = () => {
    state.forced.clear();
    $("#whatif-banner").hidden = true;
    useOfficial();
    updateMeta(dia);
    renderAll();
    const selA = $("#h2h-a");
    if (selA && selA.value) renderH2H(selA.value, $("#h2h-b").value);
  };
  if (document.startViewTransition) document.startViewTransition(apply);
  else apply();                          // sin soporte: cambio directo, sin animación
  const input = $("#toc-date");
  if (input) input.value = dia || input.max;
}

/* ---------- índice lateral con sección activa ---------- */
function setupToc() {
  const links = [...document.querySelectorAll(".toc a")];
  if (!links.length) return;
  const byId = new Map(links.map(a => [a.getAttribute("href").slice(1), a]));
  const setActive = id =>
    links.forEach(a => a.classList.toggle("active", a === byId.get(id)));
  const obs = new IntersectionObserver(entries => {
    for (const e of entries) if (e.isIntersecting) setActive(e.target.id);
  }, { rootMargin: "-18% 0px -72% 0px" });  // franja de lectura, ~20% desde arriba
  for (const id of byId.keys()) {
    const el = document.getElementById(id);
    if (el) obs.observe(el);
  }
  setActive(links[0].getAttribute("href").slice(1));
}

/* calendario del índice: salta a la predicción al cierre de la jornada elegida */
async function setupTocCalendar(currentDia) {
  const input = $("#toc-date");
  if (!input) return;
  let days;
  try {
    const h = await fetch("history.json", { cache: "no-store" })
      .then(r => { if (!r.ok) throw 0; return r.json(); });
    days = h.days.map(d => d.date);
  } catch { return; }                       // sin historial no hay calendario
  if (!days.length) return;
  const last = days[days.length - 1];
  input.min = days[0];
  input.max = last;
  input.value = currentDia && days.includes(currentDia) ? currentDia : last;
  input.addEventListener("change", () => {
    if (!input.value) return;
    // si el día elegido no tiene foto, usa la jornada anterior más cercana
    const pick = [...days].reverse().find(d => d <= input.value) || days[0];
    const target = pick === last ? null : pick;
    history.pushState({}, "", target ? `index.html?dia=${target}` : "index.html");
    loadDay(target);
  });
  $("#toc-cal").hidden = false;
}

function useOfficial() {
  const probs = {};
  for (const t of state.data.teams) probs[t.id] = t.probs;
  state.probs = probs;
  state.ko = state.data.ko || null;
  state.paths = state.data.paths || null;
}

function teamById(id) { return state.data.teams.find(t => t.id === id); }

function renderAll() {
  renderThermometer();
  renderGroups();
  renderBracket();
  renderRoundsTable();
}

/* ---------- termómetro de favoritos ---------- */
function renderThermometer() {
  const top = [...state.data.teams]
    .sort((a, b) => state.probs[b.id].champion - state.probs[a.id].champion)
    .slice(0, 12);
  const max = state.probs[top[0].id].champion || 1;
  $("#thermometer").innerHTML = top.map((t, i) => {
    const p = state.probs[t.id].champion;
    return `<li class="therm-row">
      <span class="rank">${i + 1}</span>
      ${flagImg(t)}
      <span class="name"><button class="team-btn" data-team="${t.id}">${t.name}</button></span>
      <div class="bar-track"><div class="bar-fill" style="inline-size:${(p / max) * 100}%"></div></div>
      <span class="pct">${pct(p)}</span>
    </li>`;
  }).join("");
}

/* ---------- tarjetas de grupos ---------- */
function renderGroups() {
  const html = Object.entries(state.data.groups).map(([g, ids]) => {
    const rows = ids.map(id => {
      const t = teamById(id), p = state.probs[id];
      return `<tr>
        <td class="team-cell">${flagImg(t)}<button class="team-btn" data-team="${t.id}">${t.name}</button></td>
        <td>${t.real.pj}</td><td><strong>${t.real.pts}</strong></td>
        <td class="prob-cell"><span class="prob-chip" style="--p:${p.win_group}">${pct(p.win_group)}</span></td>
        <td class="prob-cell"><span class="prob-chip" style="--p:${p.r32}">${pct(p.r32)}</span></td>
      </tr>`;
    }).join("");
    return `<div class="group-card">
      <h3>Grupo <strong>${g}</strong></h3>
      <table>
        <thead><tr><th>Selección</th><th>PJ</th><th>Pts</th><th>1º</th><th>Clasif.</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
  }).join("");
  $("#groups").innerHTML = html;
}

/* ---------- cuadro de eliminatorias ---------- */
function bracketColumns() {
  const { R32, R16, QF, SF, FINAL } = state.data.bracket;
  const feed = m => {                       // partidos que alimentan el cruce m
    for (const def of [R16, QF, SF, FINAL]) if (def[m]) return def[m];
    return null;
  };
  const expand = ids => ids.flatMap(m => feed(String(m)) || []);
  const sf = FINAL["104"];                  // [101, 102]
  const qf = expand(sf), r16 = expand(qf), r32 = expand(r16);
  return [
    { label: "Dieciseisavos", ids: r32, slots: R32 },
    { label: "Octavos", ids: r16 },
    { label: "Cuartos", ids: qf },
    { label: "Semifinales", ids: sf },
    { label: "Final", ids: [104], center: true },
  ];
}

function slotHTML(entries) {
  const [topId, topP] = entries[0];
  const t = teamById(topId);
  const locked = topP >= 0.9995;
  const tip = entries.map(([id, p]) =>
    `${teamById(id).name} ${pct(p)}`).join(", ");
  return `<div class="slot${locked ? " locked" : ""}" title="${tip}">
    ${flagImg(t)}<span class="nm">${t.name}</span>
    <span class="sp">${locked ? "fijo" : pct(topP)}</span>
  </div>`;
}

function renderBracket() {
  if (!state.ko) { $("#bracket-section").hidden = true; return; }
  $("#bracket-section").hidden = false;
  const cols = bracketColumns();
  // conectores por columna: clase de entrada (con la separación vertical entre
  // los dos cruces que alimentan la casilla) y de salida hacia la ronda siguiente
  const wiring = [
    ["", "out-r"], ["in-l v16", "out-r"], ["in-l v8", "out-r"],
    ["in-l v4", "out-r"], ["in-l v2", ""],
  ];
  $("#bracket").innerHTML = cols.map((col, ci) => {
    const cls = wiring[ci].filter(Boolean).join(" ");
    const boxes = col.ids.map(m => {
      const sides = state.ko[String(m)];
      if (!sides) return "";
      const fmtSlot = s => s[0] === "T" ? "3º" : `${s[0]}º ${s[1]}`;
      const label = col.slots
        ? `P${m} · ${fmtSlot(col.slots[String(m)][0])} vs ${fmtSlot(col.slots[String(m)][1])}`
        : `Partido ${m}`;
      return `<div class="match-box ${cls}${col.center ? " final-box" : ""}" title="${label}">
        ${slotHTML(sides[0])}${slotHTML(sides[1])}
        ${col.center ? championMini() : ""}
      </div>`;
    }).join("");
    return `<div class="bracket-col">
      <h3>${col.label}</h3>
      <div class="bracket-col-inner">${boxes}</div>
    </div>`;
  }).join("");
}

function championMini() {
  const top = [...state.data.teams]
    .sort((a, b) => state.probs[b.id].champion - state.probs[a.id].champion)
    .slice(0, 3);
  const rows = top.map(t => `<div class="slot">
    ${flagImg(t)}<span class="nm">${t.name}</span>
    <span class="sp">${pct(state.probs[t.id].champion)}</span>
  </div>`).join("");
  return `<div class="champ-mini">
    <div class="mlabel">Campeón más probable</div>${rows}
  </div>`;
}

/* ---------- tabla de rondas ---------- */
function renderRoundsTable() {
  const cols = ["r32", "r16", "qf", "sf", "final", "champion"];
  let teams = [...state.data.teams].sort((a, b) =>
    state.probs[b.id].champion - state.probs[a.id].champion ||
    state.probs[b.id].final - state.probs[a.id].final ||
    state.probs[b.id].r32 - state.probs[a.id].r32);
  const half = Math.ceil(teams.length / 2);
  $("#rounds-toggle").textContent = state.allRounds
    ? `Ver solo las ${half} primeras`
    : `Ver las ${teams.length} selecciones`;
  if (!state.allRounds) teams = teams.slice(0, half);
  $("#rounds-table tbody").innerHTML = teams.map(t => {
    const cells = cols.map(c => {
      const p = state.probs[t.id][c];
      const gold = c === "champion" ? " gold" : "";
      return `<td class="heat${gold}" style="--p:${p}">${pct(p)}</td>`;
    }).join("");
    return `<tr><td class="sticky-col team-cell">${flagImg(t)}<button class="team-btn" data-team="${t.id}">${t.name}</button></td>${cells}</tr>`;
  }).join("");
}

/* ---------- camino más probable por selección ---------- */
function setupPathDialog() {
  document.addEventListener("click", e => {
    const btn = e.target.closest(".team-btn");
    if (btn) openPath(btn.dataset.team);
  });
}

function openPath(tid) {
  if (!state.paths) return;
  const t = teamById(tid);
  $("#path-title").innerHTML = `${flagImg(t)} El camino de ${t.name}`;
  const path = state.paths[tid] || {};
  const rounds = ["r32", "r16", "qf", "sf", "final"];
  const rows = rounds.map(rnd => {
    const reach = state.probs[tid][rnd];
    let rivals = "";
    if (reach > 0 && path[rnd] && path[rnd].length) {
      rivals = path[rnd].map(([opp, pMeet, pBeat]) => {
        const o = teamById(opp);
        const cond = Math.min(pMeet / reach, 1);  // rival dado que juega la ronda
        return `<span class="rival" title="Si se cruzan, ${t.name} pasa el ${pct(pBeat)} de las veces">
          ${flagImg(o, "flag flag-sm")}${o.name} ${pct(cond)}</span>`;
      }).join(" ");
    } else if (reach === 0) {
      rivals = `<span class="muted">no llega en ninguna simulación</span>`;
    }
    return `<tr>
      <td>${ROUND_LABELS[rnd]}</td>
      <td class="num">${pct(reach)}</td>
      <td>${rivals}</td>
    </tr>`;
  }).join("");
  const champ = `<tr class="champ-row">
    <td>${ROUND_LABELS.champion}</td>
    <td class="num">${pct(state.probs[tid].champion)}</td><td></td>
  </tr>`;
  $("#path-body").innerHTML = `
    <table class="path-table">
      <thead><tr><th>Ronda</th><th class="num">Llega</th>
        <th>Rivales más probables (si juega esa ronda)</th></tr></thead>
      <tbody>${rows}${champ}</tbody>
    </table>
    <p class="hint">El porcentaje junto a cada rival es la frecuencia con la que aparece
      enfrente cuando ${t.name} disputa esa ronda; al pasar el cursor se ve con qué
      frecuencia supera ese cruce.</p>`;
  $("#path-dialog").showModal();
}

/* ---------- cara a cara ---------- */
function setupH2H() {
  const byName = [...state.data.teams].sort((a, b) =>
    a.name.localeCompare(b.name, "es"));
  const options = byName.map(t => `<option value="${t.id}">${t.name}</option>`).join("");
  const selA = $("#h2h-a"), selB = $("#h2h-b");
  selA.innerHTML = options; selB.innerHTML = options;
  const favs = [...state.data.teams].sort((a, b) =>
    state.probs[b.id].champion - state.probs[a.id].champion);
  selA.value = favs[0].id; selB.value = favs[1].id;

  const refresh = () => renderH2H(selA.value, selB.value);
  selA.addEventListener("change", refresh);
  selB.addEventListener("change", refresh);
  $("#h2h-swap").addEventListener("click", () => {
    [selA.value, selB.value] = [selB.value, selA.value];
    refresh();
  });
  refresh();
}

function poissonArr(lam, kmax = 10) {
  const arr = [Math.exp(-lam)];
  for (let k = 1; k <= kmax; k++) arr[k] = arr[k - 1] * lam / k;
  return arr;
}

function h2hStats(a, b, params) {
  const [la, lb] = Simulator.matchLambdas(a, b, params);
  const pa = poissonArr(la), pb = poissonArr(lb);
  let p1 = 0, px = 0, p2 = 0;
  const scores = [];
  for (let i = 0; i <= 10; i++) for (let j = 0; j <= 10; j++) {
    const p = pa[i] * pb[j];
    scores.push([i, j, p]);
    if (i > j) p1 += p; else if (i === j) px += p; else p2 += p;
  }
  const pae = poissonArr(la / 3), pbe = poissonArr(lb / 3);  // prórroga
  let e1 = 0, ex = 0, e2 = 0;
  for (let i = 0; i <= 10; i++) for (let j = 0; j <= 10; j++) {
    const p = pae[i] * pbe[j];
    if (i > j) e1 += p; else if (i === j) ex += p; else e2 += p;
  }
  const share = la / (la + lb);
  const pen = 0.5 + (share - 0.5) * params.pen_tilt;
  const ko = p1 + px * (e1 + ex * pen);
  scores.sort((x, y) => y[2] - x[2]);
  return { la, lb, p1, px, p2, ko, top: scores.slice(0, 5) };
}

function renderH2H(idA, idB) {
  const out = $("#h2h-out");
  if (idA === idB) {
    out.innerHTML = `<p class="hint">Elige dos selecciones distintas.</p>`;
    return;
  }
  const a = teamById(idA), b = teamById(idB);
  const s = h2hStats(a, b, state.data.params);
  const fmtG = x => x.toFixed(2).replace(".", ",");
  const chips = s.top.map(([i, j, p]) =>
    `<span class="score-chip">${i}-${j} <small>${pct(p)}</small></span>`).join("");
  const hostNote = a.host !== b.host
    ? `<p class="hint">${(a.host ? a : b).name} juega como anfitrión, así que el modelo
       le aplica su ventaja de local.</p>` : "";
  out.innerHTML = `
    <div class="h2h-card">
      <div class="h2h-names">
        <span class="h2h-team">${flagImg(a)} ${a.name}</span>
        <span class="h2h-vs">goles esperados ${fmtG(s.la)} a ${fmtG(s.lb)}</span>
        <span class="h2h-team h2h-right">${b.name} ${flagImg(b)}</span>
      </div>
      <div class="h2h-bar" role="img"
        aria-label="${a.name} gana ${pct(s.p1)}, empate ${pct(s.px)}, ${b.name} gana ${pct(s.p2)}">
        <div class="seg seg-a" style="inline-size:${s.p1 * 100}%"></div>
        <div class="seg seg-x" style="inline-size:${s.px * 100}%"></div>
        <div class="seg seg-b" style="inline-size:${s.p2 * 100}%"></div>
      </div>
      <div class="h2h-legend">
        <span><span class="dot dot-a"></span>Gana ${a.name} ${pct(s.p1)}</span>
        <span><span class="dot dot-x"></span>Empate ${pct(s.px)}</span>
        <span><span class="dot dot-b"></span>Gana ${b.name} ${pct(s.p2)}</span>
      </div>
      <p class="h2h-scores">Marcadores más probables: ${chips}</p>
      <p class="h2h-ko">Si fuera una eliminatoria (con prórroga y penaltis),
        ${a.name} pasaría el <strong>${pct(s.ko)}</strong> de las veces.</p>
      ${hostNote}
    </div>`;
}

/* ---------- modo ¿y si...? ---------- */
function setupWhatIf() {
  const dialog = $("#whatif-dialog");
  const groupSel = $("#whatif-group");
  groupSel.innerHTML = Object.keys(state.data.groups)
    .map(g => `<option value="${g}">Grupo ${g}</option>`).join("");

  $("#whatif-open").addEventListener("click", () => {
    renderWhatIfMatches(groupSel.value);
    dialog.showModal();
  });
  groupSel.addEventListener("change", () => renderWhatIfMatches(groupSel.value));
  $("#whatif-reset").addEventListener("click", () => {
    state.forced.clear();
    useOfficial();
    $("#whatif-banner").hidden = true;
    renderAll();
  });
}

function renderWhatIfMatches(g) {
  const ids = state.data.groups[g];
  const played = new Map(state.data.results.map(r => [r.home + "|" + r.away, r.score]));
  const items = [];
  for (let i = 0; i < 4; i++) for (let j = i + 1; j < 4; j++) {
    const a = teamById(ids[i]), b = teamById(ids[j]);
    let real = played.get(a.id + "|" + b.id);
    if (!real && played.has(b.id + "|" + a.id)) {
      const r = played.get(b.id + "|" + a.id);
      real = [r[1], r[0]];
    }
    const key = a.id + "|" + b.id;
    const forced = state.forced.get(key);
    if (real) {
      items.push(`<li class="match-row played">
        ${flagImg(a)} ${a.name} <span class="vs">vs</span> ${b.name} ${flagImg(b)}
        <span class="real-score">${real[0]}-${real[1]} · jugado</span>
      </li>`);
    } else {
      items.push(`<li class="match-row" data-key="${key}">
        ${flagImg(a)} ${a.name} <span class="vs">vs</span> ${b.name} ${flagImg(b)}
        <span class="score-inputs">
          <input type="number" min="0" max="9" value="${forced ? forced[0] : 1}" aria-label="Goles ${a.name}">
          <span class="vs">a</span>
          <input type="number" min="0" max="9" value="${forced ? forced[1] : 0}" aria-label="Goles ${b.name}">
          <button class="btn btn-small btn-accent" data-apply>${forced ? "Cambiar" : "Forzar"}</button>
        </span>
      </li>`);
    }
  }
  $("#whatif-matches").innerHTML = items.join("");
  $("#whatif-matches").querySelectorAll("[data-apply]").forEach(btn => {
    btn.addEventListener("click", () => {
      const row = btn.closest(".match-row");
      const [inA, inB] = row.querySelectorAll("input");
      state.forced.set(row.dataset.key,
        [Math.max(0, +inA.value || 0), Math.max(0, +inB.value || 0)]);
      runWhatIf();
      renderForcedChips();
      renderWhatIfMatches($("#whatif-group").value);
    });
  });
  renderForcedChips();
}

function renderForcedChips() {
  const box = $("#whatif-forced");
  box.innerHTML = [...state.forced.entries()].map(([key, score]) => {
    const [h, a] = key.split("|");
    return `<span class="forced-chip">${teamById(h).name} ${score[0]}-${score[1]} ${teamById(a).name}
      <button data-remove="${key}" aria-label="Quitar">×</button></span>`;
  }).join("");
  box.querySelectorAll("[data-remove]").forEach(btn => {
    btn.addEventListener("click", () => {
      state.forced.delete(btn.dataset.remove);
      if (state.forced.size) runWhatIf();
      else {
        useOfficial();
        $("#whatif-banner").hidden = true;
        renderAll();
      }
      renderForcedChips();
      renderWhatIfMatches($("#whatif-group").value);
    });
  });
}

function runWhatIf() {
  document.body.classList.add("simulating");
  // cede un frame para que se vea el estado "simulando" antes del cálculo
  requestAnimationFrame(() => setTimeout(() => {
    const res = Simulator.run(state.data, state.forced, WHATIF_SIMS);
    state.probs = res.probs;
    state.ko = res.ko;
    state.paths = res.paths;
    const n = state.forced.size;
    $("#whatif-desc").textContent =
      `${n} resultado${n > 1 ? "s" : ""} forzado${n > 1 ? "s" : ""} · ${WHATIF_SIMS.toLocaleString("es")} nuevas simulaciones`;
    $("#whatif-banner").hidden = false;
    renderAll();
    document.body.classList.remove("simulating");
  }, 16));
}
