"""
_graph_emit.py — costruisce il contratto dati `graph.json` per la visualizzazione
del grafo (HTML interattivo + Canvas). Stdlib puro.

Riusa l'output di `_graph_metrics.enrich()` (community, pagerank, betweenness,
suggerimenti) e aggiunge:
  - `type` del nodo (dedotto dalla cartella wiki/<tipo>s/, fallback frontmatter)
  - `label` (campo `title` del frontmatter, fallback allo stem)
  - flag `structural` (index/overview/log/… — pagine auto-gestite)
  - posizione `x`/`y` (layout community-clustered, deterministico)

Schema prodotto: vedi GraphViz_Spec_Plan.md §3.
"""

from __future__ import annotations

import math
import re
from datetime import date
from pathlib import Path

# Cartella diretta sotto wiki/ → tipo pagina.
TYPE_BY_FOLDER = {
    "entities": "entity",
    "concepts": "concept",
    "sources": "source",
    "queries": "query",
    "synthesis": "synthesis",
}

# Pagine auto-gestite / strutturali (sotto wiki/): non sono contenuto.
STRUCTURAL = {"index", "overview", "log", "glossary", "lint-report", "meetings-index"}

# Palette condivisa fra i renderer (HTML + Canvas) per coerenza visiva.
TYPE_COLORS = {
    "entity": "#2563eb",      # blue
    "concept": "#16a34a",     # green
    "source": "#d97706",      # amber
    "query": "#9333ea",       # purple
    "synthesis": "#dc2626",   # red
    "unknown": "#64748b",     # slate
    "structural": "#94a3b8",  # slate-400
}
COMMUNITY_COLORS = [
    "#2563eb", "#16a34a", "#d97706", "#9333ea", "#dc2626", "#0891b2",
    "#ca8a04", "#db2777", "#65a30d", "#7c3aed", "#0d9488", "#e11d48",
]

_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_TITLE_RE = re.compile(r'^title\s*:\s*"?(.*?)"?\s*$', re.MULTILINE)
_TYPE_RE = re.compile(r'^type\s*:\s*"?([\w-]+)"?\s*$', re.MULTILINE)


def read_meta(path: Path) -> tuple[str | None, str | None]:
    """(type, title) dal frontmatter del file; best-effort, (None, None) se assente."""
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None, None
    m = _FM_RE.match(content)
    if not m:
        return None, None
    fm = m.group(1)
    tm = _TYPE_RE.search(fm)
    tim = _TITLE_RE.search(fm)
    return (tm.group(1) if tm else None), (tim.group(1).strip() if tim else None)


def infer_type(path: Path, fm_type: str | None) -> str:
    """Tipo del nodo: prima la cartella (deterministica), poi il frontmatter."""
    folder = path.parent.name
    if folder in TYPE_BY_FOLDER:
        return TYPE_BY_FOLDER[folder]
    return fm_type or "unknown"


def _internal_graph(nodes: dict, edge_counts: dict):
    """Gradi interni (in/out, pesati) e archi non orientati unici con peso."""
    node_set = set(nodes.keys())
    out_deg = {n: 0 for n in node_set}
    in_deg = {n: 0 for n in node_set}
    undirected_w: dict[tuple[str, str], int] = {}
    for (src, tgt), cnt in edge_counts.items():
        if src not in node_set or tgt not in node_set or src == tgt:
            continue
        out_deg[src] += cnt
        in_deg[tgt] += cnt
        key = (src, tgt) if src < tgt else (tgt, src)
        undirected_w[key] = undirected_w.get(key, 0) + cnt
    return out_deg, in_deg, undirected_w


def cluster_layout(community_members: dict, spacing: float = 1000.0) -> dict:
    """Layout community-clustered, deterministico: ogni community è un cerchio di
    nodi attorno a un centro; i centri sono disposti su un cerchio globale.
    Ritorna dict node_id -> (x, y)."""
    comms = sorted(community_members.keys())
    k = len(comms)
    pos: dict[str, tuple[float, float]] = {}
    if k == 0:
        return pos
    big_r = spacing * max(1.0, k / (2 * math.pi)) * 1.5
    for idx, cid in enumerate(comms):
        members = community_members[cid]
        if k == 1:
            cx, cy = 0.0, 0.0
        else:
            ang = 2 * math.pi * idx / k
            cx, cy = big_r * math.cos(ang), big_r * math.sin(ang)
        n = len(members)
        if n == 1:
            pos[members[0]] = (cx, cy)
            continue
        r = spacing * 0.25 * math.sqrt(n)
        for j, node in enumerate(members):
            a = 2 * math.pi * j / n
            pos[node] = (cx + r * math.cos(a), cy + r * math.sin(a))
    return pos


def build_graph_json(nodes: dict, edge_counts: dict, enriched: dict,
                     vault_root: Path | None = None, vault_name: str | None = None) -> dict:
    """Assembla il dict `graph.json`. `enriched` = output di _graph_metrics.enrich()."""
    node_set = set(nodes.keys())
    out_deg, in_deg, undirected_w = _internal_graph(nodes, edge_counts)
    comm = enriched["communities"]            # node -> community id
    members = enriched["community_members"]   # community id -> [node] (per pagerank)
    pr = enriched["pagerank"]
    btw = enriched["betweenness"]
    pos = cluster_layout(members)

    out_nodes = []
    for stem in sorted(node_set):
        path = nodes[stem]
        fm_type, title = read_meta(path)
        rel = (path.relative_to(vault_root).as_posix()
               if vault_root else path.as_posix())
        x, y = pos.get(stem, (0.0, 0.0))
        out_nodes.append({
            "id": stem,
            "label": title or stem,
            "type": infer_type(path, fm_type),
            "structural": stem in STRUCTURAL,
            "path": rel,
            "linkCount": out_deg[stem] + in_deg[stem],
            "community": comm.get(stem, -1),
            "pagerank": round(pr.get(stem, 0.0), 6),
            "betweenness": round(btw.get(stem, 0.0), 4),
            "x": round(x, 2),
            "y": round(y, 2),
        })

    out_edges = [
        {"source": a, "target": b, "weight": w}
        for (a, b), w in sorted(undirected_w.items())
    ]

    label_of = {n["id"]: n["label"] for n in out_nodes}
    out_comms = [
        {"id": cid, "size": len(members[cid]),
         "topNodes": [label_of.get(m, m) for m in members[cid][:3]]}
        for cid in sorted(members.keys())
    ]

    insights = {
        "bridges": [{"id": s, "betweenness": round(v, 4)}
                    for s, v in enriched["top_betweenness"][:8] if v > 0],
        "suggested": enriched["suggestions"][:15],
        "isolated": sorted(n for n in node_set
                           if out_deg[n] + in_deg[n] == 0 and n not in STRUCTURAL),
    }

    return {
        "meta": {
            "generated": date.today().isoformat(),
            "vault": vault_name or (vault_root.name if vault_root else ""),
            "nodes": len(out_nodes),
            "edges": len(out_edges),
            "modularity": round(enriched.get("modularity", 0.0), 4),
        },
        "nodes": out_nodes,
        "edges": out_edges,
        "communities": out_comms,
        "insights": insights,
    }
