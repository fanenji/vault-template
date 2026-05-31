---
name: wiki-ingest
description: Ingest documents (PDF, DOCX, PPTX, XLSX, HTML, MD, TXT) into the llm-wiki vault using the 2-step chain-of-thought pipeline (analysis → generation). Handles SHA256 caching, persistent queue, sanitization, robust FILE-block parsing, page merging with existing wiki content, post-ingest QMD index update. Use when the user wants to import, ingest, or process new source files.
---

# wiki-ingest

Pipeline di ingest a 2 step (analisi → generazione) con porting fedele del backend originale `src/lib/ingest.ts`. L'LLM gira nella tua sessione di agente; gli script Python si occupano di:
- Preprocessing documenti (MarkItDown)
- Cache SHA256 (skip su file invariati)
- Coda persistente
- Parsing robusto FILE blocks (gestisce CRLF, troncamenti, code fence, case variants)
- Sanitization output LLM (3 fix ricorrenti per frontmatter corrotto)
- Page merge (array union + LLM body merge condizionato)
- Aggiornamento indice QMD post-ingest

## Quando usarla

- L'utente chiede di importare / ingerire / processare uno o più documenti
- File nuovi appaiono in `raw/sources/` o in `_inbox/`
- L'utente vuole rigenerare la wiki da una source aggiornata

## Pre-requisiti

```bash
pip install 'markitdown[all]'   # per preprocessing documenti
npm install -g @tobilu/qmd       # per indice search
bash scripts/init-vault.sh       # nella vault, una volta sola
```

## Procedura completa

Per OGNI file sorgente, esegui questi step in ordine.

### Step 0 — Coda (opzionale, per batch)

Se l'utente ti chiede di ingerire molti file (es. tutto `_inbox/` o `raw/sources/nuovi/`):

```bash
python .claude/skills/wiki-ingest/scripts/queue.py add <file1> <file2> ...
```

Poi processa uno per volta:

```bash
ITEM=$(python .claude/skills/wiki-ingest/scripts/queue.py next)
# ITEM è JSON: { id, source_path, status, ... }
# segui Step 1-7 sotto, poi:
python .claude/skills/wiki-ingest/scripts/queue.py mark <id> done
# o se fallisce:
python .claude/skills/wiki-ingest/scripts/queue.py mark <id> failed --error "..."
```

Se ingest singolo, salta lo Step 0.

### Step 1 — Cache check

```bash
python .claude/skills/wiki-ingest/scripts/cache.py check <source_path>
```

- Exit 0 + stampa lista files → **CACHE HIT**, salta tutto e riporta all'utente
- Exit 1 → **CACHE MISS**, prosegui

### Step 2 — Preprocessing

```bash
SOURCE_MD=$(python .claude/skills/wiki-ingest/scripts/preprocess.py <source_path>)
```

Questo converte PDF/DOCX/PPTX/XLSX/HTML/etc → markdown plain, troncato a 50k char. Salva l'output in un file temporaneo per i prossimi step (es. `/tmp/source.md`).

### Step 3 — Step 1 LLM: Analysis

Leggi il prompt template:

```bash
cat .claude/skills/wiki-ingest/prompts/analysis.md
```

Sostituisci le variabili `{{...}}`:
- `{{source_filename}}` → basename del file (es. `paper.pdf`)
- `{{source_content}}` → contenuto preprocessato (Step 2)
- `{{folder_context}}` → path della cartella sorgente (es. `_inbox/clippings`) se rilevante
- `{{purpose}}` → contenuto di `purpose.md`
- `{{index}}` → contenuto di `wiki/index.md`

**Fai la chiamata LLM nella tua sessione** con temperature bassa (~0.1), reasoning OFF (per modelli che lo supportano), max_tokens ~4096.

Output atteso: testo strutturato in markdown (Key Entities, Key Concepts, Main Arguments, ecc.). Salva in `/tmp/analysis.md`.

### Step 4 — Step 2 LLM: Generation

Leggi il prompt template:

```bash
cat .claude/skills/wiki-ingest/prompts/generation.md
```

Sostituisci:
- `{{source_filename}}`, `{{source_basename}}` (filename senza estensione)
- `{{today}}` → data odierna `YYYY-MM-DD`
- `{{purpose}}`, `{{schema}}` → contenuti di `purpose.md` e `schema.md`
- `{{index}}`, `{{overview}}` → contenuti di `wiki/index.md` e `wiki/overview.md`

**User message** deve contenere:
1. Riferimento al file: `Source document to process: **<filename>**`
2. Reminder: "Stage 1 Analysis is CONTEXT only, do NOT echo"
3. Il contenuto di `/tmp/analysis.md` (Step 3)
4. Il contenuto preprocessato di `/tmp/source.md` (Step 2)
5. Trigger: "Now emit the FILE blocks... Your response MUST begin with `---FILE:`"

**Fai la chiamata LLM** con temperature 0.1, max_tokens ~8192.

Output atteso: stringa che inizia con `---FILE:` e contiene N blocchi FILE + opzionali blocchi REVIEW. Salva in `/tmp/generation.txt`.

### Step 5 — Finalize (parse + sanitize + write)

```bash
python .claude/skills/wiki-ingest/scripts/finalize.py \
    --source <source_path> \
    --generation-file /tmp/generation.txt
```

Output JSON con:
- `written_paths`: file scritti in `wiki/`
- `warnings`: warning del parser/sanitizer
- `reviews`: blocchi REVIEW estratti (passa al review queue se l'utente lo vuole)
- `merge_needed`: lista pagine che necessitano LLM body merge (vedi Step 6)
- `hard_failures`: errori FS irrecuperabili
- `archived_source`: path (rel) del sorgente spostato in `raw/sources/`, oppure `null`

`finalize.py` si occupa automaticamente di:
- Sanitize (rimuove code fence, ripara frontmatter)
- Path safety check (reject `..`, absolute paths, traversal)
- Append a `wiki/log.md`
- Overwrite di `wiki/index.md` e `wiki/overview.md`
- Save cache SHA256 (se nessun hard failure)
- `qmd update && qmd embed` (re-indicizza + embedda i nuovi file; indice locale `.qmd/` di qmd 2.5.2)
- **Archiviazione sorgente**: su ingest pienamente riuscito sposta l'originale da `_inbox/` a `raw/sources/` (move). Se è già sotto `raw/sources/` non lo tocca. Disattivabile con `--no-archive`. **Non devi spostare il file a mano**: lo fa lo script.

### Step 6 — Page merge LLM (se `merge_needed` non vuoto)

Per ogni elemento in `merge_needed` (significa: la pagina esisteva con body diverso, finalize ha applicato solo array-field union):

1. Leggi `.claude/skills/wiki-ingest/prompts/merge.md`
2. Sostituisci `{{existing_content}}`, `{{incoming_content}}`, `{{source_filename}}`
3. Chiama l'LLM
4. Scrivi il risultato sul path con `apply_llm_merge_result` (importa da `_merge_pages.py`) per applicare i locked fields + sanity check

Snippet rapido:

```python
from _merge_pages import apply_llm_merge_result
# llm_output = risposta LLM
# existing = leggi pagina dal disco prima del fix
final = apply_llm_merge_result(llm_output, existing, incoming)
write_file(rel_path, final)
```

(Se vuoi saltare lo step 6 per ora, le pagine resteranno con array-union + new body — coerenti, ma con meno coesione del merge LLM. Va segnalato all'utente.)

### Step 7 — Report all'utente

Riporta:
- ✓ N file scritti
- ⚠ M warnings (cita i più importanti)
- 📝 R review items (chiedi all'utente come gestirli)
- 🔀 K page merge LLM eseguiti
- Cache HIT/MISS

## Esempio d'uso (singolo file)

```
Utente: "Ingerisci _inbox/transformer-paper.pdf nella wiki"

Skill:
1. cache.py check _inbox/transformer-paper.pdf  → MISS
2. preprocess.py _inbox/transformer-paper.pdf > /tmp/source.md
3. Leggo prompts/analysis.md, sostituisco, chiamata LLM → /tmp/analysis.md
4. Leggo prompts/generation.md, sostituisco, chiamata LLM → /tmp/generation.txt
5. finalize.py --source _inbox/transformer-paper.pdf --generation-file /tmp/generation.txt
   → { written_paths: [wiki/sources/transformer-paper.md, wiki/entities/vaswani-et-al.md, ...],
       warnings: [], reviews: [], merge_needed: [...],
       archived_source: "raw/sources/transformer-paper.pdf" }
   (finalize.py ha già spostato il sorgente da _inbox a raw/sources)
6. Per ogni merge_needed: chiamata LLM merge → write
7. Report all'utente (cita `archived_source`).
```

## Note importanti

- **Archiviazione automatica del sorgente**: `finalize.py` sposta da solo `_inbox/<file>` → `raw/sources/<file>` su ingest riuscito (`raw/` è la "source of truth" immutabile). **Non spostarlo a mano.** Per saltare l'archiviazione usa `finalize.py --no-archive`.
- **NON ingerire da `raw/sources/`** direttamente se il file viene da `_inbox/` (verrebbe processato sul posto senza spostamento).
- **Lingua**: i prompt sono in inglese ma l'output rispetta la lingua della source (rule built-in). Se la wiki è multilingua e l'utente vuole forzare l'italiano, aggiungi alla user message: `Output language: Italian.`
- **Batch grossi** (>10 file): processa uno per volta, non parallelizzare. Il pipeline a 2 step satura il context; ingest paralleli rischiano errori.
- **Idempotente**: rilancia la skill su un file già ingerito → la cache restituisce HIT e nulla viene riscritto. Forza re-ingest con `python cache.py remove <filename>`.
- **Recovery**: se l'ingest crasha a metà, la coda mantiene lo stato (`queue.py reset-failed` per riprovare). Le pagine scritte parzialmente restano (sono coerenti perché ogni FILE block è atomico).

## Limiti correnti

- **Image extraction**: il backend originale estrae immagini embedded da PDF/PPTX/DOCX. Per il template Python iniziale **NON è implementato**. Se ti serve, considera di chiamare `pdfimages` (poppler) o `pdfplumber` come post-step prima di Step 3.
- **Multimodal captioning**: idem, non implementato. Pannelo per estensione futura.
