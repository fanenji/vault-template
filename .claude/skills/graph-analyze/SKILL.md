---
name: graph-analyze
description: Analyze the wiki as a directed graph (pages = nodes, [[wikilinks]] = edges). Computes node/edge counts, degree, density, orphans, sinks, broken links, top hubs. With --deep also runs community detection (Louvain), centrality (PageRank + betweenness/bridge pages), connected components, and suggested missing links — all from curated wikilinks, no LLM, stdlib only. Saves a structured report in _notes/graph-analysis-YYYY-MM-DD.md. Use when the user asks for wiki graph metrics, link analysis, thematic clusters, hub/bridge pages, or structural health overview.
---

# graph-analyze

Analisi del grafo orientato della wiki: ogni `.md` in `wiki/` è un nodo, ogni `[[wikilink]]` è un arco diretto. Calcola metriche di degree distribution, densità, broken links, hub principali. Output: riepilogo console + report markdown in `_notes/`.

## Quando usarla

- L'utente chiede "quanto è interconnessa la wiki?", "quali pagine sono hub?", "ci sono molti orfani?"
- Periodicamente (es. settimanale) per monitorare l'evoluzione del grafo
- Pre / post grandi ingest, per misurare l'impatto strutturale
- **Analisi avanzata (`--deep`)**: l'utente chiede "quali sono i temi/cluster della wiki?", "quali pagine fanno da ponte?", "quali pagine andrebbero collegate?", "ci sono isole scollegate?"

## Procedura

```bash
python .claude/skills/graph-analyze/scripts/graph-analyze.py [--console-only] [--deep]
```

Lo script:
1. Cammina ricorsivamente `wiki/` raccogliendo i nodi (file .md, indicizzati per stem lowercase)
2. Estrae i `[[wikilink]]` dai body
3. Distingue link interni validi (target esiste) da broken
4. Calcola: N, L_internal, L_broken, ⟨K_out⟩, ⟨K_in⟩, densità, orfani, sink, top-10 hub in/out
5. Stampa riepilogo console
6. (Salvo `--console-only`) scrive `_notes/graph-analysis-<YYYY-MM-DD>.md` con il report completo

**Output console (sempre)**:
```
Graph Analysis — 2026-05-24
N = 142  |  L = 387  |  L_broken = 12
<K_out> = 2.81  |  <K_in> = 2.73  |  d = 0.019345 (1.935%)
Orphans: 8  |  Sinks: 15
Output: /vault/_notes/graph-analysis-2026-05-24.md
```

**Output file** (solo senza `--console-only`):
- Frontmatter `type: analysis`, tag `[analysis, graph, metrics]`
- Tabella "Metriche di base"
- Tabella "Hub principali" (top-10 per in-degree)
- Tabella "Pagine più connesse in uscita" (top-10 per out-degree)
- Sezione "Lettura dei risultati" con interpretazione qualitativa di densità, orfani, broken link

## Analisi avanzata (`--deep`)

Con `--deep` lo script calcola, **riusando gli stessi wikilink** (nessuna chiamata LLM, nessuna dipendenza esterna — logica in `scripts/_graph_metrics.py`), quattro analisi aggiuntive accodate al report e riassunte in console:

1. **Componenti connesse** — isole di conoscenza nella proiezione non orientata. Segnala se la wiki è un unico tessuto o un arcipelago, elencando le isole scollegate.
2. **Community tematiche (Louvain)** — clusterizza le pagine in vicinati densamente connessi (i temi *emergenti*, non quelli delle cartelle), con valore di modularità Q e pagine-chiave per cluster (le più centrali per PageRank).
3. **Centralità** — **PageRank** (importanza globale, pesata dall'importanza di chi linka) e **betweenness/Brandes** (pagine-**ponte** sui cammini fra cluster: rimuoverle frammenterebbe la wiki).
4. **Link suggeriti** — coppie di pagine **non collegate** con molti vicini in comune (score Adamic-Adar): candidate a un wikilink. **Marcati come deduzione strutturale da verificare, mai come fatto wiki** (coerente con l'epistemic-hygiene del progetto). Le pagine auto-gestite (`index`, `log`, …) sono escluse.

Costo: a ~200 nodi è istantaneo. Le complessità (coppie O(N²), Brandes O(N·E)) sono pensate per questa scala; un cutoff per-cluster va introdotto solo se la wiki cresce di un ordine di grandezza.

## Flag

- `--console-only` — stampa riepilogo ma non scrive il file
- `--deep` — abilita l'analisi avanzata (community, centralità, componenti, link suggeriti)
- `--viz` — emette le visualizzazioni in `_notes/graph/` (`graph.json` + `graph.html` + `graph.canvas`); implica il calcolo avanzato come `--deep`
- `--vault PATH` — usa un vault diverso da quello auto-detected

## Visualizzazione (`--viz`)

Con `--viz` lo script scrive tre file in `_notes/graph/` (fuori dall'indice QMD):

- **`graph.json`** — contratto dati (logica in `_graph_emit.py`, stdlib): nodi con `type` (dedotto dalla cartella `wiki/<tipo>s/`), `label` (title), flag `structural`, `linkCount`, `community`, `pagerank`, `betweenness`, posizione `x`/`y` (layout community-clustered deterministico); archi non orientati unici con `weight` (molteplicità wikilink); `communities` e `insights` (bridges/suggested/isolated).
- **`graph.html`** — visualizzazione **interattiva self-contained** (`_graph_html.py`): Canvas-2D con pan/zoom, hover-highlight dei vicini, ricerca, toggle colore tipo/community e i filtri del riferimento (hide structural/isolated, max-links, per-type, reset). Tutto inline, nessuna risorsa remota. Si apre in un browser; **in Obsidian (obsidian-html-plugin) serve Unrestricted mode** per eseguire il JS.
- **`graph.canvas`** — Obsidian Canvas nativo (`_graph_canvas.py`): nodi `text` con `[[wikilink]]` (cliccabili), raggruppati per community, colorati per tipo, dimensionati per grado. I filtri sono applicati a generazione (default: nascondi strutturali).

Dettagli e piano: `GraphViz_Spec_Plan.md`.

## Interazione con altre skill

- Dopo `wiki-ingest` su molti file: usa `graph-analyze` per misurare l'impatto sul grafo
- Per fix puntuali sui broken link: passa al follow-up con `wiki-lint --check structural`
- Il report `_notes/graph-analysis-*.md` finisce nella personal area, non è parte della wiki — non viene letto da `wiki-query`/`qmd embed`
- **Schedulazione**: il plugin `llm-wiki-control` può eseguire `graph-analyze --deep` periodicamente (Settings → "Schedulazione graph-analyze", default settimanale, stesso meccanismo del lint schedulato). È deterministico/senza LLM, quindi gira senza costo token.

## Note

- **Case-insensitive**: i nomi pagina sono normalizzati lowercase, coerente con il resto delle skill.
- **Exclude orphan list**: `index`, `log`, `overview`, `glossary`, `lint-report`, `meetings-index` sono esclusi dagli "orfani" perché auto-gestiti / strutturali.
- **Dipendenze**: zero — solo stdlib Python (incluse community/centralità in `_graph_metrics.py`).
- **Performance**: base O(N) sui file (<1s su 1000 pagine). Con `--deep` resta istantaneo nell'ordine delle centinaia di nodi.
- **Test**: `.claude/skills/graph-analyze/tests/test_graph_metrics.py` (unittest stdlib, grafi a risultato noto). Eseguire dopo ogni modifica agli algoritmi: `cd .../graph-analyze/tests && python3 -m unittest discover`.

## Esempio d'uso

**Utente**: "Fai un'analisi del grafo della wiki"

**Skill flow**:
```bash
python .claude/skills/graph-analyze/scripts/graph-analyze.py          # metriche di base
python .claude/skills/graph-analyze/scripts/graph-analyze.py --deep   # + cluster, ponti, link suggeriti
```

Output console + file `_notes/graph-analysis-2026-05-24.md` creato.

Riporta all'utente il riepilogo + path del file generato + 1-2 osservazioni qualitative. Con `--deep`, evidenzia i cluster tematici emersi, le pagine-ponte e — separandoli nettamente come **suggerimenti da verificare** — i link mancanti proposti.
