"""
_graph_canvas.py — renderer Obsidian Canvas (.canvas, JSON Canvas) del grafo.

Dal graph.json produce un canvas con:
  - nodi `text` contenenti `[[wikilink]]` alla pagina (cliccabili, nativi),
    colorati per tipo, dimensionati per linkCount, posizionati dal layout x/y;
  - un nodo `group` per ogni community Louvain (riquadro etichettato col top-node);
  - archi dai wikilink (Canvas non ha spessore arco → il peso non è rappresentato).

I filtri sono applicati **a generazione** (Canvas è statico): default = nascondi
le pagine strutturali, come nel riferimento. Vedi GraphViz_Spec_Plan.md §7.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from _graph_emit import TYPE_COLORS, COMMUNITY_COLORS


def _visible(data: dict, hide_structural: bool, hide_isolated: bool,
             max_links: int | None, hidden_types: set | None) -> list[dict]:
    hidden_types = hidden_types or set()
    out = []
    for n in data["nodes"]:
        if n["type"] in hidden_types:
            continue
        if hide_structural and n.get("structural"):
            continue
        if hide_isolated and n["linkCount"] <= 0:
            continue
        if max_links is not None and n["linkCount"] > max_links:
            continue
        out.append(n)
    return out


def _wikilink(node: dict) -> str:
    """`[[basename]]` (o `[[basename|label]]`) — basename reale dal path."""
    base = PurePosixPath(node["path"]).stem if node.get("path") else node["id"]
    label = node.get("label") or base
    safe_label = label.replace("]", "").replace("|", "")
    return f"[[{base}]]" if safe_label == base else f"[[{base}|{safe_label}]]"


def _node_size(link_count: int) -> tuple[int, int]:
    width = 140 + 8 * min(link_count, 18)   # 140..284
    return width, 60


def build_canvas(data: dict, hide_structural: bool = True, hide_isolated: bool = False,
                 max_links: int | None = None, hidden_types: set | None = None) -> dict:
    visible = _visible(data, hide_structural, hide_isolated, max_links, hidden_types)
    vis_ids = {n["id"] for n in visible}

    canvas_nodes: list[dict] = []
    canvas_edges: list[dict] = []

    # Riquadri group per community (bounding box dei nodi membri).
    by_comm: dict[int, list[dict]] = {}
    for n in visible:
        by_comm.setdefault(n["community"], []).append(n)

    top_node = {c["id"]: (c["topNodes"][0] if c.get("topNodes") else "")
                for c in data.get("communities", [])}

    for cid, members in sorted(by_comm.items()):
        if len(members) < 2:
            continue  # niente riquadro per community singoletto
        xs, ys, dims = [], [], []
        for m in members:
            w, h = _node_size(m["linkCount"])
            xs.append(m["x"] - w / 2); ys.append(m["y"] - h / 2)
            dims.append((m["x"] + w / 2, m["y"] + h / 2))
        pad = 60
        minx = min(xs) - pad; miny = min(ys) - pad
        maxx = max(d[0] for d in dims) + pad; maxy = max(d[1] for d in dims) + pad
        canvas_nodes.append({
            "id": f"grp-{cid}",
            "type": "group",
            "x": round(minx), "y": round(miny),
            "width": round(maxx - minx), "height": round(maxy - miny),
            "label": f"#{cid} {top_node.get(cid, '')}".strip(),
            "color": COMMUNITY_COLORS[cid % len(COMMUNITY_COLORS)],
        })

    # Nodi testo (uno per pagina visibile).
    for n in visible:
        w, h = _node_size(n["linkCount"])
        canvas_nodes.append({
            "id": n["id"],
            "type": "text",
            "text": _wikilink(n),
            "x": round(n["x"] - w / 2), "y": round(n["y"] - h / 2),
            "width": w, "height": h,
            "color": TYPE_COLORS.get(n["type"], TYPE_COLORS["unknown"]),
        })

    # Archi (solo fra nodi visibili).
    for i, e in enumerate(data["edges"]):
        if e["source"] in vis_ids and e["target"] in vis_ids:
            canvas_edges.append({
                "id": f"e{i}",
                "fromNode": e["source"],
                "toNode": e["target"],
            })

    return {"nodes": canvas_nodes, "edges": canvas_edges}
