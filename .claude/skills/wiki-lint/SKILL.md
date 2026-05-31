---
name: wiki-lint
description: Run a health audit on the llm-wiki vault. Detects broken wikilinks, orphan pages, frontmatter issues, missing pages (via QMD semantic dedup), and semantic problems like contradictions/staleness/missing topics (via LLM). Use when the user asks to audit, lint, check the wiki health, or find issues.
---

# wiki-lint

Audit di salute della wiki in due passaggi:

1. **Check deterministici** — script Python `scripts/lint.py` (porting fedele di `src/lib/lint.ts`). Veloce, no LLM, no rete (ma usa QMD locale per il check missing-page).
2. **Check semantico** — l'agente legge un sample delle pagine e identifica contraddizioni, claim obsoleti, gap concettuali.

## Quando usarla

- L'utente chiede "audita la wiki", "controlla i link rotti", "ci sono pagine orfane?", "ci sono contraddizioni?"
- Prima di un commit / merge importante
- Periodicamente, per manutenzione

## Procedura

### Step 1 — Check deterministici via script

Esegui:

```bash
python .claude/skills/wiki-lint/scripts/lint.py --json
```

Output: lista JSON di oggetti `{type, severity, page, detail, affected_pages, suggestion}`.

Tipi di issue rilevati dallo script:

| Tipo | Severity | Cosa rileva |
|---|---|---|
| `orphan` | info | Pagina senza inbound link (nessun'altra pagina la cita) |
| `broken-link` | warning | `[[wikilink]]` che punta a una pagina inesistente |
| `no-outlinks` | info | Pagina senza nessun `[[wikilink]]` in uscita |
| `frontmatter` | warning | Frontmatter mancante o campi richiesti assenti (per type) |
| `missing-page` | warning/info | Broken link che NON ha match semantico in QMD → vero stub da creare. Se ha match `≥0.85` → suggerimento di correggere il wikilink |

Flag utili:

```bash
--check structural       # solo orphan/broken-link/no-outlinks
--check frontmatter      # solo frontmatter
--check missing-page     # solo missing-page
--no-qmd                 # disabilita il check semantico via QMD
--similarity 0.9         # threshold per missing-page (default 0.85)
--report-file wiki/lint-report.md  # scrivi su file
```

### Step 2 — Check semantico (delegato a te, agente)

Lo script non chiama LLM. Tu come agente esegui questo check:

1. Leggi (con `Read` o `qmd multi-get`) il contenuto delle pagine principali della wiki. Per vault grandi (>50 pagine) prendi un sample stratificato: tutte le `entities/`, top-N `concepts/` per inbound count, tutte le `synthesis/`.
2. Per ciascuna pagina estrai frontmatter + primi 500 char del body (replica esatta dello stage-1 di `runSemanticLint` originale).
3. Componi un prompt che chiede di identificare:
   - **contradiction**: due+ pagine con claim conflittuali
   - **stale**: info che appare obsoleta o superata
   - **missing-page**: concetto molto referenziato ma senza pagina dedicata
   - **suggestion**: domande o fonti da aggiungere
4. Output atteso dall'LLM: blocchi nel formato

    ```
    ---LINT: type | severity | Short title---
    Description of the issue.
    PAGES: page1.md, page2.md
    ---END LINT---
    ```

5. Parsa i blocchi e aggiungi al report come `type: semantic, severity: warning|info`.

Esempio prompt (adatta in italiano se la wiki è in italiano):

> Sei un wiki quality analyst. Rivedi i seguenti riassunti di pagine wiki e identifica problemi reali (non inventare). Per ogni issue usa esattamente questo formato:
>
> `---LINT: <type> | <severity> | <titolo breve>---`
> `<descrizione>`
> `PAGES: page1.md, page2.md`
> `---END LINT---`
>
> Types: `contradiction`, `stale`, `missing-page`, `suggestion`.
> Severity: `warning`, `info`.
>
> ## Wiki Pages
> {summaries}

### Step 3 — Report unificato

Combina i risultati di Step 1 (JSON) e Step 2 (parsed) in un report markdown finale. Scrivi in `wiki/lint-report.md` se l'utente lo chiede, altrimenti stampa.

Aggiorna `wiki/log.md`:

```markdown
- YYYY-MM-DD HH:MM — wiki-lint: <N warning>, <M info>
```

## Modalità --fix (opzionale)

Se l'utente passa `--fix`:
- Per ogni `missing-page` con severity warning (vero stub): crea pagina vuota in `wiki/entities/<slug>.md` o `wiki/concepts/<slug>.md` (chiedi all'utente quale categoria), con frontmatter minimo e placeholder body. Decidi tu la cartella euristicamente dal nome (PascalCase / sembra entità → entities; altrimenti concepts).
- Per ogni `frontmatter` warning di "missing field": aggiungi i campi mancanti con valori sensati (`created: <oggi>`, `title: <titolo dedotto dal filename>`, ecc.).
- Per ogni `missing-page` info di suggerimento (semantica): **non** auto-correggere, mostra solo come suggerimento all'utente (rinominare wikilink è ad alto rischio).

Dopo `--fix`, esegui `qmd update && qmd embed` (dalla vault root) per riaggiornare l'indice.

## Esempio d'uso

**Utente**: "Fai un audit della wiki"

**Skill flow**:
1. `python .claude/skills/wiki-lint/scripts/lint.py --json` → 23 issue
2. Sample 30 pagine, build prompt, esegui semantic check → 4 issue
3. Compongo report markdown con 27 issue totali
4. Stampo a video + chiedo se salvare in `wiki/lint-report.md`
5. Append log

## Errori comuni

- **`qmd: command not found`** → suggerisci `bash _system/scripts/init-vault.sh` o `npm install -g @tobilu/qmd`
- **indice QMD assente** (manca `.qmd/`) → `qmd init && qmd collection add ./wiki && qmd update && qmd embed` dalla vault root (primo embed lento, scarica modello). qmd 2.5.2 usa l'indice project-local `.qmd/`, non più `--db .llm-wiki/qmd-index.sqlite`.
- **Frontmatter parse warning su molte pagine** → forse la vault non aderisce ancora al schema; suggerisci `--fix` o di aggiornare schema.md
