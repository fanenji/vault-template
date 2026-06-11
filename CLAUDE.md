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

- **Test obbligatori** dopo ogni modifica agli script: le suite sono in `.claude/skills/wiki-ingest/tests/` e `.claude/skills/wiki-lint/tests/` (`python3 -m unittest discover` dalla cartella tests). Sono unittest stdlib: non introdurre dipendenze.
- **Script self-contained**: gli script delle skill usano solo stdlib, trovano la vault con `find_vault_root()` (risale cercando `wiki/` + `.llm-wiki/`), leggono `.llm-wiki/config.json` best-effort con default nei flag CLI. Mantieni questo pattern.
- **Verifica E2E in vault temporanea** (`mktemp -d` con `wiki/` + `.llm-wiki/`): mai sporcare la `wiki/` del template con dati di prova.
- **Sincronizza la documentazione**: se cambi il comportamento di una skill, aggiorna il suo SKILL.md; se cambi lo stato in `.llm-wiki/`, aggiorna `.llm-wiki/README.md` e `.gitignore`; se aggiungi file machinery, verifica che `install-into-vault.sh` li copra (è l'updater delle vault target — testalo con `--dry-run` su un target finto).
- **Plugin**: gli installer copiano solo `manifest.json`, `main.js`, `styles.css`. Dopo modifiche a `src/`, ricompila (o allinea `main.js` in modo equivalente), altrimenti i target non ricevono la modifica.
- **Prompt delle skill** (`prompts/*.md`): il parser dei FILE block è strict — se tocchi il formato di output richiesto, aggiorna parser e test insieme.

### Convenzioni di commit

- Messaggi convenzionali (`feat(scope):`, `fix(scope):`) con corpo che spiega il perché.
- Non committare lo stato UI di Obsidian (`workspace.json`, `data.json` di plugin terzi): viene raccolto dai commit di vault backup.
- Commit e push solo su richiesta dell'utente.
