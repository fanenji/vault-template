---
name: deep-research
description: Multi-query web research on a topic (Tavily with DuckDuckGo fallback), synthesize results into a wiki page with cross-references to existing wiki content (via QMD), save in wiki/queries/, optionally auto-ingest. Use when the user wants external/web research on a topic, especially one not already in the wiki.
---

# deep-research

Pipeline di ricerca web multi-query con sintesi LLM e cross-reference automatica con la wiki esistente. Porting fedele di `src/lib/deep-research.ts` adattato al pattern Python+agente.

## Quando usarla

- L'utente chiede ricerca esterna su un topic (web, non solo wiki)
- Topic non ancora coperto dalla wiki
- Bisogna integrare info recenti che vanno oltre i documenti già ingeriti
- L'utente passa esplicitamente `/deep-research <topic>` o equivalente

## Pre-requisiti

- Tavily API key in `.llm-wiki/secrets.json` (raccomandato) o `TAVILY_API_KEY` env. Senza, fallback automatico a DuckDuckGo.
- `pip install duckduckgo-search` per il fallback DDG.

## Procedura

### Step 1 — Multi-query expansion

Genera 3-5 query diverse dal topic dell'utente. Usa il template:

```bash
cat .claude/skills/deep-research/prompts/query_generation.md
```

Sostituisci `{{topic}}`, `{{num_queries}}` (default 3), `{{folder_context}}` se rilevante. Fai chiamata LLM (temperature ~0.3, max_tokens ~200), parsing: una query per riga.

In alternativa rapida (no LLM): se il topic è già una query keyword-rich, usa direttamente `[topic]`.

### Step 2 — Web search

Esegui:

```bash
python .claude/skills/deep-research/scripts/research.py search-multi \\
    "<query1>" "<query2>" "<query3>" --max-results 5
```

Output JSON con:
- `queries`: lista query usate
- `providers_used`: { tavily: N, duckduckgo: M } (DDG = fallback)
- `results`: lista deduplicata di `{title, url, snippet, source, query}`

Se 0 risultati → comunica all'utente che non si trova nulla e chiedi se vuole un altro fraseggio del topic.

### Step 3 — (Opzionale) Fetch contenuto pagine

Per arricchire i risultati, fetcha alcune URL con la skill `defuddle` se disponibile (estrae markdown pulito da HTML), oppure con `WebFetch`. Limita a 3-5 URL per non saturare il context. Aggiungi il markdown estratto al campo `snippet` (o crea `content`).

Se l'utente vuole risposta veloce, salta questo step — Tavily restituisce già snippet decenti.

### Step 4 — Cross-reference via QMD

Cerca nella wiki esistente pagine semanticamente vicine al topic:

```bash
qmd query "<topic>" --json -n 8   # qmd 2.5.2: indice locale .qmd/, esegui dalla vault root (no --db)
```

Estrai `path` e `title` dei top-K. Questi diventano `{{qmd_related_pages}}` nel prompt di sintesi.

Leggi anche `wiki/index.md` per il contesto completo della wiki.

### Step 5 — Sintesi LLM

Usa il template:

```bash
cat .claude/skills/deep-research/prompts/synthesis.md
```

Sostituisci:
- `{{topic}}` → topic originale dell'utente
- `{{wiki_index}}` → contenuto di `wiki/index.md`
- `{{qmd_related_pages}}` → lista markdown delle top-K pagine QMD (es. `- [[anthropic]] (score 0.91)`)
- `{{search_results}}` → numerated list: `[1] **Title** (source)\n<snippet>`, una per risultato

Fai chiamata LLM nella tua sessione. Temperature ~0.4, max_tokens ~6000.

Output: pagina markdown completa (senza frontmatter — quello lo aggiunge lo script).

Salva la sintesi in `/tmp/research-synth.md` e le references in `/tmp/research-refs.json`:

```json
[
  { "title": "...", "url": "...", "source": "..." },
  ...
]
```

### Step 6 — Save in wiki

```bash
REL_PATH=$(python .claude/skills/deep-research/scripts/research.py save-result \\
    --topic "<topic>" \\
    --synthesis-file /tmp/research-synth.md \\
    --references-json /tmp/research-refs.json)
```

Lo script:
- Crea `wiki/queries/research-<slug>-<YYYY-MM-DD>.md`
- Aggiunge frontmatter standard (`type: query`, `origin: deep-research`)
- Strip-pa `<think>/<thinking>` blocks dalla sintesi (replica safety del backend)
- Appende `## References` con le URL

### Step 7 — Aggiorna indice QMD

```bash
qmd update && qmd embed
```

Così la nuova pagina è subito search-able da `wiki-query`.

### Step 8 — (Opzionale) Auto-ingest

Per estrarre entities/concepts dalla sintesi e creare pagine collegate, invoca la skill `wiki-ingest` sul file salvato:

```
Invoca skill wiki-ingest con source_path = <vault_root>/<REL_PATH>
```

Questo trasforma una research page singola in un sottografo di entity/concept pages collegate al resto della wiki. Comportamento identico a `autoIngest(result)` del backend originale (`src/lib/deep-research.ts` riga 220).

### Step 9 — Report all'utente

- ✓ Path della research salvata
- 📊 N risultati web (tavily / ddg)
- 🔗 K cross-reference create con pagine esistenti
- Se Step 8: ✓ entity/concept pages create

## Esempio d'uso

**Utente**: "Fai una deep-research su 'mixture of experts in 2026'"

**Flow**:
1. Genera 3 query: `mixture of experts architecture 2026`, `MoE scaling laws recent`, `sparse models production deployment`
2. `research.py search-multi` con quelle query → 12 URL deduplicate
3. (Skip fetch step per velocità)
4. `qmd query "mixture of experts"` → trova `[[transformer]]`, `[[scaling-laws]]` esistenti
5. Sintesi LLM: pagina markdown con cross-ref `[[transformer]]` e `[[scaling-laws]]`
6. `research.py save-result` → `wiki/queries/research-mixture-of-experts-in-2026-2026-05-24.md`
7. `qmd update && qmd embed`
8. (Opzionale) invoco `wiki-ingest` sulla nuova pagina → crea `wiki/concepts/mixture-of-experts.md`, `wiki/entities/<azienda-citata>.md`, ecc.
9. Report.

## Note

- **Tavily quota**: piano free Tavily ha 1000 req/mese. Su HTTP 401/403/429 il fallback DDG entra in azione automaticamente. Avvisa l'utente quando succede (compare in stderr).
- **Lingua**: i template prompt sono in inglese ma chiedono all'LLM di rispondere nella lingua del topic. Se l'utente scrive in italiano, l'output sarà in italiano.
- **Deduplicazione**: lo script dedupa per URL esatto. Se vuoi de-dupe per dominio, post-processa il JSON.
- **Auto-ingest** (Step 8): è opzionale ma fortemente raccomandato — senza, la research page resta orfana e non viene scomposta in entity/concept. Decidi in base al richiesto dall'utente.

## Limiti

- **Solo Tavily + DDG**: il backend originale supportava anche SerpApi e SearXNG. Possono essere aggiunti a `web_search.py` con poca complessità.
- **Niente concorrenza queue**: deep-research è single-task per ora. Per batch (ricerca su 10 topic) chiama la skill in loop.
- **Niente cache**: ogni invocazione esegue search e LLM. Se l'utente ripete lo stesso topic in giornata, ri-paga. Aggiungere cache "topic+date → result" è feature futura.
