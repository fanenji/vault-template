# CLAUDE.md

Istruzioni per Claude Code su questa vault. Gli altri agenti (Pi, OpenCode, …) sono **operatori della KB** e leggono solo `AGENTS.md`; se sei l'operatore della KB e non Claude Code, il tuo documento è quello.

## Ripartizione dei ruoli

In questa vault Claude Code è lo **sviluppatore del sistema llm-wiki** (skill, script, plugin, installer) e, all'occorrenza, anche operatore della KB. Pi (DeepSeek) gestisce la knowledge base e opera solo tramite le skill.

Il contesto operativo (struttura della vault, skill, convenzioni, QMD, regole) è in AGENTS.md, importato qui sotto. **Nota**: la sezione "Il tuo ruolo: operatore" di AGENTS.md vale per gli altri agenti — tu puoi modificare la machinery, ma quando operi sulla KB rispetta le stesse regole operative (skill, convenzioni, conferme prima di azioni distruttive).

@AGENTS.md

## Ruolo: sviluppo del sistema

### Cosa è "machinery"

- `.claude/skills/*/` — SKILL.md (contratti), `scripts/` (Python), `prompts/`, `tests/`
- `.claude/commands/` — slash command (symlinkati in `.opencode/`)
- `_system/scripts/` — `init-vault.sh` (setup), `install-into-vault.sh` (updater per vault target)
- `.obsidian/plugins/llm-wiki-control/` — plugin Obsidian (sorgenti in `src/`, compilato in `main.js`)

### Regole di sviluppo

- **Test obbligatori** dopo ogni modifica agli script: le suite sono in `.claude/skills/wiki-ingest/tests/`, `.claude/skills/wiki-lint/tests/` e `.claude/skills/graph-analyze/tests/` (`python3 -m unittest discover` dalla cartella tests). Sono unittest stdlib: non introdurre dipendenze.
- **Script self-contained**: gli script delle skill usano solo stdlib, trovano la vault con `find_vault_root()` (risale cercando `wiki/` + `.llm-wiki/`), leggono `.llm-wiki/config.json` best-effort con default nei flag CLI. Mantieni questo pattern.
- **Verifica E2E in vault temporanea** (`mktemp -d` con `wiki/` + `.llm-wiki/`): mai sporcare la `wiki/` del template con dati di prova.
- **Sincronizza la documentazione**: se cambi il comportamento di una skill, aggiorna il suo SKILL.md; se cambi lo stato in `.llm-wiki/`, aggiorna `.llm-wiki/README.md` e `.gitignore`; se aggiungi file machinery, verifica che `install-into-vault.sh` li copra (è l'updater delle vault target — testalo con `--dry-run` su un target finto).
- **Plugin**: gli installer copiano solo `manifest.json`, `main.js`, `styles.css`. Dopo modifiche a `src/`, ricompila (o allinea `main.js` in modo equivalente), altrimenti i target non ricevono la modifica.
- **Prompt delle skill** (`prompts/*.md`): il parser dei FILE block è strict — se tocchi il formato di output richiesto, aggiorna parser e test insieme.

### Vault di test: `../vault-test`

Esiste una vault gemella in `/Users/S.Parodi/Vaults/vault-test` che **eredita live la machinery** da questo template via symlink assoluti:

- `.claude/skills` → `vault-template/.claude/skills` (e `.opencode/skills|commands` a cascata, via symlink relativi)
- `.claude/commands` → `vault-template/.claude/commands`
- `_system/scripts` → `vault-template/_system/scripts`
- `.obsidian/plugins/llm-wiki-control/main.js` → `vault-template/.../main.js` (per vedere le modifiche al plugin serve ricaricare Obsidian nella vault-test)

Tutto il resto è **proprio di vault-test** e indipendente: `wiki/`, `raw/`, `_inbox/`, `.llm-wiki/` (stato), `.qmd/` (indice), `CLAUDE.md`/`AGENTS.md`, config Obsidian. Gli esperimenti lì non sporcano mai il template.

Come usarla durante lo sviluppo:

- **Ogni modifica a script/skill/comandi nel template è immediatamente attiva in vault-test** — niente install, niente sync. Per provarla: `cd /Users/S.Parodi/Vaults/vault-test` ed esegui da lì (gli script risolvono la vault dal cwd via `find_vault_root`).
- Usala per i **test manuali/E2E con contenuto reale persistente** (ingest di documenti veri, query, lint su una wiki popolata). Per i test automatici e usa-e-getta resta la regola della vault temporanea `mktemp`.
- **Non lanciare `install-into-vault.sh` su vault-test**: l'installer copierebbe file reali sopra/attraverso i symlink. Vault-test non ne ha bisogno per definizione.
- Se aggiungi una **nuova categoria di machinery** (una nuova top-level dir condivisa), crea il symlink corrispondente anche in vault-test, e verifica lo stato dei link con `ls -la` (è già successo che `commands` fosse una copia stale invece di un symlink).

- Messaggi convenzionali (`feat(scope):`, `fix(scope):`) con corpo che spiega il perché.
- Non committare lo stato UI di Obsidian (`workspace.json`, `data.json` di plugin terzi): viene raccolto dai commit di vault backup.
- Commit e push solo su richiesta dell'utente.
