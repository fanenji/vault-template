# LLM Wiki Control

Pannello di controllo dentro Obsidian per le **Agent Skills** della llm-wiki.
Non reimplementa la logica delle skill: **pilota l'agente `pi` in headless**
(`pi -p --mode json --skill <path> "<prompt>"`) e mostra l'output in streaming.

Plugin **desktop-only** (usa `child_process` per lanciare `pi`).

## Cosa fa

- Icona ribbon + comando "Apri pannello LLM Wiki" → pannello laterale (`ItemView`).
- Tab **Query**: domanda → `wiki-query`, streaming live, storico delle query con
  click → resume e Follow-up (continua la sessione via `--session <id>`); bottone
  "Salva la risposta in wiki/queries/" attivo a ricerca completata (manda un
  follow-up di salvataggio sulla sessione attiva).
- Tab **DeepResearch**: argomento → `deep-research` (Tavily/DuckDuckGo), streaming
  con `[[wikilink]]` + cross-ref, storico, toggle **Auto-ingest** (Step 8).
- Tab **Ingest**: seleziona un file (o l'intera cartella `_inbox/clippings`) →
  `wiki-ingest`. Avviso costo token per batch > 5 file (regola di `AGENTS.md`).
- Tab **Lint**: esegue `wiki-lint` (audit) con checkbox `--fix`; report in
  `_notes/lint/lint-report.md`.
- Settings: percorso di `pi`, provider/model (dropdown da `pi --list-models`),
  cartella ingest, **Tavily API key** (→ `.llm-wiki/secrets.json`), toggle
  "mostra thinking" e "mostra i comandi eseguiti", **schedulazione lint**
  (lint automatico periodico: script deterministico senza LLM, con report e diff;
  il check semantico via pi parte solo se compaiono warning nuovi. Il run
  scaduto parte anche all'avvio di Obsidian).

## Build

```bash
npm install
npm run build      # tsc -noEmit + esbuild → main.js
```

`main.js` è committato, quindi sul Mac basta abilitare il plugin (non serve build).

## Installare/aggiornare su altre vault

Le vault **nuove** nascono da vault-template (copia/clone): già complete.

Per le vault **esistenti** (che hanno già llm-wiki in versione pre-plugin) usa lo
script idempotente, lanciato **da vault-template**:

```bash
bash _system/scripts/install-into-vault.sh /path/to/vault [--dry-run]
```

Aggiorna la machinery (skill, script, plugin) + migra l'indice a qmd 2.5.2
(`.qmd/`), **preservando** i contenuti per-vault (`purpose.md`, `schema.md`, note,
`wiki/`). `CLAUDE.md`/`AGENTS.md` vengono aggiornati con backup `.bak`. La
machinery sostituita è salvata in `.llm-wiki/backups/<timestamp>/` se la vault
non è un repo git. È idempotente: rilanciabile come updater. Usa `--dry-run` per
vedere prima cosa cambierebbe. Dopo: ricarica Obsidian e abilita il plugin
("Fidati dell'autore" alla prima installazione).

## Verifica runtime (sul Mac, dove `pi` è installato)

1. **Schema eventi** — ✅ confermato su `pi v0.78`. Lo stream live usa delta
   incrementali (`message_update.assistantMessageEvent.text_delta`), il reasoning
   arriva su `thinking_end`, i tool su `tool_execution_start`; lo storico dai file
   di sessione usa righe `type:"message"` con `content[]`. Tutto gestito da
   `normalizeRawEvent` in `src/runner/events.ts` (vedi commento iniziale del file).
2. **Runner isolato**:
   `pi -p --mode json --skill .claude/skills/wiki-query "Cosa sappiamo su X?"`
   → conferma lo streaming e la creazione di un `.jsonl` in
   `~/.pi/agent/sessions/<cartella-della-vault>/`.
3. **UI** — abilita il plugin (o ricarica con la skill `obsidian-cli`), clicca
   l'icona ribbon: si apre il pannello con i tab Query e Ingest.
4. **Query** — fai una domanda, "Cerca": output live con `[[wikilink]]`; la
   sessione compare nello storico. Click → resume; "Follow-up" continua la stessa
   sessione.
5. **Ingest** — seleziona un file in `_inbox/clippings`, "Ingerisci": le pagine
   vengono create in `wiki/` (la skill chiude con `qmd embed --update`).
6. **Settings** — "Ricarica modelli" popola il dropdown da `pi --list-models`.

## Note

- Lo storico si legge **direttamente** dai file `.jsonl` di `pi`
  (`~/.pi/agent/sessions/`): `sessionStore` filtra per `cwd === vault root`
  leggendo la prima riga di ogni file, senza dipendere dalla regola di
  sanitizzazione del path usata da `pi`.
- I prompt lanciati dal plugin sono marcati con `[llm-wiki:<skill>]` per
  distinguere le sessioni nello storico per tab.
- PATH: su macOS Obsidian eredita un PATH ridotto; il runner aggiunge
  `/opt/homebrew/bin` e `/usr/local/bin`. In alternativa, imposta il percorso
  assoluto di `pi` nei settings.
