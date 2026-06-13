/* Página de evolución: gráfica de probabilidad de campeón por jornada
   (SVG generado a mano, sin dependencias), movimientos de la última jornada
   y viaje en el tiempo hacia la predicción guardada de cualquier día. */

"use strict";

const PALETTE = ["#2e7d5b", "#b35642", "#4f6db8", "#a3812f",
                 "#7e6bbf", "#3f8fa3", "#b06183", "#6f7f3c"];

const pctTxt = p => (p * 100).toFixed(1).replace(".", ",") + "%";
const fmtShort = iso => new Date(iso + "T12:00:00")
  .toLocaleDateString("es", { day: "numeric", month: "short" });
const fmtLong = iso => new Date(iso + "T12:00:00")
  .toLocaleDateString("es", { day: "numeric", month: "long" });
const flagImg = t =>
  `<img class="flag flag-sm" src="https://flagcdn.com/w40/${t.flag}.png" alt="" width="40" height="27" loading="lazy">`;

init();

async function init() {
  let hist, data;
  try {
    // no-store: los datos cambian cada día y el navegador no debe cachearlos
    [hist, data] = await Promise.all([
      fetch("history.json", { cache: "no-store" })
        .then(r => { if (!r.ok) throw 0; return r.json(); }),
      fetch("data.json", { cache: "no-store" })
        .then(r => { if (!r.ok) throw 0; return r.json(); }),
    ]);
  } catch {
    document.querySelector("#load-error").hidden = false;
    return;
  }
  const teams = {};
  for (const t of data.teams) teams[t.id] = t;

  renderChart(hist.days, teams);
  renderMovers(hist.days, teams);
  renderTimeTravel(hist.days, teams);
}

/* curva suave (Catmull-Rom convertida a Bézier cúbica) por los puntos dados */
function smoothPath(pts) {
  if (pts.length < 2) return "";
  if (pts.length === 2) return `M${pts[0]} L${pts[1]}`;
  let d = `M${pts[0]}`;
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[Math.max(0, i - 1)], p1 = pts[i];
    const p2 = pts[i + 1], p3 = pts[Math.min(pts.length - 1, i + 2)];
    const c1 = [p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6];
    const c2 = [p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6];
    d += `C${c1} ${c2} ${p2}`;
  }
  return d;
}

function renderChart(days, teams) {
  const last = days[days.length - 1].champion;
  const top = Object.keys(last).sort((a, b) => last[b] - last[a]).slice(0, 8);

  const W = 880, H = 380, ml = 56, mr = 192, mt = 18, mb = 32;
  const pw = W - ml - mr, ph = H - mt - mb;
  const n = days.length;
  const x = i => n > 1 ? ml + (i * pw) / (n - 1) : ml + pw / 2;

  // eje ajustado al rango real de las favoritas: los cambios diarios se ven
  const vals = days.flatMap(d => top.map(id => d.champion[id] || 0));
  let lo = Math.min(...vals), hi = Math.max(...vals);
  const pad = (hi - lo) * 0.18 || 0.01;
  lo = Math.max(0, lo - pad); hi += pad;
  const step = [0.002, 0.005, 0.01, 0.02, 0.025, 0.05, 0.1]
    .find(s => (hi - lo) / s <= 7) || 0.1;
  lo = Math.floor(lo / step) * step;
  hi = Math.ceil(hi / step) * step;
  const y = p => mt + ph - ((p - lo) / (hi - lo)) * ph;
  const fmtAxis = v => (v * 100).toFixed(step < 0.01 ? 1 : 0).replace(".", ",") + "%";

  let grid = "";
  for (let v = lo; v <= hi + 1e-9; v += step) {
    grid += `<line x1="${ml}" y1="${y(v)}" x2="${ml + pw}" y2="${y(v)}"
      stroke="#eceae2"/>
      <text x="${ml - 9}" y="${y(v) + 4}" text-anchor="end" font-size="11"
      fill="#9aa1ab">${fmtAxis(v)}</text>`;
  }

  const every = Math.max(1, Math.ceil(n / 9));
  let xlabels = "";
  for (let i = 0; i < n; i++) {
    if (i % every && i !== n - 1) continue;
    xlabels += `<text x="${x(i)}" y="${H - 8}" text-anchor="middle"
      font-size="11" fill="#9aa1ab">${fmtShort(days[i].date)}</text>`;
  }

  // etiquetas a la derecha, con separación anticolisión
  const labels = top.map((id, k) => ({
    id, k, yPos: y(last[id] || 0), p: last[id] || 0,
  })).sort((a, b) => a.yPos - b.yPos);
  for (let i = 1; i < labels.length; i++)
    if (labels[i].yPos - labels[i - 1].yPos < 17)
      labels[i].yPos = labels[i - 1].yPos + 17;

  let series = "", tags = "";
  for (const { id, k, yPos, p } of labels) {
    const color = PALETTE[k % PALETTE.length];
    const pts = days.map((d, i) => [x(i), y(d.champion[id] || 0)]);
    const path = smoothPath(pts);
    const dots = days.map((d, i) =>
      `<circle cx="${pts[i][0]}" cy="${pts[i][1]}"
        r="${i === n - 1 ? 3.6 : 2.6}" fill="${color}">
        <title>${teams[id].name} · ${fmtLong(d.date)} · ${pctTxt(d.champion[id] || 0)}</title>
      </circle>`).join("");
    series += `<g class="serie" data-team="${id}">
      ${path ? `<path class="hit" d="${path}" fill="none" stroke="transparent"
        stroke-width="16"/>
      <path class="line" d="${path}" fill="none" stroke="${color}"
        stroke-width="2" stroke-linecap="round" pathLength="1"/>` : ""}
      ${dots}
    </g>`;
    tags += `<g class="serie-label" data-team="${id}">
      <image href="https://flagcdn.com/w40/${teams[id].flag}.png"
        x="${ml + pw + 10}" y="${yPos - 7}" width="18" height="13.5"
        preserveAspectRatio="xMidYMid slice"/>
      <text x="${ml + pw + 33}" y="${yPos + 4}" font-size="12.5">
        <tspan font-weight="600" fill="${color}">${teams[id].name}</tspan>
        <tspan fill="#9aa1ab" font-size="11.5"> ${pctTxt(p)}</tspan>
      </text>
    </g>`;
  }

  const chart = document.querySelector("#chart");
  chart.innerHTML =
    `<svg viewBox="0 0 ${W} ${H}" role="img"
      aria-label="Evolución de la probabilidad de campeón por jornada">
      ${grid}${xlabels}${series}${tags}
    </svg>`;
  document.querySelector("#chart-note").hidden = days.length > 1;
  setupChartFocus(chart);
}

/* foco interactivo: pasar el cursor destaca una serie, el clic la deja fijada */
function setupChartFocus(chart) {
  let pinned = null;
  const setFocus = id => {
    chart.classList.toggle("has-focus", Boolean(id));
    chart.querySelectorAll("[data-team]").forEach(el =>
      el.classList.toggle("focus", el.dataset.team === id));
  };
  chart.addEventListener("pointerover", e => {
    const g = e.target.closest("[data-team]");
    if (g && !pinned) setFocus(g.dataset.team);
  });
  chart.addEventListener("pointerout", () => { if (!pinned) setFocus(null); });
  chart.addEventListener("click", e => {
    const g = e.target.closest("[data-team]");
    pinned = g && pinned !== g.dataset.team ? g.dataset.team : null;
    setFocus(pinned);
  });
}

function renderMovers(days, teams) {
  if (days.length < 2) return;
  const [prev, last] = days.slice(-2);
  const deltas = Object.keys(last.champion)
    .map(id => [id, (last.champion[id] || 0) - (prev.champion[id] || 0)])
    .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
    .slice(0, 6);

  document.querySelector("#movers-hint").textContent =
    `Probabilidad de campeón frente a la actualización del ${fmtLong(prev.date)} ` +
    `(${last.results - prev.results} partido${last.results - prev.results === 1 ? "" : "s"} ` +
    `nuevo${last.results - prev.results === 1 ? "" : "s"} fijado${last.results - prev.results === 1 ? "" : "s"}). ` +
    `Los movimientos pequeños son en parte ruido de simulación.`;

  document.querySelector("#movers").innerHTML = deltas.map(([id, d]) => {
    const t = teams[id];
    const cls = d > 0 ? "delta-up" : (d < 0 ? "delta-down" : "");
    const sign = d > 0 ? "+" : "";
    return `<div class="mover">
      ${flagImg(t)}<span class="mover-name">${t.name}</span>
      <span class="mover-now">${pctTxt(last.champion[id] || 0)}</span>
      <span class="mover-delta ${cls}">${sign}${(d * 100).toFixed(1).replace(".", ",")}</span>
    </div>`;
  }).join("");
  document.querySelector("#movers-section").hidden = false;
}

function renderTimeTravel(days, teams) {
  const rows = [...days].reverse().map((d, i) => {
    const idx = days.length - 1 - i;
    const newCount = d.results - (idx > 0 ? days[idx - 1].results : 0);
    const dayLabel = idx === 0 && d.results === 0
      ? `<span class="tt-pct">antes del torneo</span>`
      : `+${newCount} nuevo${newCount === 1 ? "" : "s"}`;
    const favId = Object.keys(d.champion)
      .reduce((a, b) => (d.champion[a] >= d.champion[b] ? a : b));
    const fav = teams[favId];
    const url = `index.html?dia=${d.date}`;
    const today = i === 0;
    return `<tr>
      <td><a href="${url}">${fmtLong(d.date)}</a>${today ? ` <span class="tt-today">última</span>` : ""}</td>
      <td>${dayLabel}</td>
      <td class="team-cell">${flagImg(fav)}${fav.name}
        <span class="tt-pct">${pctTxt(d.champion[favId])}</span></td>
      <td><a class="btn btn-small" href="${url}">Ver ese día</a></td>
    </tr>`;
  }).join("");
  document.querySelector("#tt-table tbody").innerHTML = rows;
}
