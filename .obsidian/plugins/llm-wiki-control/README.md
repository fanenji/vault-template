# LLM Wiki Control

Pannello di controllo dentro Obsidian per le **Agent Skills** della llm-wiki.
Non reimplementa la logica delle skill: **pilota l'agente `pi` in headless**
(`pi -p --mode json --skill <path> "<prompt>"`) e mostra l'output in streaming.

Plugin **desktop-only** (usa `child_process` per lanciare `pi`).

## Cosa fa (v1 / MVP)

- Icona ribbon + comando "Apri pannello LLM Wiki" → pannello laterale (`ItemView`).
- Tab **Query**: domanda → `wiki-query`, streaming live, storico delle query con
  click → resume e Follow-up (continua la sessione via `--session <id>`).
- Tab **Ingest**: seleziona un file (o l'intera cartella `_inbox/clippings`) →
  `wiki-ingest`. Avviso costo token per batch > 5 file (regola di `CLAUDE.md`).
- Settings: percorso di `pi`, provider/model (dropdown da `pi --list-models`),
  cartella ingest, toggle "mostra thinking".

DeepResearch, Lint `--fix` e schedulazione sono predisposti ma fuori scope v1.

## Build

```bash
npm install
npm run build      # tsc -noEmit + esbuild → main.js
```

`main.js` è committato, quindi sul Mac basta abilitare il plugin (non serve build).

## Verifica runtime (sul Mac, dove `pi` è installato)

Il container di sviluppo non ha `pi` né Obsidian: questi step vanno eseguiti localmente.

1. **Schema eventi** — nella vault root:
   `pi -p --mode json "ciao"`
   Confronta i nomi-campo con `src/runner/events.ts`. Se differiscono, adatta
   `normalizeRawEvent` (cerca il commento `TODO confermare schema`).
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
