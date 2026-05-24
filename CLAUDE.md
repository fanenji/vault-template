# CLAUDE.md

Istruzioni per agenti (Claude Code, OpenCode, Pi, …) che operano su questa vault.

## Cos'è questa vault

Una **knowledge base LLM-driven** organizzata come llm-wiki. Documenti grezzi vivono in `raw/sources/` (immutabili); le pagine wiki generate dall'LLM vivono in `wiki/` (modificabili). `purpose.md` e `schema.md` definiscono scope e regole strutturali — leggili prima di qualsiasi operazione non banale.

## Skill disponibili

Le funzionalità principali sono esposte come **Agent Skills** in `.claude/skills/`. Carica la skill rilevante prima di operare:

| Skill | Quando usarla |
|---|---|
| `wiki-query` | L'utente chiede informazioni che richiedono ricerca nella wiki |
| `wiki-lint` | Audit di salute della wiki (broken link, orfani, contraddizioni) |
| `wiki-ingest` | Nuovi documenti da processare in `raw/sources/` o specificati dall'utente |
| `deep-research` | Ricerca esterna (web) su un argomento, da integrare nella wiki |

Ogni skill ha un proprio `SKILL.md` con il contratto operativo.

## Convenzioni rapide

- **Wikilink**: usa sempre `[[nome-pagina]]` per cross-reference. Case-insensitive.
- **Frontmatter**: ogni pagina wiki ha YAML frontmatter con almeno `type`, `title`, `created`.
- **Tipi pagina**: `entity`, `concept`, `source`, `query`, `synthesis` (vedi `schema.md`).
- **Cartella raw/**: immutabile. Mai modificare contenuto, solo aggiungere.
- **Cartella wiki/**: modificabile dagli agenti. `index.md`, `log.md`, `overview.md` sono auto-gestiti.
- **Lingua**: l'output rispetta la lingua del contenuto di input (auto-detect).

## Stato interno

`.llm-wiki/` contiene queue di ingest, cache SHA256, indice QMD. **Non modificare a mano** salvo per debug. Le skill aggiornano lo stato in modo idempotente.

## `_system/`

Cartella per configurazione Obsidian e script di sistema:
- `_system/canvas/` — file `.canvas` (whiteboards visivi), popolati manualmente dall'utente
- `_system/templates/` — template di note Obsidian, popolati manualmente
- `_system/scripts/init-vault.sh` — script di inizializzazione (markitdown + qmd + DDG + indice QMD)

Il pattern segue le convenzioni di Obsidian: `_system/` raggruppa tutto ciò che non è contenuto della knowledge base (è "macchina", non "conoscenza").

## Retrieval

La ricerca nella wiki (lessicale + semantica + reranking) usa [QMD](https://github.com/tobi/qmd). Comandi shell utili:

```bash
qmd query "domanda" --json -n 10    # hybrid search con reranking
qmd vsearch "concetto" -n 5         # vector-only
qmd search "termine esatto"         # BM25-only
qmd get "wiki/entities/foo.md"      # recupera un file
qmd multi-get "wiki/concepts/*.md"  # batch
qmd embed --update                  # rinfresca l'indice dopo modifiche
```

L'indice è in `.llm-wiki/qmd-index.sqlite`. Dopo ogni ingest, le skill chiamano `qmd embed --update` per mantenerlo coerente.

**QMD — primo avvio**: al primo `qmd embed` e al primo `qmd query`, QMD scarica due modelli GGUF (~400 MB totali). Richiede connessione. Se il comando va in timeout:
1. Rilancia `qmd embed --db .llm-wiki/qmd-index.sqlite` su una rete stabile.
2. Per le query, usa `--no-rerank` per saltare il secondo modello: `qmd query "..." --no-rerank`.

## Configurazione Tavily (deep-research)

La skill `deep-research` usa Tavily di default e DuckDuckGo come fallback automatico. Per usare Tavily:

1. Apri `.llm-wiki/secrets.json` (già creato da `init-vault.sh`, non committato):
   ```json
   { "TAVILY_API_KEY": "tvly-xxxxxxxxxxxxxxxx" }
   ```
2. Oppure: `export TAVILY_API_KEY="tvly-..."` nel tuo `.zshrc` / `.bashrc`.

Senza Tavily il fallback DuckDuckGo è attivo automaticamente — non serve configurazione.

## Regole generali

- Non cancellare file senza conferma esplicita dell'utente.
- Conferma sempre prima di operazioni distruttive sulla wiki (rinomine massive, merge pagine).
- Per ingest di batch (>5 file), avvisa l'utente del costo stimato in token prima di procedere.
- Se una skill fallisce a metà, lo stato in `.llm-wiki/` è coerente: puoi sempre rilanciare la skill (idempotente).
