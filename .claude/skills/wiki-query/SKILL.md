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
- Indice QMD locale `.qmd/` inizializzato (creato da `init-vault.sh` via `qmd init` + `qmd collection add ./wiki`)
- Almeno una pagina in `wiki/`

> **qmd 2.5.2**: l'indice è **project-local** (`.qmd/`, discovery dal cwd) — esegui sempre `qmd` dalla **vault root**. Il vecchio flag `--db .llm-wiki/qmd-index.sqlite` non esiste più (è ignorato): **non usarlo**.

Se l'indice non esiste (manca `.qmd/`), suggerisci all'utente di eseguire `bash _system/scripts/init-vault.sh`.

**Primo avvio — download modelli**: QMD scarica due modelli GGUF alla prima esecuzione (~400 MB totali). Se la query va in timeout con "timed out downloading a model":
- Rilancia `qmd update && qmd embed` su rete stabile, poi riprova.
- Come fallback immediato usa `--no-rerank` (salta il secondo modello, usa RRF score):
  ```bash
  qmd query "<domanda>" --no-rerank --json -n 8
  ```

## Procedura

### 1. Retrieval

Esegui hybrid search (BM25 + vector + reranking) dalla vault root:

```bash
qmd query "<domanda utente>" --json -n 8
```

L'output JSON contiene `path`, `score`, `title`, `snippet` per ogni risultato. Filtra i risultati con `score < 0.3` (poco rilevanti).

**Se 0 risultati:**
- Prova `qmd vsearch "<domanda>"` (solo semantico, più tollerante)
- Se ancora 0, comunica all'utente che la wiki non ha contenuti pertinenti e suggerisci di fare un `deep-research` sull'argomento.

### 2. Lettura contenuto

Recupera i file rilevanti in batch:

```bash
qmd multi-get <path1> <path2> ...
```

Oppure usa il tuo tool `Read` per ciascun path. Limita a 5-8 file per non saturare il context.

### 3. Sintesi

> **REGOLA FONDAMENTALE — epistemic hygiene**
>
> Ogni affermazione nella risposta deve rientrare in una delle due categorie seguenti, **mai mescolate implicitamente**:
>
> | Categoria | Fonte | Marcatura richiesta |
> |---|---|---|
> | **Fatto wiki** | Presente letteralmente o parafrasabile senza gap logici dai file letti | `[[wikilink]]` con citazione della pagina |
> | **Deduzione** | Inferita dal modello per analogia, generalizzazione o ragionamento | `_(deduzione: ...)_` con la premessa esplicitata |
>
> **È vietato presentare una deduzione come fatto wiki.** Se la wiki parla di X e l'utente chiede Y, e Y si può dedurre da X per analogia, quella deduzione va **sempre** esplicitata come tale — anche se sembra ovvia.
>
> **Segnale di allarme**: se stai per scrivere qualcosa che non puoi citare con un `[[wikilink]]` e non è una deduzione esplicitata, **non scriverlo**. Di' invece: "La wiki non contiene informazioni su questo aspetto specifico."

Componi la risposta seguendo queste regole:

- **Cita sempre con `[[wikilink]]`** quando menzioni un'entità o concetto che ha una pagina nella wiki (usa il basename senza `.md` e senza il path della cartella, es. `[[anthropic]]` non `[[entities/anthropic]]`).
- **Fatti wiki**: ogni claim sostantivo deve avere un `[[wikilink]]` di supporto. Se non riesci a citare una pagina specifica, il claim non è un fatto wiki.
- **Deduzioni**: ogni inferenza, analogia o generalizzazione **deve** essere marcata esplicitamente con `_(deduzione: <premessa usata>)_`. Esempio: "È probabile che il progetto usi lo stesso approccio _(deduzione: per analogia con [[progetto-simile]] che segue lo stesso pattern)_."
- **Gap espliciti**: se la wiki non contiene l'informazione richiesta, dillo chiaramente: "La wiki non documenta X. [Suggerisco `deep-research` per approfondire.]"
- **Non colmare i gap silenziosamente**: è preferibile una risposta parziale con lacune dichiarate a una risposta completa con deduzioni non marcate.
- **Lingua**: rispondi nella lingua dell'utente (auto-detect dalla domanda).
- **Citazioni contestuali**: cita `[[nome-pagina]]` alla fine della frase che il contenuto supporta. Esempio: "L'azienda è stata fondata nel 2021 [[anthropic]]."

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

Dopo il save, aggiorna l'indice QMD (dalla vault root):

```bash
qmd update && qmd embed
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
qmd query "Anthropic sicurezza AI safety" --json -n 8
# → [{"path": "wiki/entities/anthropic.md", "score": 0.91, ...},
#    {"path": "wiki/concepts/constitutional-ai.md", "score": 0.78, ...},
#    {"path": "wiki/synthesis/ai-safety-landscape-2025.md", "score": 0.62, ...}]
qmd multi-get wiki/entities/anthropic.md wiki/concepts/constitutional-ai.md wiki/synthesis/ai-safety-landscape-2025.md
```

**Risposta**:
> [[anthropic]] è un'azienda di AI safety fondata nel 2021 [[anthropic]]. Ha sviluppato [[constitutional-ai]] come metodo di allineamento basato su principi espliciti, alternativa a RLHF puro [[constitutional-ai]]. La loro posizione nel landscape è documentata in [[ai-safety-landscape-2025]] dove appaiono come uno dei tre principali lab focalizzati sulla sicurezza [[ai-safety-landscape-2025]].
>
> La wiki non documenta i budget destinati alla sicurezza né i nomi dei ricercatori principali del team safety.
>
> _(deduzione: dato che [[constitutional-ai]] è il loro metodo pubblico principale, è probabile che guidi anche i lavori interni non pubblicati — ma questo non è documentato nella wiki)_
>
> **Fonti consultate**:
> - `wiki/entities/anthropic.md`
> - `wiki/concepts/constitutional-ai.md`
> - `wiki/synthesis/ai-safety-landscape-2025.md`

## Note operative

- Se l'utente fa una domanda di follow-up nella stessa sessione, riusa il context già caricato invece di rieseguire QMD (a meno che la domanda richieda info diverse).
- Per domande aperte ("dimmi tutto su X"), fai 2-3 query QMD con angolature diverse e unisci i risultati deduplicando per path.
- Se trovi contraddizioni fra pagine, segnalalo all'utente e suggerisci `wiki-lint` per la review.
