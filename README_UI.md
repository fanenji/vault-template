# LLM Wiki — Interfaccia (plugin Obsidian) & deploy

Riepilogo dell'interfaccia utente del sistema **llm-wiki**: il plugin Obsidian
`llm-wiki-control` e lo script di installazione/aggiornamento
`install-into-vault.sh`.

---

## 1. Cos'è

Il plugin porta dentro Obsidian le **Agent Skills** della vault (`wiki-query`,
`wiki-ingest`, e in roadmap `deep-research`/`wiki-lint`). Non reimplementa la
logica delle skill: **pilota l'agente `pi` in modalità headless**
(`pi -p --mode json --skill <path> "<prompt>"`) e mostra l'output in streaming.

Conseguenze architetturali:

- È un **runner di agente**: usare il plugin equivale a lanciare le skill con un
  agente (Claude Code / pi / OpenCode) dalla vault root. Le skill restano quindi
  pienamente utilizzabili anche **senza** plugin.
- È **desktop-only** (usa `child_process` per lanciare `pi`); non funziona su
  Obsidian mobile.
- Lo **storico** non richiede un DB custom: si legge direttamente dai file di
  sessione di `pi` (`~/.pi/agent/sessions/<cwd>/*.jsonl`), filtrati per la vault
  corrente e marcati dal plugin con `[llm-wiki:<skill>]`.

---

## 2. Funzionalità implementate

### Pannello & navigazione
- **Icona ribbon** "Apri pannello LLM Wiki" + comando
  `llm-wiki-control:open-llm-wiki-panel`.
- **Pannello laterale** agganciabile (`ItemView`), con tab **Query** e **Ingest**.

### Tab Query
- Casella domanda → esegue `wiki-query`.
- **Streaming live** della risposta (token-by-token) con citazioni `[[wikilink]]`.
- **Storico query**: lista delle sessioni precedenti (lette dai file di `pi`);
  click su una riga = **resume**; pulsante **Follow-up** per continuare la stessa
  conversazione (`pi --session <id>`); **Nuova** per ripartire.
- **Checkbox "Salva la risposta in wiki/queries/"** (default off): se attiva,
  istruisce la skill a salvare la risposta come pagina e a reindicizzare QMD.

### Tab DeepResearch
- Casella argomento → esegue `deep-research` (ricerca web multi-query con Tavily,
  fallback automatico a DuckDuckGo).
- **Streaming live** della sintesi con citazioni `[[wikilink]]` + cross-reference
  alle pagine wiki esistenti; salva una pagina in `wiki/queries/research-…md`.
- **Storico ricerche** con resume/Follow-up (come Query).
- **Toggle "Auto-ingest"** (default off): se attivo, scompone la pagina di
  ricerca in pagine entity/concept collegate (Step 8 della skill).

### Tab Ingest
- Selettore **file singolo** o **intera cartella** (default `_inbox/clippings`,
  configurabile).
- Esegue `wiki-ingest` con **streaming live**.
- **Avviso costo token** per batch > 5 file (regola di `CLAUDE.md`).
- A fine ingest riuscito il **sorgente viene archiviato** automaticamente in
  `raw/sources/` (vedi §3).

### Streaming / log
- Parser eventi allineato allo schema reale di `pi --mode json` (v0.78):
  `message_update.assistantMessageEvent.text_delta` per il testo,
  `thinking_end` per il reasoning, `tool_execution_start` per i tool.
- **Toggle "Mostra i comandi eseguiti"** (default **off**): nasconde le righe dei
  tool (`bash`, `read`, …) per un log pulito; attivabile dai settings.
- Pulsante **Stop** per interrompere l'esecuzione (abort del processo `pi`).

### Impostazioni
- `Percorso di pi` (comando o path assoluto).
- `Provider` / `Model` (dropdown popolato da `pi --list-models`).
- `Cartella ingest predefinita`.
- `Mostra il thinking` (default off).
- `Mostra i comandi eseguiti` (default off).
- Predisposti (iterazione 2, non attivi): schedulazione `wiki-lint`.

### Roadmap (predisposto, non ancora implementato)
- Tab **Lint** con checkbox `--fix` (skill `wiki-lint`).
- **Schedulazione** automatica del lint.

---

## 3. Comportamenti lato backend (skill/script)

Modifiche al sistema llm-wiki collegate all'interfaccia:

- **QMD 2.5.2**: l'indice è **project-local** in `.qmd/` (discovery dal cwd) +
  collection nominate. Il vecchio flag `--db .llm-wiki/qmd-index.sqlite` non
  esiste più ed è ignorato. Comandi: `qmd query "…"` (dalla vault root),
  refresh = `qmd update && qmd embed`. `init-vault.sh` crea l'indice con
  `qmd init` + `qmd collection add ./wiki`.
- **Archiviazione sorgente**: `finalize.py`, su ingest pienamente riuscito,
  sposta l'originale da `_inbox/` a `raw/sources/` (`raw/` = source of truth
  immutabile). Idempotente; disattivabile con `--no-archive`.

Requisiti runtime: `pi`, `qmd` 2.5.2, `markitdown`, `duckduckgo-search`
(installati da `init-vault.sh`), e l'indice `.qmd/` inizializzato.

---

## 4. `install-into-vault.sh` — installer/updater idempotente

Script per **installare o aggiornare** il sistema llm-wiki + il plugin in una
vault. Pensato per le **vault esistenti** (che hanno già llm-wiki in versione
pre-plugin); le **vault nuove** nascono invece da `vault-template` (copia/clone)
e sono già complete.

### Uso

Lanciarlo **da `vault-template`** (la source-of-truth), passando la vault target:

```bash
bash _system/scripts/install-into-vault.sh /path/to/vault            # applica
bash _system/scripts/install-into-vault.sh /path/to/vault --dry-run  # anteprima
```

### Cosa fa

| Componente | Azione |
|---|---|
| `.claude/skills/`, `.claude/commands/`, `_system/scripts/` | **Machinery**: sincronizzata (aggiorna/aggiunge). Niente `--delete`: le tue skill/script custom non vengono rimossi. Esclude `__pycache__`, `*.pyc`, `.DS_Store`. |
| Plugin (`manifest.json`, `main.js`, `styles.css`) | Copiati in `.obsidian/plugins/llm-wiki-control/`; l'id è aggiunto a `community-plugins.json` (merge, preserva gli altri plugin). |
| Indice QMD | Migrazione a 2.5.2 delegata a `init-vault.sh` (idempotente): `.qmd/` + collection `wiki` + `qmd update && qmd embed` + `secrets.json`. Il vecchio `.llm-wiki/qmd-index.sqlite` viene ignorato. |
| Struttura | Crea le cartelle mancanti (`wiki/*`, `raw/sources`, `_inbox/clippings`) con `.gitkeep`; non sovrascrive contenuti. |

### Cosa **preserva** (mai toccato)

- `purpose.md`, `schema.md` (scope e regole specifiche della wiki).
- `wiki/`, `raw/`, `_inbox/`, `_notes/`, le tue note, `_system/canvas`,
  `_system/templates`.

### Istruzioni (`CLAUDE.md`, `AGENTS.md`)

Aggiornate alla versione del template, ma con **backup** `<file>.bak-<timestamp>`
se differiscono (così le tue eventuali personalizzazioni restano recuperabili).

### Backup della machinery sostituita

- Vault target **non** git → backup in `.llm-wiki/backups/<timestamp>/`.
- Vault target **git** → nessun backup (usi `git diff`/revert).

### Proprietà

- **Idempotente**: rilanciabile come updater; un secondo run senza cambiamenti è
  un no-op.
- **`--dry-run`**: mostra cosa cambierebbe senza applicare nulla.

### Dopo l'installazione (in Obsidian)

1. Ricarica la vault (o riavvia Obsidian).
2. Prima installazione: Impostazioni → Plugin della community → abilita
   **LLM Wiki Control** (e "Fidati dell'autore" se richiesto).
3. L'icona ribbon **"Apri pannello LLM Wiki"** apre il pannello.

> **Nota — perdita storico**: lo storico è per-vault (sessioni `pi` legate al
> path della vault). Installando in una vault diversa si parte da storico vuoto:
> è atteso, non c'è nulla da migrare.

---

## 5. Workflow di sviluppo del plugin

```bash
cd .obsidian/plugins/llm-wiki-control
npm install
npm run build      # tsc -noEmit + esbuild → main.js (committato)
```

Per iterare su una vault di test (`vault-test`) i cui `main.js`,
`.claude/skills` e `_system/scripts` sono **symlink** a `vault-template`:

```bash
# dopo un build in vault-template:
obsidian vault="vault-test" plugin:reload id=llm-wiki-control
```

I symlink propagano automaticamente le modifiche; basta ricaricare il plugin.

---

## 6. Limiti noti

- **Desktop-only** (Node `child_process`); no mobile.
- Schema eventi verificato su **pi v0.78**: se `pi` cambia il formato di
  `--mode json`, adeguare `src/runner/events.ts`.
- Lo `stdin` del processo `pi` viene chiuso subito dopo lo spawn
  (`child.stdin.end()`): necessario sotto Electron, altrimenti `pi` resta in
  attesa di EOF e non produce output.
