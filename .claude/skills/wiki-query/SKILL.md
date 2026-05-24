---
name: wiki-query
description: Search the llm-wiki vault and answer a user question using existing pages, with [[wikilink]] citations. Use whenever the user asks something that needs looking up information from this vault (entities, concepts, sources, past research). Backed by QMD hybrid search (BM25 + vector + LLM reranking).
---

# wiki-query

Cerca nella wiki via [QMD](https://github.com/tobi/qmd) e sintetizza una risposta usando solo le informazioni effettivamente trovate, con citazioni `[[wikilink]]` per ogni claim sostantivo.

## Quando usarla

- L'utente chiede "cosa sappiamo su X?", "qual è il rapporto fra X e Y?", "trova le fonti che parlano di Z"
- Hai bisogno di contesto dalla wiki prima di rispondere a un'altra domanda
- L'utente vuole esplorare un argomento già documentato nella vault

**Non** usarla quando l'utente vuole creare/modificare pagine (usa `wiki-ingest`) o auditare la wiki (usa `wiki-lint`).

## Prerequisiti

- `qmd` installato globalmente (vedi `_system/scripts/init-vault.sh`)
- Indice QMD inizializzato in `.llm-wiki/qmd-index.sqlite`
- Almeno una pagina in `wiki/`

Se l'indice non esiste, suggerisci all'utente di eseguire `bash _system/scripts/init-vault.sh`.

**Primo avvio — download modelli**: QMD scarica due modelli GGUF alla prima esecuzione (~400 MB totali). Se la query va in timeout con "timed out downloading a model":
- Rilancia `qmd embed --db .llm-wiki/qmd-index.sqlite` su rete stabile, poi riprova.
- Come fallback immediato usa `--no-rerank` (salta il secondo modello, usa RRF score):
  ```bash
  qmd query "<domanda>" --db "$QMD_DB" --no-rerank --json -n 8
  ```

## Procedura

### 1. Retrieval

Determina il path del DB QMD relativo alla vault root:

```bash
QMD_DB=".llm-wiki/qmd-index.sqlite"
```

Esegui hybrid search (BM25 + vector + reranking):

```bash
qmd query "<domanda utente>" --db "$QMD_DB" --json -n 8
```

L'output JSON contiene `path`, `score`, `title`, `snippet` per ogni risultato. Filtra i risultati con `score < 0.3` (poco rilevanti).

**Se 0 risultati:**
- Prova `qmd vsearch "<domanda>"` (solo semantico, più tollerante)
- Se ancora 0, comunica all'utente che la wiki non ha contenuti pertinenti e suggerisci di fare un `deep-research` sull'argomento.

### 2. Lettura contenuto

Recupera i file rilevanti in batch:

```bash
qmd multi-get <path1> <path2> ... --db "$QMD_DB"
```

Oppure usa il tuo tool `Read` per ciascun path. Limita a 5-8 file per non saturare il context.

### 3. Sintesi

Componi la risposta seguendo queste regole:

- **Cita sempre con `[[wikilink]]`** quando menzioni un'entità o concetto che ha una pagina nella wiki (usa il basename senza `.md` e senza il path della cartella, es. `[[anthropic]]` non `[[entities/anthropic]]`).
- **Distingui** chiaramente fra (a) informazioni dalla wiki e (b) tue inferenze. Le inferenze vanno marcate "_(inferenza, non documentata nella wiki)_".
- **Non inventare** informazioni che non sono nei file letti. Se la wiki dice X e l'utente chiede Y che non c'è, dillo esplicitamente.
- **Lingua**: rispondi nella lingua dell'utente (auto-detect dalla domanda).
- **Citazioni contestuali**: se una pagina specifica supporta una claim, cita `[[nome-pagina]]` alla fine della frase. Esempio: "L'azienda è stata fondata nel 2021 [[anthropic]]."

### 4. Salvataggio (opzionale)

Se l'utente lo chiede esplicitamente ("salva questa risposta", "metti nella wiki") o se la risposta è ricca e probabilmente riutilizzabile, salvala in `wiki/queries/` con frontmatter:

```yaml
---
type: query
title: "<titolo breve della domanda>"
created: <YYYY-MM-DD>
origin: chat
query: "<domanda originale>"
tags: []
---
```

Nome file: kebab-case, max 50 char, suffisso data `-YYYY-MM-DD.md`. Es. `quanto-fattura-anthropic-2026-05-24.md`.

Dopo il save, aggiorna l'indice QMD:

```bash
qmd embed --update --db "$QMD_DB"
```

### 5. Log

Append al `wiki/log.md`:

```markdown
- YYYY-MM-DD HH:MM — query: "<domanda>" → <N> pagine consultate
```

## Output atteso

Una risposta in linguaggio naturale con:
1. La risposta diretta alla domanda
2. Citazioni `[[wikilink]]` inline o a fine periodo
3. Un breve elenco "**Fonti consultate**:" alla fine con i path delle pagine usate

## Esempio

**Utente**: "Cosa fa Anthropic in tema sicurezza?"

**Skill flow**:
```bash
qmd query "Anthropic sicurezza AI safety" --db .llm-wiki/qmd-index.sqlite --json -n 8
# → [{"path": "wiki/entities/anthropic.md", "score": 0.91, ...},
#    {"path": "wiki/concepts/constitutional-ai.md", "score": 0.78, ...},
#    {"path": "wiki/synthesis/ai-safety-landscape-2025.md", "score": 0.62, ...}]
qmd multi-get wiki/entities/anthropic.md wiki/concepts/constitutional-ai.md wiki/synthesis/ai-safety-landscape-2025.md
```

**Risposta**:
> [[anthropic]] è un'azienda di AI safety fondata nel 2021. Ha sviluppato [[constitutional-ai]] come metodo di allineamento basato su principi espliciti, alternativa a RLHF puro. La loro posizione nel landscape è documentata in [[ai-safety-landscape-2025]] dove appaiono come uno dei tre principali lab focalizzati sulla sicurezza.
>
> **Fonti consultate**:
> - `wiki/entities/anthropic.md`
> - `wiki/concepts/constitutional-ai.md`
> - `wiki/synthesis/ai-safety-landscape-2025.md`

## Note operative

- Se l'utente fa una domanda di follow-up nella stessa sessione, riusa il context già caricato invece di rieseguire QMD (a meno che la domanda richieda info diverse).
- Per domande aperte ("dimmi tutto su X"), fai 2-3 query QMD con angolature diverse e unisci i risultati deduplicando per path.
- Se trovi contraddizioni fra pagine, segnalalo all'utente e suggerisci `wiki-lint` per la review.
