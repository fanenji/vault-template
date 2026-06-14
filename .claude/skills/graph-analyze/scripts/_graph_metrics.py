"""
_graph_metrics.py — analisi avanzata del grafo wiki (stdlib puro).

Consuma gli archi già estratti da graph-analyze (`edge_counts`: i wikilink
curati nei body) e calcola, senza alcuna chiamata LLM e senza dipendenze
esterne:

  1. connected_components()  — isole di conoscenza (proiezione non orientata)
  2. louvain_communities()   — vicinati tematici (ottimizzazione di modularità)
  3. pagerank()              — importanza globale sul grafo orientato
  4. betweenness()           — pagine-ponte (algoritmo di Brandes)
  5. suggest_links()         — link mancanti suggeriti (vicini in comune)

Tutti gli archi reali sono `EXTRACTED` (wikilink espliciti). L'unico output
"inferito" è suggest_links(): va presentato come deduzione strutturale da
verificare, mai come fatto wiki.

A ~200 nodi tutte le funzioni sono istantanee. Le complessità (coppie O(N²),
Brandes O(N·E)) sono accettabili a questa scala; un cutoff per-cluster va
introdotto solo se/quando la wiki cresce di un ordine di grandezza.
"""

from __future__ import annotations

import math
from collections import defaultdict, deque

# Pagine auto-gestite: escluse da community/suggerimenti per non introdurre
# rumore (sono hub strutturali, non contenuto).
_AUTO_PAGES = {"index", "log", "overview", "glossary", "lint-report", "meetings-index"}


# --------------------------------------------------------------------------- #
# Costruzione delle strutture di adiacenza (solo archi interni, no self-loop)
# --------------------------------------------------------------------------- #

def build_graph(nodes: dict, edge_counts: dict) -> dict:
    """Da (nodes, edge_counts) costruisce le rappresentazioni del grafo.

    - directed[u][v] = peso (conteggio link u->v), solo archi interni, u != v
    - undirected[u][v] = peso simmetrico (u->v + v->u)
    - tutti i nodi compaiono come chiavi anche se isolati
    """
    node_set = set(nodes.keys())
    directed: dict[str, dict[str, int]] = {n: {} for n in node_set}
    undirected: dict[str, dict[str, int]] = {n: {} for n in node_set}

    for (src, tgt), cnt in edge_counts.items():
        if src not in node_set or tgt not in node_set or src == tgt:
            continue
        directed[src][tgt] = directed[src].get(tgt, 0) + cnt
        undirected[src][tgt] = undirected[src].get(tgt, 0) + cnt
        undirected[tgt][src] = undirected[tgt].get(src, 0) + cnt

    return {"node_set": node_set, "directed": directed, "undirected": undirected}


# --------------------------------------------------------------------------- #
# 1. Componenti connesse (proiezione non orientata)
# --------------------------------------------------------------------------- #

def connected_components(undirected: dict) -> list[set[str]]:
    """Componenti debolmente connesse, ordinate per dimensione decrescente."""
    seen: set[str] = set()
    components: list[set[str]] = []
    for start in sorted(undirected.keys()):
        if start in seen:
            continue
        comp: set[str] = set()
        queue = deque([start])
        seen.add(start)
        while queue:
            node = queue.popleft()
            comp.add(node)
            for nbr in undirected[node]:
                if nbr not in seen:
                    seen.add(nbr)
                    queue.append(nbr)
        components.append(comp)
    components.sort(key=len, reverse=True)
    return components


# --------------------------------------------------------------------------- #
# 2. Community detection (Louvain pesato, multi-livello)
# --------------------------------------------------------------------------- #

def _modularity(graph: dict, node2com: dict, m: float) -> float:
    if m == 0:
        return 0.0
    inc: dict = defaultdict(float)   # peso interno per community
    deg: dict = defaultdict(float)   # somma gradi per community
    for u in graph:
        com_u = node2com[u]
        for v, w in graph[u].items():
            deg[com_u] += w
            if node2com[v] == com_u:
                inc[com_u] += w if u != v else 2 * w
    q = 0.0
    for com in deg:
        q += inc[com] / (2 * m) - (deg[com] / (2 * m)) ** 2
    return q


def _degree(graph: dict, node: str) -> float:
    """Grado pesato; il self-loop conta doppio (convenzione Louvain)."""
    return sum(w if nbr != node else 2 * w for nbr, w in graph[node].items())


def _one_level(graph: dict, m: float) -> dict:
    """Una passata di local-moving. Ritorna node2com sul `graph` dato."""
    node2com = {n: n for n in graph}
    gdeg = {n: _degree(graph, n) for n in graph}
    loops = {n: graph[n].get(n, 0) for n in graph}
    com_deg = dict(gdeg)  # somma gradi dei nodi nella community

    improved = True
    while improved:
        improved = False
        for node in sorted(graph.keys()):
            cur_com = node2com[node]
            # peso dei link da `node` verso ciascuna community vicina
            nbr_w: dict = defaultdict(float)
            for nbr, w in graph[node].items():
                if nbr == node:
                    continue
                nbr_w[node2com[nbr]] += w
            # rimuovi node dalla sua community
            com_deg[cur_com] -= gdeg[node]
            best_com = cur_com
            best_gain = nbr_w.get(cur_com, 0.0) - com_deg[cur_com] * gdeg[node] / (2 * m)
            for com, w in nbr_w.items():
                gain = w - com_deg[com] * gdeg[node] / (2 * m)
                if gain > best_gain + 1e-12:
                    best_gain = gain
                    best_com = com
            com_deg[best_com] += gdeg[node]
            node2com[node] = best_com
            if best_com != cur_com:
                improved = True
    return node2com


def _aggregate(graph: dict, node2com: dict) -> dict:
    """Comprime ogni community in un super-nodo (archi sommati, self-loop interni)."""
    new: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    seen_pairs: set = set()
    for u in graph:
        cu = node2com[u]
        new.setdefault(cu, defaultdict(float))
        for v, w in graph[u].items():
            cv = node2com[v]
            # ogni arco non orientato una sola volta
            key = (min(u, v), max(u, v))
            if u != v and key in seen_pairs:
                continue
            seen_pairs.add(key)
            new[cu][cv] += w
            if cu != cv:
                new[cv][cu] += w
    return {k: dict(v) for k, v in new.items()}


def louvain_communities(undirected: dict) -> dict:
    """Partizione dei nodi in community. Ritorna dict node -> community_id (int),
    con id assegnati in ordine di dimensione decrescente (0 = più grande)."""
    # m = somma dei pesi degli archi (ogni arco non orientato contato una volta;
    # eventuali self-loop una volta).
    m = 0.0
    for u in undirected:
        for v, w in undirected[u].items():
            if u <= v:
                m += w
    if m == 0:
        return {n: i for i, n in enumerate(sorted(undirected.keys()))}

    # mappa nodo-originale -> super-nodo corrente, raffinata a ogni livello
    partition = {n: n for n in undirected}
    graph = {u: dict(nbrs) for u, nbrs in undirected.items()}

    while True:
        node2com = _one_level(graph, m)
        # aggiorna la partizione degli originali
        partition = {orig: node2com[cur] for orig, cur in partition.items()}
        # se ogni nodo è già da solo o non cambia nulla, stop
        n_before = len(set(graph.keys()))
        n_after = len(set(node2com.values()))
        if n_after == n_before:
            break
        graph = _aggregate(graph, node2com)

    # rinumera le community come interi 0..k-1 per dimensione decrescente
    members: dict = defaultdict(list)
    for node, com in partition.items():
        members[com].append(node)
    ordered = sorted(members.values(), key=len, reverse=True)
    result: dict[str, int] = {}
    for idx, group in enumerate(ordered):
        for node in group:
            result[node] = idx
    return result


def modularity(undirected: dict, node2com: dict) -> float:
    m = 0.0
    for u in undirected:
        for v, w in undirected[u].items():
            if u <= v:
                m += w
    return _modularity(undirected, node2com, m) if m else 0.0


# --------------------------------------------------------------------------- #
# 3a. PageRank (grafo orientato, power iteration)
# --------------------------------------------------------------------------- #

def pagerank(directed: dict, damping: float = 0.85,
             max_iter: int = 100, tol: float = 1e-9) -> dict:
    nodes = list(directed.keys())
    n = len(nodes)
    if n == 0:
        return {}
    out_w = {u: sum(directed[u].values()) for u in nodes}
    rank = {u: 1.0 / n for u in nodes}

    for _ in range(max_iter):
        new = {u: (1.0 - damping) / n for u in nodes}
        dangling = damping * sum(rank[u] for u in nodes if out_w[u] == 0) / n
        for u in nodes:
            new[u] += dangling
        for u in nodes:
            if out_w[u] == 0:
                continue
            share = damping * rank[u] / out_w[u]
            for v, w in directed[u].items():
                new[v] += share * w
        diff = sum(abs(new[u] - rank[u]) for u in nodes)
        rank = new
        if diff < tol:
            break
    return rank


# --------------------------------------------------------------------------- #
# 3b. Betweenness centrality (Brandes, non orientato non pesato)
# --------------------------------------------------------------------------- #

def betweenness(undirected: dict) -> dict:
    cb = {n: 0.0 for n in undirected}
    for s in undirected:
        stack: list[str] = []
        pred: dict[str, list[str]] = {w: [] for w in undirected}
        sigma = {w: 0.0 for w in undirected}
        dist = {w: -1 for w in undirected}
        sigma[s] = 1.0
        dist[s] = 0
        queue = deque([s])
        while queue:
            v = queue.popleft()
            stack.append(v)
            for w in undirected[v]:
                if dist[w] < 0:
                    dist[w] = dist[v] + 1
                    queue.append(w)
                if dist[w] == dist[v] + 1:
                    sigma[w] += sigma[v]
                    pred[w].append(v)
        delta = {w: 0.0 for w in undirected}
        while stack:
            w = stack.pop()
            for v in pred[w]:
                delta[v] += (sigma[v] / sigma[w]) * (1.0 + delta[w])
            if w != s:
                cb[w] += delta[w]
    # grafo non orientato: ogni cammino contato due volte
    for w in cb:
        cb[w] /= 2.0
    return cb


# --------------------------------------------------------------------------- #
# 4. Link suggeriti (vicini in comune, deduzione strutturale)
# --------------------------------------------------------------------------- #

def suggest_links(undirected: dict, min_common: int = 2,
                  top: int = 15, exclude: set | None = None) -> list[dict]:
    """Coppie NON adiacenti con >= min_common vicini in comune, ordinate per
    score Adamic-Adar. Esclude le pagine auto-gestite per ridurre il rumore."""
    exclude = (exclude or set()) | _AUTO_PAGES
    candidates = [n for n in undirected if n not in exclude]
    nbrs = {n: set(undirected[n].keys()) for n in candidates}
    deg = {n: len(undirected[n]) for n in undirected}

    suggestions: list[dict] = []
    cand_sorted = sorted(candidates)
    for i, a in enumerate(cand_sorted):
        for b in cand_sorted[i + 1:]:
            if b in nbrs[a]:  # già collegate (in qualunque verso)
                continue
            common = nbrs[a] & nbrs[b]
            if len(common) < min_common:
                continue
            score = sum(1.0 / math.log(deg[c]) for c in common if deg[c] > 1)
            suggestions.append({
                "a": a, "b": b,
                "common": sorted(common),
                "n_common": len(common),
                "score": round(score, 4),
            })
    suggestions.sort(key=lambda s: (s["score"], s["n_common"]), reverse=True)
    return suggestions[:top]


# --------------------------------------------------------------------------- #
# Entry point: arricchisce `metrics` con tutte le analisi avanzate
# --------------------------------------------------------------------------- #

def enrich(nodes: dict, edge_counts: dict, exclude_auto: set | None = None) -> dict:
    g = build_graph(nodes, edge_counts)
    directed, undirected = g["directed"], g["undirected"]

    components = connected_components(undirected)
    comm = louvain_communities(undirected)
    pr = pagerank(directed)
    btw = betweenness(undirected)
    suggestions = suggest_links(undirected, exclude=exclude_auto)

    # membri per community (ordinati per pagerank interno)
    comm_members: dict[int, list[str]] = defaultdict(list)
    for node, cid in comm.items():
        comm_members[cid].append(node)
    for cid in comm_members:
        comm_members[cid].sort(key=lambda n: pr.get(n, 0), reverse=True)

    return {
        "components": components,
        "communities": comm,
        "community_members": dict(comm_members),
        "modularity": modularity(undirected, comm),
        "pagerank": pr,
        "betweenness": btw,
        "suggestions": suggestions,
        "top_pagerank": sorted(pr.items(), key=lambda x: x[1], reverse=True)[:10],
        "top_betweenness": sorted(btw.items(), key=lambda x: x[1], reverse=True)[:10],
    }
