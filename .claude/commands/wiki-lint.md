---
description: Audit the wiki for broken links, orphans, frontmatter issues, and semantic problems
---

Invoca la skill `wiki-lint` per fare un audit di salute della wiki.

Opzioni passate dall'utente: $ARGUMENTS

Flag riconosciuti:
- `--fix` → applica fix automatici dove sicuro (stub pages, frontmatter, `lint_ignore` per issue intenzionali confermate)
- `--report-only` → stampa il report ma non scrive `_notes/lint/lint-report.md`
- `--no-semantic` → salta il check semantico LLM (solo deterministici)
- `--no-qmd` → salta i check via QMD (missing-page, similar-pairs)

Segui la procedura completa di `.claude/skills/wiki-lint/SKILL.md`: Step 1 deterministici via `lint.py` (con diff vs run precedente), Step 2 semantico via LLM (coppie simili QMD + campione a rotazione), Step 3 report unificato in `_notes/lint/lint-report.md`. Aggiorna `wiki/log.md` al termine. Nel riassunto dai priorità alle issue `new` e ai `pending` vecchi.
