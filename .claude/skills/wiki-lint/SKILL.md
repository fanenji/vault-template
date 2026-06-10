---
name: wiki-lint
description: Run a health audit on the llm-wiki vault. Detects broken wikilinks, orphan pages, frontmatter/schema issues (duplicate slugs, broken related refs, type/folder mismatch), stale pending queues, missing pages (via QMD semantic dedup), and semantic problems like contradictions/staleness (via LLM on QMD-similar page pairs). Tracks run history with new/resolved diff. Use when the user asks to audit, lint, check the wiki health, or find issues.
---

# wiki-lint

Audit di salute della wiki in due passaggi:

1. **Check deterministici** — script Python `scripts/lint.py`. Veloce, no LLM, no rete (ma usa QMD locale per missing-page e similar-pairs). Mantiene uno **storico dei run** in `.llm-wiki/lint/history/` e riporta il **diff** (nuove/risolte) rispetto al run precedente.
2. **Check semantico** — l'agente legge integralmente le coppie di pagine semanticamente simili (trovate via QMD) per contraddizioni/duplicazioni, più un campione a rotazione per staleness e gap.

I report vanno in **`_notes/lint/`** — mai in `wiki/` (finirebbero nell'indice QMD e nel lint stesso).

## Quando usarla

- L'utente chiede "audita la wiki", "controlla i link rotti", "ci sono pagine orfane?", "ci sono contraddizioni?"
- Prima di un commit / merge importante
- Periodicamente (il plugin `llm-wiki-control` la schedula in automatico)
- **Incrementale post-ingest**: la skill `wiki-ingest` invoca `lint.py --pages <scritte>` dopo ogni finalize

## Procedura

### Step 1 — Check deterministici via script

Esegui (dalla vault root):

```bash
python .claude/skills/wiki-lint/scripts/lint.py --json
```

Output: lista JSON di oggetti `{type, severity, page, detail, affected_pages, suggestion, status}`. Il campo `status` vale `new` (issue assente nel run precedente) o `persistent`. Le issue `new` sono le più urgenti: probabilmente introdotte dall'ultimo ingest.

Tipi di issue rilevati dallo script:

| Tipo | Severity | Cosa rileva |
|---|---|---|
| `broken-link` | warning | `[[wikilink]]` che punta a una pagina inesistente (link a index/log/overview sono validi) |
| `duplicate-slug` | warning | Stesso basename in cartelle diverse — i wikilink risolvono in modo ambiguo (vietato da schema.md) |
| `frontmatter-ref` | warning | Slug in `related:` inesistente, o `source_path` che non esiste su disco |
| `missing-page` | warning/info | Broken link senza match semantico in QMD → vero stub da creare. Se ha match `≥0.85` → suggerimento di correggere il wikilink |
| `frontmatter` | warning/info | Frontmatter mancante, campi richiesti assenti, date non `YYYY-MM-DD` |
| `type-folder` | warning | `type:` incoerente con la cartella (es. entity in `concepts/`) |
| `naming` | info | Filename non kebab-case lowercase |
| `not-ingested` | info | File in `raw/sources/` non referenziato da nessuna pagina |
| `pending` | warning/info | Merge/review pendenti in `.llm-wiki/` (warning se più vecchi di `pending_max_age_days`, default 7) |
| `orphan` | info | Pagina senza inbound link da pagine di contenuto (overview non conta; self-link non contano) |
| `no-outlinks` | info | Pagina senza nessun `[[wikilink]]` in uscita |
| `similar-pair` | info | Coppia di pagine ad alta similarità QMD (solo con `--check similar-pairs`, input per lo Step 2) |

Flag utili:

```bash
--check structural|frontmatter|schema|missing-page|pending   # subset
--check similar-pairs    # opt-in (una vsearch per pagina): coppie per lo Step 2
--pages wiki/entities/a.md wiki/concepts/b.md   # lint incrementale (solo issue di quelle pagine; no storico)
--no-qmd                 # disabilita i check via QMD
--similarity 0.9         # threshold missing-page (default: config.json o 0.85)
--no-history             # non salvare il run / non calcolare il diff
--report-file _notes/lint/lint-report.md   # scrivi su file
```

**Soppressione**: una pagina con frontmatter `lint_ignore: [orphan, no-outlinks]` non viene segnalata per quei tipi (vedi schema.md). Il numero di issue soppresse appare nel summary del report.

**Storico**: ogni run completo viene salvato in `.llm-wiki/lint/history/<ts>.json` (retention: ultimi 30). Il report markdown include le sezioni "🆕 Nuove dal run precedente" e "✅ Risolte".

### Step 2 — Check semantico (delegato a te, agente)

Lo script non chiama LLM. Tu come agente esegui questo check in due parti:

**2a. Contraddizioni/duplicazioni — mirato sulle coppie simili.**

```bash
python .claude/skills/wiki-lint/scripts/lint.py --check similar-pairs --json
```

Per ogni `similar-pair`: leggi **entrambe le pagine integralmente** (`Read` o `qmd multi-get`) e verifica: claim in conflitto? contenuto duplicato da unire? Le contraddizioni vivono quasi sempre tra pagine che parlano della stessa cosa — confrontare le coppie ad alta similarità è molto più efficace che campionare 500 char da tutta la wiki.

**2b. Staleness e gap — campione a rotazione.**

Leggi `.llm-wiki/lint/last-sampled.json` (se esiste): `{ "<rel_path>": "<ISO timestamp ultimo sample>" }`. Scegli le ~15 pagine campionate meno di recente (o mai), leggine frontmatter + primi 500 char, e cerca:
- **stale**: info che appare obsoleta o superata
- **missing-page**: concetto molto referenziato ma senza pagina dedicata
- **suggestion**: domande o fonti da aggiungere

Aggiorna `last-sampled.json` con il timestamp per le pagine campionate: nel giro di pochi run l'intera wiki viene coperta, senza rileggere sempre le stesse.

**Formato output** per entrambe le parti:

```
---LINT: type | severity | Short title---
Description of the issue.
PAGES: page1.md, page2.md
---END LINT---
```

Types: `contradiction`, `duplicate`, `stale`, `missing-page`, `suggestion`. Severity: `warning`, `info`. Parsa i blocchi e aggiungili al report come `type: semantic`. Non inventare issue: se una coppia simile è legittima (es. entity + concept correlati), non segnalarla.

### Step 3 — Report unificato

Combina Step 1 (markdown con summary/diff già pronto da `--report-file`) e Step 2 (parsed) in un report finale in **`_notes/lint/lint-report.md`**:

```bash
python .claude/skills/wiki-lint/scripts/lint.py --report-file _notes/lint/lint-report.md
# poi appendi al file la sezione "## semantic" con le issue dello Step 2
```

Aggiorna `wiki/log.md`:

```markdown
- YYYY-MM-DD HH:MM — wiki-lint: <N warning> (<X nuove>, <Y risolte>), <M info>
```

Nel riassunto all'utente dai priorità alle issue `new` e ai `pending` vecchi.

## Modalità --fix (opzionale)

Se l'utente passa `--fix`:
- Per ogni `missing-page` con severity warning (vero stub): crea pagina vuota in `wiki/entities/<slug>.md` o `wiki/concepts/<slug>.md` (chiedi all'utente quale categoria), con frontmatter minimo e placeholder body. Decidi tu la cartella euristicamente dal nome (PascalCase / sembra entità → entities; altrimenti concepts).
- Per ogni `frontmatter` warning di "missing field": aggiungi i campi mancanti con valori sensati (`created: <oggi>`, `title: <titolo dedotto dal filename>`, ecc.).
- Per ogni `orphan`/`no-outlinks` **intenzionale** confermato dall'utente: aggiungi `lint_ignore: [<type>]` al frontmatter della pagina invece di lasciare che si ripresenti a ogni run.
- Per ogni `missing-page` info di suggerimento (semantica): **non** auto-correggere, mostra solo come suggerimento (rinominare wikilink è ad alto rischio).
- `duplicate-slug` e `type-folder`: **mai** auto-fix (rinomine/spostamenti rompono i wikilink) — proponi all'utente le opzioni.

Dopo `--fix`, esegui `qmd update && qmd embed` (dalla vault root) per riaggiornare l'indice.

## Test

```bash
cd .claude/skills/wiki-lint/tests && python3 -m unittest discover
```

## Errori comuni

- **`qmd: command not found`** → suggerisci `bash _system/scripts/init-vault.sh` o `npm install -g @tobilu/qmd`
- **indice QMD assente** (manca `.qmd/`) → `qmd init && qmd collection add ./wiki && qmd update && qmd embed` dalla vault root (primo embed lento, scarica modello). qmd 2.5.2 usa l'indice project-local `.qmd/`, non più `--db`.
- **Frontmatter parse warning su molte pagine** → forse la vault non aderisce ancora allo schema; suggerisci `--fix` o di aggiornare schema.md
- **Molte issue `persistent` ignorate da settimane** → proponi all'utente una sessione di triage: fix o `lint_ignore` esplicito, così il report torna a essere segnale.
