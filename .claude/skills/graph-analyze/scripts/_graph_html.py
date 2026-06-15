"""
_graph_html.py — renderer HTML self-contained del grafo (Variante A, vanilla).

Produce un singolo file HTML con dati + CSS + JS **inline** (nessuna dipendenza
remota): renderer Canvas-2D con layout precalcolato (x/y dal graph.json), pan/zoom,
hover-highlight dei vicini, ricerca, toggle colore tipo/community e i filtri
portati da `graph-filters.ts` del riferimento (hide structural/isolated, max-links,
per-type, hide singolo nodo, reset).

Nota: il JS gira in browser; in Obsidian (obsidian-html-plugin) serve Unrestricted
mode. Vedi GraphViz_Spec_Plan.md §5.0.
"""

from __future__ import annotations

import json

from _graph_emit import TYPE_COLORS, COMMUNITY_COLORS


def render_html(data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return (
        _TEMPLATE
        .replace("/*__DATA__*/", payload)
        .replace("/*__TYPE_COLORS__*/", json.dumps(TYPE_COLORS))
        .replace("/*__COMMUNITY_COLORS__*/", json.dumps(COMMUNITY_COLORS))
    )


_TEMPLATE = r"""<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Knowledge Graph</title>
<style>
  * { box-sizing: border-box; }
  html, body { margin: 0; height: 100%; font-family: -apple-system, system-ui, sans-serif; }
  #app { position: fixed; inset: 0; background: #f8fafc; color: #0f172a; }
  #toolbar { position: absolute; top: 0; left: 0; right: 0; height: 40px; display: flex;
    align-items: center; gap: 8px; padding: 0 10px; background: rgba(255,255,255,.95);
    border-bottom: 1px solid #e2e8f0; font-size: 12px; z-index: 5; }
  #toolbar .counts { color: #64748b; }
  #toolbar .grow { flex: 1; }
  button { font: inherit; font-size: 12px; border: 1px solid #cbd5e1; background: #fff;
    border-radius: 6px; padding: 4px 8px; cursor: pointer; }
  button.active { background: #e2e8f0; font-weight: 600; }
  input[type=search], input[type=number] { font: inherit; font-size: 12px; border: 1px solid #cbd5e1;
    border-radius: 6px; padding: 4px 8px; }
  #filters { position: absolute; top: 48px; left: 10px; width: 250px; background: rgba(255,255,255,.97);
    border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px; font-size: 12px; z-index: 5;
    box-shadow: 0 4px 16px rgba(0,0,0,.08); }
  #filters.hidden { display: none; }
  #filters h3 { margin: 0 0 8px; font-size: 12px; display: flex; justify-content: space-between; }
  #filters .group { margin-bottom: 10px; }
  #filters .group > .lbl { color: #64748b; font-weight: 600; margin-bottom: 4px; }
  #filters label { display: flex; align-items: center; gap: 6px; padding: 1px 0; }
  #types { display: grid; grid-template-columns: 1fr 1fr; gap: 2px 8px; }
  #legend { position: absolute; bottom: 10px; left: 10px; background: rgba(255,255,255,.95);
    border: 1px solid #e2e8f0; border-radius: 8px; padding: 8px 10px; font-size: 11px; z-index: 5; }
  #legend .row { display: flex; align-items: center; gap: 6px; padding: 1px 0; }
  #legend .dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
  canvas { position: absolute; top: 40px; left: 0; right: 0; bottom: 0; width: 100%;
    height: calc(100% - 40px); display: block; cursor: grab; }
  canvas.dragging { cursor: grabbing; }
  #info { color: #475569; max-width: 320px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
</head>
<body>
<div id="app">
  <div id="toolbar">
    <strong>Knowledge Graph</strong>
    <span class="counts" id="counts"></span>
    <button id="btnFilter">Filtri</button>
    <button id="btnType" class="active">Tipo</button>
    <button id="btnComm">Community</button>
    <input type="search" id="search" placeholder="Cerca…" style="width:140px">
    <span class="grow"></span>
    <span id="info"></span>
    <button id="btnFit">Adatta</button>
  </div>

  <div id="filters" class="hidden">
    <h3>Filtri <button id="btnReset" style="padding:2px 6px">Reset</button></h3>
    <div class="group">
      <div class="lbl">Rapidi</div>
      <label><input type="checkbox" id="fStructural" checked> Nascondi strutturali</label>
      <label><input type="checkbox" id="fIsolated"> Nascondi isolati</label>
    </div>
    <div class="group">
      <div class="lbl">Max link</div>
      <label><input type="number" id="fMax" min="0" placeholder="Qualsiasi" style="width:90px"> sopra soglia</label>
    </div>
    <div class="group">
      <div class="lbl">Tipi</div>
      <div id="types"></div>
    </div>
  </div>

  <canvas id="c"></canvas>
  <div id="legend"></div>
</div>

<script type="application/json" id="graph-data">/*__DATA__*/</script>
<script>
const DATA = JSON.parse(document.getElementById('graph-data').textContent);
const TYPE_COLORS = /*__TYPE_COLORS__*/;
const COMMUNITY_COLORS = /*__COMMUNITY_COLORS__*/;

const canvas = document.getElementById('c');
const ctx = canvas.getContext('2d');
const nodeById = new Map(DATA.nodes.map(n => [n.id, n]));
const maxLink = Math.max(1, ...DATA.nodes.map(n => n.linkCount));

const state = {
  filters: { hideStructural: true, hideIsolated: false, maxLinks: null,
             hiddenTypes: new Set(), hiddenNodeIds: new Set() },
  colorMode: 'type', search: '', hovered: null,
  cam: { x: 0, y: 0, zoom: 1 },
};

let visNodes = [], visEdges = [], adj = new Map();

function comm(n) {
  const k = COMMUNITY_COLORS.length;
  return COMMUNITY_COLORS[((n.community % k) + k) % k];
}
function nodeColor(n) {
  return state.colorMode === 'community' ? comm(n) : (TYPE_COLORS[n.type] || TYPE_COLORS.unknown);
}
function nodeRadius(n) { return 4 + 10 * Math.sqrt(n.linkCount / maxLink); }
function matches(n) { return state.search && n.label.toLowerCase().includes(state.search.toLowerCase()); }

function recompute() {
  const f = state.filters;
  const hidden = new Set();
  for (const n of DATA.nodes) {
    if (f.hiddenNodeIds.has(n.id)) hidden.add(n.id);
    else if (f.hiddenTypes.has(n.type)) hidden.add(n.id);
    else if (f.hideStructural && n.structural) hidden.add(n.id);
    else if (f.hideIsolated && n.linkCount <= 0) hidden.add(n.id);
    else if (f.maxLinks != null && n.linkCount > f.maxLinks) hidden.add(n.id);
  }
  visNodes = DATA.nodes.filter(n => !hidden.has(n.id));
  const vis = new Set(visNodes.map(n => n.id));
  visEdges = DATA.edges.filter(e => vis.has(e.source) && vis.has(e.target));
  adj = new Map(visNodes.map(n => [n.id, new Set()]));
  for (const e of visEdges) { adj.get(e.source).add(e.target); adj.get(e.target).add(e.source); }
  document.getElementById('counts').textContent =
    visNodes.length + '/' + DATA.nodes.length + ' pagine · ' + visEdges.length + ' link';
  draw();
}

function toScreen(x, y) {
  return [(x - state.cam.x) * state.cam.zoom + canvas.width / 2,
          (y - state.cam.y) * state.cam.zoom + canvas.height / 2];
}
function fit() {
  if (!visNodes.length) { draw(); return; }
  let a = Infinity, b = Infinity, c = -Infinity, d = -Infinity;
  for (const n of visNodes) { a = Math.min(a, n.x); b = Math.min(b, n.y); c = Math.max(c, n.x); d = Math.max(d, n.y); }
  const w = c - a || 1, h = d - b || 1;
  state.cam.x = (a + c) / 2; state.cam.y = (b + d) / 2;
  state.cam.zoom = Math.min(canvas.width / (w * 1.25), canvas.height / (h * 1.25), 2);
  draw();
}

function draw() {
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  const hov = state.hovered, nbrs = hov ? adj.get(hov) : null;
  for (const e of visEdges) {
    const a = nodeById.get(e.source), b = nodeById.get(e.target);
    const [ax, ay] = toScreen(a.x, a.y), [bx, by] = toScreen(b.x, b.y);
    const active = hov && (e.source === hov || e.target === hov);
    ctx.strokeStyle = hov ? (active ? '#1e293b' : '#eef2f6') : 'rgba(100,116,139,0.22)';
    ctx.lineWidth = active ? 2 : 0.6;
    ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(bx, by); ctx.stroke();
  }
  for (const n of visNodes) {
    const [x, y] = toScreen(n.x, n.y);
    const r = nodeRadius(n) * Math.max(0.6, Math.min(state.cam.zoom, 1.6));
    const dim = hov && n.id !== hov && !(nbrs && nbrs.has(n.id));
    ctx.globalAlpha = dim ? 0.13 : 1;
    ctx.fillStyle = nodeColor(n);
    ctx.beginPath(); ctx.arc(x, y, r, 0, 2 * Math.PI); ctx.fill();
    if (matches(n)) { ctx.globalAlpha = 1; ctx.strokeStyle = '#f59e0b'; ctx.lineWidth = 3; ctx.stroke(); }
    if (n.id === hov) { ctx.globalAlpha = 1; ctx.strokeStyle = '#0f172a'; ctx.lineWidth = 2; ctx.stroke(); }
    if (!dim && (r > 9 || n.id === hov || matches(n))) {
      ctx.globalAlpha = 1; ctx.fillStyle = '#0f172a'; ctx.font = '11px sans-serif';
      ctx.textAlign = 'center'; ctx.fillText(n.label, x, y - r - 3);
    }
    ctx.globalAlpha = 1;
  }
}

function nodeAt(sx, sy) {
  let best = null, bd = Infinity;
  for (const n of visNodes) {
    const [x, y] = toScreen(n.x, n.y);
    const r = nodeRadius(n) * Math.max(0.6, Math.min(state.cam.zoom, 1.6)) + 4;
    const dd = (x - sx) ** 2 + (y - sy) ** 2;
    if (dd <= r * r && dd < bd) { bd = dd; best = n; }
  }
  return best;
}

// ── Eventi ─────────────────────────────────────────────────────────────────
let dragging = false, lastX = 0, lastY = 0, moved = false;
canvas.addEventListener('mousedown', e => { dragging = true; moved = false; lastX = e.clientX; lastY = e.clientY; canvas.classList.add('dragging'); });
window.addEventListener('mouseup', () => { dragging = false; canvas.classList.remove('dragging'); });
canvas.addEventListener('mousemove', e => {
  const rect = canvas.getBoundingClientRect();
  const sx = e.clientX - rect.left, sy = e.clientY - rect.top;
  if (dragging) {
    moved = true;
    state.cam.x -= (e.clientX - lastX) / state.cam.zoom;
    state.cam.y -= (e.clientY - lastY) / state.cam.zoom;
    lastX = e.clientX; lastY = e.clientY; draw(); return;
  }
  const n = nodeAt(sx, sy);
  const id = n ? n.id : null;
  if (id !== state.hovered) {
    state.hovered = id;
    document.getElementById('info').textContent = n ? (n.label + '  ·  ' + n.type + '  ·  ' + n.linkCount + ' link') : '';
    canvas.style.cursor = n ? 'pointer' : 'grab';
    draw();
  }
});
canvas.addEventListener('wheel', e => {
  e.preventDefault();
  const rect = canvas.getBoundingClientRect();
  const sx = e.clientX - rect.left, sy = e.clientY - rect.top;
  const wx = (sx - canvas.width / 2) / state.cam.zoom + state.cam.x;
  const wy = (sy - canvas.height / 2) / state.cam.zoom + state.cam.y;
  const factor = e.deltaY < 0 ? 1.1 : 1 / 1.1;
  state.cam.zoom = Math.max(0.05, Math.min(8, state.cam.zoom * factor));
  state.cam.x = wx - (sx - canvas.width / 2) / state.cam.zoom;
  state.cam.y = wy - (sy - canvas.height / 2) / state.cam.zoom;
  draw();
}, { passive: false });
canvas.addEventListener('click', e => {
  if (moved) return;
  const rect = canvas.getBoundingClientRect();
  const n = nodeAt(e.clientX - rect.left, e.clientY - rect.top);
  if (!n) return;
  // best-effort: apri la pagina in Obsidian (può non funzionare nel viewer)
  const file = n.path.replace(/\.md$/, '');
  window.location.href = 'obsidian://open?vault=' + encodeURIComponent(DATA.meta.vault) +
    '&file=' + encodeURIComponent(file);
});

// ── Controlli ────────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);
$('btnFilter').onclick = () => $('filters').classList.toggle('hidden');
$('btnFit').onclick = fit;
$('btnType').onclick = () => { state.colorMode = 'type'; $('btnType').classList.add('active'); $('btnComm').classList.remove('active'); renderLegend(); draw(); };
$('btnComm').onclick = () => { state.colorMode = 'community'; $('btnComm').classList.add('active'); $('btnType').classList.remove('active'); renderLegend(); draw(); };
$('search').oninput = e => { state.search = e.target.value.trim(); draw(); };
$('fStructural').onchange = e => { state.filters.hideStructural = e.target.checked; recompute(); };
$('fIsolated').onchange = e => { state.filters.hideIsolated = e.target.checked; recompute(); };
$('fMax').oninput = e => { const v = e.target.value.trim(); state.filters.maxLinks = v === '' ? null : Math.max(0, +v); recompute(); };
$('btnReset').onclick = () => {
  state.filters = { hideStructural: true, hideIsolated: false, maxLinks: null, hiddenTypes: new Set(), hiddenNodeIds: new Set() };
  $('fStructural').checked = true; $('fIsolated').checked = false; $('fMax').value = '';
  buildTypeToggles(); recompute();
};

function buildTypeToggles() {
  const counts = {};
  for (const n of DATA.nodes) counts[n.type] = (counts[n.type] || 0) + 1;
  const box = $('types'); box.innerHTML = '';
  for (const t of Object.keys(counts).sort()) {
    const id = 'ty_' + t;
    const lab = document.createElement('label');
    lab.innerHTML = '<input type="checkbox" id="' + id + '" ' +
      (state.filters.hiddenTypes.has(t) ? '' : 'checked') + '> ' + t + ' <span style="color:#94a3b8">' + counts[t] + '</span>';
    box.appendChild(lab);
    lab.querySelector('input').onchange = e => {
      if (e.target.checked) state.filters.hiddenTypes.delete(t); else state.filters.hiddenTypes.add(t);
      recompute();
    };
  }
}

function renderLegend() {
  const el = $('legend'); el.innerHTML = '';
  if (state.colorMode === 'type') {
    const present = [...new Set(DATA.nodes.map(n => n.type))].sort();
    for (const t of present) {
      el.innerHTML += '<div class="row"><span class="dot" style="background:' + (TYPE_COLORS[t] || TYPE_COLORS.unknown) + '"></span>' + t + '</div>';
    }
  } else {
    for (const c of DATA.communities.slice(0, 12)) {
      const color = COMMUNITY_COLORS[c.id % COMMUNITY_COLORS.length];
      el.innerHTML += '<div class="row"><span class="dot" style="background:' + color + '"></span>#' + c.id + ' · ' + (c.topNodes[0] || '') + ' (' + c.size + ')</div>';
    }
  }
}

function resize() { canvas.width = canvas.clientWidth; canvas.height = canvas.clientHeight; draw(); }
window.addEventListener('resize', resize);

// init
canvas.width = canvas.clientWidth; canvas.height = canvas.clientHeight;
buildTypeToggles(); renderLegend(); recompute(); fit();
</script>
</body>
</html>
"""
