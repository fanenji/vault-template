# LLM Wiki Template

Vault Obsidian preconfigurata per essere gestita come knowledge base **LLM-driven**, derivata dal progetto [llm_wiki](https://github.com/nashsu/llm_wiki). Le funzionalità (ingest, chat, lint, deep-research, transcript, graph-analyze) sono implementate come **Agent Skills** invocabili da Claude Code, OpenCode, Pi e qualsiasi altro client compatibile, oppure direttamente da shell tramite gli script Python in `.claude/skills/*/scripts/`.

Il retrieval (search lessicale + semantico + reranking) è delegato a [QMD](https://github.com/tobi/qmd), un motore di ricerca locale che indicizza la cartella `wiki/`.

## Come usarlo come template

```bash
# 1. Clona / copia la cartella in una nuova posizione
cp -r /path/to/llm-wiki-template /path/to/my-new-wiki
cd /path/to/my-new-wiki

# 2. Setup dipendenze (markitdown, qmd, duckduckgo-search) e indice iniziale
bash _system/scripts/init-vault.sh

# 3. Apri la cartella in Obsidian (oppure ignora Obsidian e usa solo CLI/agente)
```

## Struttura

```
.
├── purpose.md          # Definisci gli obiettivi e lo scope della wiki
├── schema.md           # Regole strutturali (tipi pagina, frontmatter, naming)
├── raw/sources/        # Documenti originali (immutabili)
├── wiki/               # Pagine generate dall'LLM (Obsidian vault)
│   ├── index.md        # Catalogo pagine
│   ├── log.md          # Storico operazioni
│   ├── overview.md     # Sintesi globale (aggiornata da ingest)
│   ├── entities/       # Persone, organizzazioni, prodotti
│   ├── concepts/       # Teorie, metodi, tecniche
│   ├── sources/        # Riassunti delle fonti
│   ├── queries/        # Risposte salvate da chat e deep-research
│   └── synthesis/      # Analisi trasversali fra più fonti
├── _inbox/             # Bucket per materiale in ingresso (clippings, journal, transcription)
├── _notes/             # Note personali fuori dalla wiki knowledge base
├── .llm-wiki/          # Stato interno (queue ingest, cache SHA256, indice QMD)
├── .claude/
│   ├── skills/         # Skill richiamabili da Claude Code / OpenCode / Pi
│   │   ├── wiki-query/
│   │   ├── wiki-lint/
│   │   ├── wiki-ingest/
│   │   ├── deep-research/
│   │   ├── transcript/
│   │   └── graph-analyze/
│   └── commands/       # Slash command thin wrapper (es. /wiki-query)
├── .opencode/          # Mirror (symlink) per OpenCode
└── _system/            # Configurazione Obsidian + script vault
    ├── canvas/         # File .canvas (visual whiteboards, da popolare manualmente)
    ├── templates/      # Template Obsidian (da popolare manualmente)
    └── scripts/
        └── init-vault.sh
```

## Skill disponibili

| Skill | Cosa fa | Slash command |
|---|---|---|
| `wiki-query` | Cerca nella wiki via QMD e risponde a una domanda con citazioni `[[wikilink]]` | `/wiki-query` |
| `wiki-lint` | Audit della wiki: orphan, broken-link, frontmatter, contraddizioni semantiche | `/wiki-lint` |
| `wiki-ingest` | Ingest 2-step (analisi → generazione) di documenti da `raw/sources/` con cache SHA256 e coda persistente | `/wiki-ingest`, `/inbox-ingest` |
| `deep-research` | Ricerca web multi-query (Tavily + DuckDuckGo fallback) → sintesi → auto-ingest | `/deep-research` |
| `transcript` | Trascrizione audio/video locale via `mlx_whisper` con summary opzionale via LLM | `/transcript` |
| `graph-analyze` | Analisi del grafo wiki (nodi/edge/densità/orfani/hub) con report in `_notes/` | `/graph-analyze` |

Tutte le skill sono **portabili**: il loro stato risiede in `.claude/skills/<nome>/`, sono in markdown standard, e gli script Python in `scripts/` sono eseguibili indipendentemente da qualsiasi agente.

## Requisiti

**Core** (installati automaticamente da `_system/scripts/init-vault.sh`):
- Python 3.10+ con `markitdown[all]` — preprocessing documenti per `wiki-ingest`
- Python `duckduckgo-search` — fallback web search per `deep-research`
- Node.js 18+ con `@tobilu/qmd` (installato globalmente) — motore di retrieval

**Opzionali** (solo se usi le skill relative):
- Account [Tavily](https://tavily.com) → `deep-research` (senza, fallback su DuckDuckGo)
- `ffmpeg` (`brew install ffmpeg`) + `mlx-whisper` (`pip install mlx-whisper`) → `transcript` (richiede macOS Apple Silicon)

## Modello operativo

Le skill chiamano l'LLM **attraverso l'agente che le invoca** (Claude Code, OpenCode, ecc.): gli script Python si occupano di I/O, preprocessing documenti, parsing strutturato dell'output LLM, gestione cache/coda. Nessuna API key LLM da configurare nel template.

Per dettagli sull'architettura di ogni skill leggi `SKILL.md` nella relativa cartella.

## TODO / Future work

Funzionalità del backend originale `llm_wiki` non ancora portate nel template.

### Multimodal — image extraction & captioning

Il backend originale Tauri estrae immagini embedded da PDF/PPTX/DOCX in `wiki/media/<source-slug>/` (via pdfium-render lato Rust) e le caption con un modello VLM, popolando una cache SHA256-keyed in `.llm-wiki/image-caption-cache.json`. Le caption arricchiscono il testo passato all'LLM di ingest, migliorando la sintesi e preservando i riferimenti `![](path)` nelle pagine wiki generate.

**Stato nel template**: NON implementato. La skill `wiki-ingest` salta interamente questo step — le immagini embedded vengono ignorate e i riferimenti `![](url)` strippati dal testo passato al pipeline a 2 step.

**Per portarlo servono**:
- Estrazione PDF: `pdfimages` (Poppler) o `pdfplumber.images`, oppure `pymupdf` per qualità superiore.
- Estrazione DOCX: `python-docx` espone `document.part.related_parts` con i blob immagine.
- Estrazione PPTX: `python-pptx` con `slide.shapes` filtrati per `MSO_SHAPE_TYPE.PICTURE`.
- Captioning VLM: chiamate a un modello con vision (GPT-4o, Claude Opus 4.X, Gemini 2.5, ecc.) — anche qui delegato all'agente che invoca la skill, oppure script che parla a un endpoint locale (es. LLaVA via Ollama).
- Cache SHA256 sulle immagini per dedup cross-source (es. logo aziendale che ricorre in 30 PDF caption una volta sola).

**Punti di estensione previsti**:
- `_system/scripts/wiki-ingest/scripts/_image_extract.py` (da creare)
- `_system/scripts/wiki-ingest/scripts/_image_caption.py` (da creare)
- Update `SKILL.md` di `wiki-ingest` con Step 2.5 (extract) e 2.6 (caption) prima dello Step 3 (analysis).
- Cache file `.llm-wiki/image-caption-cache.json`.

### Altri TODO minori

- **Vector store custom dell'ingest** (LanceDB) — sostituito interamente da QMD nel template. La feature "dedup semantico durante ingest" via QMD `vsearch` è documentata nelle skill ma può essere migliorata.
- **Provider web search aggiuntivi** — backend originale supporta anche SerpApi e SearXNG. `web_search.py` può essere esteso facilmente.
- **Coda concorrente** — la `queue.py` corrente è single-task. Per ingest batch paralleli serve concurrency control.
- **Review queue UI** — il backend originale ha una review queue interattiva. Nel template le `REVIEW` blocks sono estratte da `finalize.py` ma ad oggi vengono solo riportate all'utente nella conversazione; non c'è uno store persistente.
