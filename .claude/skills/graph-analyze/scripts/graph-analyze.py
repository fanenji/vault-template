#!/usr/bin/env python3
"""
graph-analyze.py — analisi diretta del grafo wiki.

Nodi: file .md sotto `wiki/`.
Edges: occorrenze di `[[wikilink]]` nei body.

Output:
  - Riepilogo console (sempre)
  - File `_notes/graph-analysis-<YYYY-MM-DD>.md` (salvo `--console-only`)

Porting fedele dello script originale `_system/scripts/graph-analyze.py`
con flag `--vault PATH` per usabilità da qualsiasi CWD.

Uso:
    python graph-analyze.py [--vault PATH] [--console-only]
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import _graph_metrics as gm

WIKI_DIR = "wiki"
NOTES_DIR = "_notes"
EXCLUDE_ORPHAN = {"index", "log", "overview", "glossary", "lint-report", "meetings-index"}
LINK_PATTERN = re.compile(r"\[\[([^\]|#]+)")
# Frontmatter YAML: escluso dall'estrazione dei link (come wiki-lint) — può
# contenere wikilink di metadato (es. source_path) che non sono edge del grafo.
FRONTMATTER_PATTERN = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)


def find_vault_root(start: Path) -> Path:
    cur = start.resolve()
    while True:
        if (cur / "wiki").is_dir() and (cur / ".llm-wiki").exists():
            return cur
        if cur.parent == cur:
            raise SystemExit(f"Non trovo una vault llm-wiki risalendo da {start}")
        cur = cur.parent


def collect_nodes(wiki_root: Path) -> dict[str, Path]:
    nodes: dict[str, Path] = {}
    for dirpath, _dirs, filenames in os.walk(wiki_root):
        for f in filenames:
            if f.endswith(".md"):
                full = Path(dirpath) / f
                stem = Path(f).stem.lower()
                nodes[stem] = full
    return nodes


def extract_edges(nodes: dict[str, Path]) -> tuple[defaultdict, defaultdict]:
    out_raw: defaultdict[str, int] = defaultdict(int)
    edge_counts: defaultdict[tuple[str, str], int] = defaultdict(int)

    for stem, filepath in nodes.items():
        try:
            content = filepath.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        body = FRONTMATTER_PATTERN.sub("", content, count=1)
        for t in LINK_PATTERN.findall(body):
            t_clean = t.lower().strip()
            out_raw[stem] += 1
            edge_counts[(stem, t_clean)] += 1

    return out_raw, edge_counts


def compute_metrics(
    nodes: dict[str, Path],
    edge_counts: defaultdict,
    out_raw: defaultdict,
) -> dict:
    node_set = set(nodes.keys())
    in_raw: defaultdict[str, int] = defaultdict(int)
    L_internal = 0
    L_broken = 0
    broken_set: set[str] = set()
    broken_refs: defaultdict[str, set[str]] = defaultdict(set)

    for (src, tgt), cnt in edge_counts.items():
        if tgt in node_set:
            L_internal += cnt
            in_raw[tgt] += cnt
        else:
            L_broken += cnt
            broken_set.add(tgt)
            broken_refs[tgt].add(src)

    N = len(nodes)
    L_total = sum(out_raw.values())
    K_out = L_total / N if N else 0
    K_in = L_internal / N if N else 0
    density = L_internal / (N * (N - 1)) if N > 1 else 0

    orphans = sorted(n for n in node_set if in_raw[n] == 0 and n not in EXCLUDE_ORPHAN)
    sinks = sorted(n for n in node_set if out_raw[n] == 0)

    top_in = sorted(in_raw.items(), key=lambda x: x[1], reverse=True)[:10]
    top_out = sorted(out_raw.items(), key=lambda x: x[1], reverse=True)[:10]

    return {
        "N": N,
        "L_total": L_total,
        "L_internal": L_internal,
        "L_broken": L_broken,
        "K_out": K_out,
        "K_in": K_in,
        "density": density,
        "orphans": orphans,
        "sinks": sinks,
        "top_in": top_in,
        "top_out": top_out,
        "broken_set": broken_set,
        "broken_refs": broken_refs,
    }


def interpret_density(density_pct: float) -> str:
    if density_pct < 1:
        return "sparse — typical for a focused research wiki with deep but narrow cross-referencing"
    if density_pct < 5:
        return "moderate — healthy level of internal linkage for a growing knowledge base"
    return "dense — highly interconnected; indicates mature, well-linked content"


def interpret_orphans(count: int) -> str:
    if count == 0:
        return "none — all pages are linked from at least one other page"
    if count <= 5:
        return f"few ({count}) — mostly recent additions or specialized pages; review for integration"
    return f"significant ({count}) — many unlinked pages; consider cross-linking or pruning"


def interpret_broken(count: int) -> str:
    if count == 0:
        return "none — all wikilinks resolve"
    if count <= 20:
        return f"low ({count}) — minor cleanup recommended"
    if count <= 50:
        return f"moderate ({count}) — should create stubs for frequently referenced missing pages"
    return f"high ({count}) — actionable; run /wiki-lint for detailed report"


def build_report(metrics: dict, today: str) -> str:
    N = metrics["N"]
    L_internal = metrics["L_internal"]
    L_broken = metrics["L_broken"]
    K_out = metrics["K_out"]
    K_in = metrics["K_in"]
    density = metrics["density"]
    density_pct = density * 100
    N_orphans = len(metrics["orphans"])
    N_sinks = len(metrics["sinks"])

    top_in_names = [f"[[{stem}]]" for stem, _ in metrics["top_in"][:3]]
    structure = (
        f"hub-and-spoke pattern with core hubs ({', '.join(top_in_names) or 'n/a'}) "
        "acting as central reference points, consistent with a curated research wiki"
    )

    lines: list[str] = []
    lines.append("---")
    lines.append("type: analysis")
    lines.append(f'title: "Graph Analysis — {today}"')
    lines.append("tags: [analysis, graph, metrics]")
    lines.append(f"created: {today}")
    lines.append(f"updated: {today}")
    lines.append("---")
    lines.append("")
    lines.append(f"# Graph Analysis — {today}")
    lines.append("")
    lines.append("## Metriche di base")
    lines.append("")
    lines.append("| Metrica | Valore |")
    lines.append("|---|---|")
    lines.append(f"| **N** (nodi / file .md) | {N} |")
    lines.append(f"| **L** (link interni validi) | {L_internal} |")
    lines.append(f"| **L rotti** (→ pagine mancanti) | {L_broken} |")
    lines.append(f"| **⟨K_out⟩** grado uscente medio | {K_out:.2f} |")
    lines.append(f"| **⟨K_in⟩** grado entrante medio | {K_in:.2f} |")
    lines.append(f"| **Densità** `d = L / N(N-1)` | {density:.6f} ({density_pct:.3f}%) |")
    lines.append(f"| Nodi orfani (in-degree = 0) | {N_orphans} |")
    lines.append(f"| Nodi sink (out-degree = 0) | {N_sinks} |")
    lines.append("")
    lines.append("## Hub principali (top 10 per in-degree)")
    lines.append("")
    lines.append("| Pagina | In-degree |")
    lines.append("|---|---|")
    for stem, deg in metrics["top_in"]:
        lines.append(f"| [[{stem}]] | {deg} |")
    lines.append("")
    lines.append("## Pagine più connesse in uscita (top 10 per out-degree)")
    lines.append("")
    lines.append("| Pagina | Out-degree |")
    lines.append("|---|---|")
    for stem, deg in metrics["top_out"]:
        lines.append(f"| [[{stem}]] | {deg} |")
    lines.append("")
    lines.append("## Lettura dei risultati")
    lines.append("")
    lines.append(f"- **Densità**: {interpret_density(density_pct)}")
    if top_in_names:
        lines.append(
            f"- **Hub dominanti**: {', '.join(top_in_names)} — "
            "these act as anchor pages that concentrate inbound references"
        )
    lines.append(f"- **Orfani**: {interpret_orphans(N_orphans)}")
    lines.append(f"- **Link rotti**: {interpret_broken(L_broken)}")
    lines.append(f"- **Struttura della rete**: {structure}")
    lines.append("")

    if metrics.get("deep"):
        lines.extend(build_deep_sections(metrics))

    return "\n".join(lines)


def build_deep_sections(metrics: dict) -> list[str]:
    """Sezioni avanzate (--deep): componenti, community, centralità, link suggeriti."""
    lines: list[str] = []

    # --- Componenti connesse -------------------------------------------------
    components = metrics["components"]
    lines.append("## Componenti connesse")
    lines.append("")
    if len(components) == 1:
        lines.append(f"Grafo connesso: un'unica componente da {len(components[0])} pagine.")
    else:
        islands = [c for c in components[1:]]
        lines.append(
            f"{len(components)} componenti — la principale ha {len(components[0])} pagine; "
            f"{len(islands)} isole scollegate:"
        )
        lines.append("")
        for comp in islands:
            members = ", ".join(f"[[{n}]]" for n in sorted(comp)[:8])
            extra = "…" if len(comp) > 8 else ""
            lines.append(f"- isola da {len(comp)}: {members}{extra}")
    lines.append("")

    # --- Community tematiche -------------------------------------------------
    members = metrics["community_members"]
    mod = metrics["modularity"]
    n_real = sum(1 for g in members.values() if len(g) >= 2)
    n_singletons = sum(1 for g in members.values() if len(g) == 1)
    lines.append("## Community tematiche (Louvain)")
    lines.append("")
    singleton_note = f" (+{n_singletons} pagine isolate)" if n_singletons else ""
    lines.append(
        f"{n_real} community emergenti dalla topologia dei link{singleton_note} "
        f"(modularità Q = {mod:.3f}). Le pagine-chiave sono le più centrali (PageRank) di ciascun gruppo:"
    )
    lines.append("")
    lines.append("| Cluster | Pagine | Pagine-chiave |")
    lines.append("|---|---|---|")
    for cid in sorted(members.keys()):
        group = members[cid]
        if len(group) < 2:
            continue
        key = ", ".join(f"[[{n}]]" for n in group[:4])
        lines.append(f"| #{cid} | {len(group)} | {key} |")
    lines.append("")

    # --- Centralità: hub globali e ponti ------------------------------------
    lines.append("## Centralità — hub globali e pagine-ponte")
    lines.append("")
    lines.append("**Hub globali (PageRank)** — importanza pesata anche dall'importanza di chi linka:")
    lines.append("")
    lines.append("| Pagina | PageRank |")
    lines.append("|---|---|")
    for stem, score in metrics["top_pagerank"][:8]:
        lines.append(f"| [[{stem}]] | {score:.4f} |")
    lines.append("")
    lines.append(
        "**Pagine-ponte (betweenness)** — stanno sui cammini fra gruppi diversi; "
        "rimuoverle frammenterebbe la wiki. Candidate a link ridondanti:"
    )
    lines.append("")
    lines.append("| Pagina | Betweenness |")
    lines.append("|---|---|")
    for stem, score in metrics["top_betweenness"][:8]:
        if score <= 0:
            continue
        lines.append(f"| [[{stem}]] | {score:.2f} |")
    lines.append("")

    # --- Link suggeriti ------------------------------------------------------
    suggestions = metrics["suggestions"]
    lines.append("## Link suggeriti (deduzione strutturale — da verificare)")
    lines.append("")
    if not suggestions:
        lines.append("_Nessuna coppia non collegata con abbastanza vicini in comune._")
    else:
        lines.append(
            "Coppie di pagine **non collegate** che condividono molti vicini: candidate "
            "a un wikilink. _Deduzione topologica, non un fatto wiki — valuta caso per caso._"
        )
        lines.append("")
        lines.append("| Pagina A | Pagina B | Vicini in comune | Score |")
        lines.append("|---|---|---|---|")
        for s in suggestions:
            common = ", ".join(f"[[{c}]]" for c in s["common"][:4])
            lines.append(f"| [[{s['a']}]] | [[{s['b']}]] | {common} ({s['n_common']}) | {s['score']} |")
    lines.append("")

    return lines


def print_summary(metrics: dict, today: str, output_path: Path | None = None) -> None:
    N = metrics["N"]
    L_internal = metrics["L_internal"]
    L_broken = metrics["L_broken"]
    K_out = metrics["K_out"]
    K_in = metrics["K_in"]
    density = metrics["density"]
    density_pct = density * 100
    N_orphans = len(metrics["orphans"])
    N_sinks = len(metrics["sinks"])

    print(f"Graph Analysis — {today}")
    print(f"N = {N}  |  L = {L_internal}  |  L_broken = {L_broken}")
    print(f"<K_out> = {K_out:.2f}  |  <K_in> = {K_in:.2f}  |  d = {density:.6f} ({density_pct:.3f}%)")
    print(f"Orphans: {N_orphans}  |  Sinks: {N_sinks}")
    if metrics.get("deep"):
        n_comp = len(metrics["components"])
        n_comm = sum(1 for g in metrics["community_members"].values() if len(g) >= 2)
        print(f"Components: {n_comp}  |  Communities: {n_comm}  |  Q = {metrics['modularity']:.3f}")
        print(f"Suggested links: {len(metrics['suggestions'])}")
    if output_path:
        print(f"Output: {output_path}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Directed graph analysis of the wiki link structure.")
    ap.add_argument("--vault", type=Path, default=None, help="Vault root (default: auto-detect)")
    ap.add_argument("--console-only", action="store_true",
                    help="Print summary only, do not write _notes/graph-analysis-<date>.md")
    ap.add_argument("--deep", action="store_true",
                    help="Analisi avanzata: community (Louvain), centralità (PageRank/betweenness), "
                         "componenti connesse, link suggeriti")
    ap.add_argument("--viz", action="store_true",
                    help="Emette _notes/graph/graph.json (contratto dati per HTML/Canvas). "
                         "Implica il calcolo avanzato come --deep.")
    args = ap.parse_args()

    vault_root = args.vault.resolve() if args.vault else find_vault_root(Path.cwd())
    wiki_root = vault_root / WIKI_DIR
    if not wiki_root.is_dir():
        print(f"Errore: {wiki_root} non esiste", file=sys.stderr)
        return 2

    nodes = collect_nodes(wiki_root)
    out_raw, edge_counts = extract_edges(nodes)
    metrics = compute_metrics(nodes, edge_counts, out_raw)

    enriched = None
    if args.deep or args.viz:
        enriched = gm.enrich(nodes, edge_counts, exclude_auto=EXCLUDE_ORPHAN)
    if args.deep:
        metrics["deep"] = True
        metrics.update(enriched)

    today = date.today().isoformat()
    output_path = vault_root / NOTES_DIR / f"graph-analysis-{today}.md"

    print_summary(metrics, today, None if args.console_only else output_path)

    if not args.console_only:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(build_report(metrics, today), encoding="utf-8")

    if args.viz:
        import json
        from _graph_emit import build_graph_json
        from _graph_html import render_html
        from _graph_canvas import build_canvas
        data = build_graph_json(nodes, edge_counts, enriched, vault_root=vault_root)
        viz_dir = vault_root / NOTES_DIR / "graph"
        viz_dir.mkdir(parents=True, exist_ok=True)
        (viz_dir / "graph.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        (viz_dir / "graph.html").write_text(render_html(data), encoding="utf-8")
        (viz_dir / "graph.canvas").write_text(
            json.dumps(build_canvas(data), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Viz: {viz_dir}/ (graph.json · graph.html · graph.canvas)  "
              f"— {data['meta']['nodes']} nodi, {data['meta']['edges']} archi")

    return 0


if __name__ == "__main__":
    sys.exit(main())
