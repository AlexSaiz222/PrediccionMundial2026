/* Calendario: lista todos los partidos (jugados y pendientes) agrupados por día.
   Fuente: fixtures.json (lo genera el robot desde football-data.org). Los nombres
   y banderas salen de data.json para ser coherentes con el resto del sitio. */
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];

const STAGE = {
  GROUP_STAGE: g => `Grupo ${g}`,
  LAST_32: () => "Dieciseisavos",
  LAST_16: () => "Octavos",
  QUARTER_FINALS: () => "Cuartos",
  SEMI_FINALS: () => "Semifinal",
  THIRD_PLACE: () => "Tercer puesto",
  FINAL: () => "Final",
};

const dayKey = d => d.toLocaleDateString("es-ES", { year: "numeric", month: "2-digit", day: "2-digit" });

let teams = {}, matches = [], filter = "all";

init();

async function init() {
  try {
    const [fx, data] = await Promise.all([
      fetch("fixtures.json", { cache: "no-store" }).then(r => { if (!r.ok) throw 0; return r.json(); }),
      fetch("data.json", { cache: "no-store" }).then(r => { if (!r.ok) throw 0; return r.json(); }),
    ]);
    matches = fx.matches;
    for (const t of data.teams) teams[t.id] = t;
  } catch { $("#load-error").hidden = false; return; }

  $$(".filter-btn").forEach(b => b.addEventListener("click", () => {
    filter = b.dataset.filter;
    $$(".filter-btn").forEach(x => x.classList.toggle("active", x === b));
    render();
  }));
  $("#jump-today").addEventListener("click", () => {
    const el = $("#cal-now");
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  });
  render();
}

const cap = s => s.charAt(0).toUpperCase() + s.slice(1);

function flag(id) {
  const t = teams[id];
  return t && t.flag
    ? `<img class="flag flag-sm" src="https://flagcdn.com/w40/${t.flag}.png" alt="" width="40" height="27" loading="lazy">`
    : "";
}
const sideName = id => id && teams[id] ? teams[id].name : (id || "Por determinar");

function matchRow(m) {
  const d = new Date(m.date);
  const time = d.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" });
  const tag = (STAGE[m.stage] || (() => m.stage))(m.group);
  const done = m.status === "FINISHED" && m.score;
  const [gh, ga] = m.score || [null, null];
  const hw = done && gh > ga, aw = done && ga > gh;
  const score = done
    ? `${gh}<span class="dash">–</span>${ga}`
    : `<span class="dash">–</span>`;
  return `<div class="cal-match${done ? " is-done" : ""}">
    <div class="cal-when"><span class="cal-time">${time}</span><span class="cal-tag">${tag}</span></div>
    <div class="cal-side cal-home${hw ? " win" : ""}"><span class="tn">${sideName(m.home)}</span>${flag(m.home)}</div>
    <div class="cal-score">${score}</div>
    <div class="cal-side cal-away${aw ? " win" : ""}">${flag(m.away)}<span class="tn">${sideName(m.away)}</span></div>
  </div>`;
}

function render() {
  const list = matches.filter(m =>
    filter === "all" ||
    (filter === "played" && m.status === "FINISHED") ||
    (filter === "pending" && m.status !== "FINISHED"));

  const byDay = new Map();
  for (const m of list) {
    const key = dayKey(new Date(m.date));
    (byDay.get(key) || byDay.set(key, []).get(key)).push(m);
  }

  const todayKey = dayKey(new Date());
  const today = new Date(); today.setHours(0, 0, 0, 0);
  let nowMarked = false;
  let html = "";
  for (const [key, dayMatches] of byDay) {
    const d0 = new Date(dayMatches[0].date);
    const label = cap(d0.toLocaleDateString("es-ES", { weekday: "long", day: "numeric", month: "long" }));
    const isToday = key === todayKey;
    // ancla "ahora": el día de hoy o, si no hay partidos hoy, el primero futuro.
    let anchor = "";
    const dDay = new Date(d0); dDay.setHours(0, 0, 0, 0);
    if (!nowMarked && dDay >= today) { anchor = ' id="cal-now"'; nowMarked = true; }
    const badge = isToday ? ' <span class="cal-hoy">Hoy</span>' : "";
    html += `<h2 class="cal-day${isToday ? " is-today" : ""}"${anchor}>${label}${badge}</h2>`;
    for (const m of dayMatches) html += matchRow(m);
  }
  $("#cal").innerHTML = html || `<p class="hint">No hay partidos para este filtro.</p>`;
  $("#jump-today").hidden = !nowMarked;
}
