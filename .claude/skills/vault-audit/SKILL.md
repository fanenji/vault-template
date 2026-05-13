---
name: vault-audit
description: Run a full health audit on the Obsidian vault. Checks frontmatter completeness (title, created, tags, type), broken [[wikilinks]], and orphan notes. Generates a markdown report and CSV, then auto-fixes missing frontmatter fields. Trigger when the user asks to audit the vault, check note health, find broken links, find orphan notes, or fix missing frontmatter.
---

# Vault Audit

Run a full health audit on the Obsidian vault at:
`/Users/S.Parodi/Library/Mobile Documents/com~apple~CloudDocs/Obsidian/Vault`

## Scripts

All scripts live in `99 System/scripts/`:

| Script | Purpose |
|--------|---------|
| `audit_frontmatter.py` | Finds files missing required fields: `title`, `created`, `tags`, `type` |
| `audit_wikilinks.py` | Finds broken `[[wikilinks]]` (note links and image refs) |
| `audit_orphans.py` | Finds notes with zero inbound links |
| `fix_frontmatter.py` | Adds missing fields without touching existing values |
| `vault-audit.sh` | Wrapper: runs all checks in parallel, generates report + CSV, runs fix |

## Running the audit

### Full audit (recommended)

```bash
VAULT_SCRIPTS="/Users/S.Parodi/Library/Mobile Documents/com~apple~CloudDocs/Obsidian/Vault/99 System/scripts"
bash "$VAULT_SCRIPTS/vault-audit.sh"
```

### Audit only, no fix

```bash
bash "$VAULT_SCRIPTS/vault-audit.sh" --no-fix
```

### Custom date for output files

```bash
bash "$VAULT_SCRIPTS/vault-audit.sh" --date 2026-04-01
```

### Individual checks (parallel)

```bash
python3 "$VAULT_SCRIPTS/audit_frontmatter.py" > /tmp/fm.json &
python3 "$VAULT_SCRIPTS/audit_wikilinks.py"   > /tmp/wl.json &
python3 "$VAULT_SCRIPTS/audit_orphans.py"     > /tmp/or.json &
wait
```

### Fix frontmatter only

```bash
python3 "$VAULT_SCRIPTS/fix_frontmatter.py"
# or from a pre-existing results file:
python3 "$VAULT_SCRIPTS/fix_frontmatter.py" /tmp/fm.json
```

## Output

- `99 System/vault-audit-YYYY-MM-DD.md` — markdown report (opened in Obsidian)
- `99 System/vault-audit-YYYY-MM-DD.csv` — all issues with columns: `check`, `file`, `detail`

## Frontmatter fix defaults

| Field | Default value |
|-------|--------------|
| `title` | Filename stem (as-is) |
| `type` | `note` |
| `created` | File birth date (`st_birthtime`) |
| `tags` | `[]` |

Skipped files: `CLAUDE.md`, `Templates/*` (not vault notes).

## Interpreting results

- **Broken wikilinks**: many are image refs (`[[image.png]]`) pointing to missing attachments — harmless. Focus on broken note links.
- **Orphans in 90 ARCHIVE**: expected — archived work notes often have no inbound links.
- **`90 ARCHIVE/90 ARCHIVE.md`**: index file with many links to deleted/renamed notes — review manually.
