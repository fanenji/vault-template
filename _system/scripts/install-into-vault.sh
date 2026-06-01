#!/usr/bin/env bash
# install-into-vault.sh — installa/aggiorna il sistema llm-wiki (skill, script,
# struttura, indice QMD) + il plugin Obsidian in una vault target.
#
# Idempotente: rilanciabile come updater. Va lanciato DALLA vault-template
# (source-of-truth), passando il path della vault da aggiornare:
#
#   bash _system/scripts/install-into-vault.sh /path/to/vault [--dry-run]
#
# Policy (vedi README):
#   - Machinery (.claude/skills, .claude/commands, _system/scripts, file del
#     plugin) → SEMPRE sincronizzata/sovrascritta.
#   - Istruzioni (CLAUDE.md, AGENTS.md) → aggiornate, ma con backup .bak se
#     differiscono dalla source.
#   - Contenuti per-vault (purpose.md, schema.md, wiki/, raw/, _inbox/, _notes/,
#     _system/canvas, _system/templates, le tue note) → MAI toccati.
#   - Backup della machinery sovrascritta: solo se la vault target NON è un repo
#     git (in .llm-wiki/backups/<timestamp>/). Su repo git si usa il diff git.

set -euo pipefail

# ── Source root (vault-template, da cui parte lo script) ──────────────────────
SOURCE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# ── Parse argomenti ───────────────────────────────────────────────────────────
DRY=0
TARGET=""
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY=1 ;;
    -h|--help)
      sed -n '2,25p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    -*) echo "✗ Opzione sconosciuta: $arg" >&2; exit 2 ;;
    *) TARGET="$arg" ;;
  esac
done

if [ -z "$TARGET" ]; then
  echo "✗ Uso: bash install-into-vault.sh <vault-target> [--dry-run]" >&2
  exit 2
fi
if [ ! -d "$TARGET" ]; then
  echo "✗ Vault target non esiste o non è una cartella: $TARGET" >&2
  exit 2
fi
TARGET="$(cd "$TARGET" && pwd)"   # path assoluto
if [ "$TARGET" = "$SOURCE_ROOT" ]; then
  echo "✗ La vault target coincide con vault-template (source). Niente da fare." >&2
  exit 2
fi

# ── Setup ─────────────────────────────────────────────────────────────────────
TS="$(date +%Y%m%d-%H%M%S)"
BACKUP_ROOT="$TARGET/.llm-wiki/backups/$TS"
IS_GIT=0
if git -C "$TARGET" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  IS_GIT=1
fi
DO_BACKUP=1
[ "$IS_GIT" -eq 1 ] && DO_BACKUP=0   # repo git → niente backup (usa git diff)

PREFIX=""
[ "$DRY" -eq 1 ] && PREFIX="[dry-run] "

echo "→ ${PREFIX}Source : $SOURCE_ROOT"
echo "→ ${PREFIX}Target : $TARGET"
echo "→ ${PREFIX}Git    : $([ "$IS_GIT" -eq 1 ] && echo "sì (backup machinery: no)" || echo "no (backup machinery: sì → .llm-wiki/backups/$TS)")"
echo ""

# ── Helper ────────────────────────────────────────────────────────────────────
# sync_dir <rel-path>  — rsync di una dir machinery da source a target.
sync_dir() {
  local rel="$1"
  local src="$SOURCE_ROOT/$rel/" dst="$TARGET/$rel/"
  [ -d "$SOURCE_ROOT/$rel" ] || return 0
  # NB: niente --delete: aggiorniamo/aggiungiamo la machinery ma NON rimuoviamo
  # eventuali skill/script custom aggiunti dall'utente nel target (più sicuro).
  local args=(-a --exclude='__pycache__/' --exclude='*.pyc' --exclude='.DS_Store' --itemize-changes)
  [ "$DRY" -eq 1 ] && args+=(-n)
  if [ "$DO_BACKUP" -eq 1 ] && [ -d "$TARGET/$rel" ]; then
    args+=(-b --backup-dir="$BACKUP_ROOT/$rel")
  fi
  echo "→ ${PREFIX}sync machinery: $rel"
  mkdir -p "$dst" 2>/dev/null || true
  rsync "${args[@]}" "$src" "$dst" | sed 's/^/    /' || true
}

# copy_file <rel-path>  — copia un singolo file machinery (con backup).
copy_file() {
  local rel="$1"
  local src="$SOURCE_ROOT/$rel" dst="$TARGET/$rel"
  [ -f "$src" ] || return 0
  if cmp -s "$src" "$dst" 2>/dev/null; then return 0; fi   # identico → skip
  echo "→ ${PREFIX}file: $rel"
  if [ "$DRY" -eq 1 ]; then return 0; fi
  mkdir -p "$(dirname "$dst")"
  if [ "$DO_BACKUP" -eq 1 ] && [ -f "$dst" ]; then
    mkdir -p "$(dirname "$BACKUP_ROOT/$rel")"
    cp -p "$dst" "$BACKUP_ROOT/$rel"
  fi
  cp -p "$src" "$dst"
}

# update_instruction <rel-path>  — CLAUDE.md/AGENTS.md: aggiorna con .bak se differisce.
update_instruction() {
  local rel="$1"
  local src="$SOURCE_ROOT/$rel" dst="$TARGET/$rel"
  [ -f "$src" ] || return 0
  if cmp -s "$src" "$dst" 2>/dev/null; then return 0; fi
  if [ ! -f "$dst" ]; then
    echo "→ ${PREFIX}istruzioni (nuovo): $rel"
    [ "$DRY" -eq 0 ] && cp -p "$src" "$dst"
    return 0
  fi
  echo "→ ${PREFIX}istruzioni (aggiorno, backup $rel.bak-$TS): $rel"
  if [ "$DRY" -eq 0 ]; then
    cp -p "$dst" "$dst.bak-$TS"
    cp -p "$src" "$dst"
  fi
}

# ensure_dir <rel-path>  — crea cartella + .gitkeep se manca (mai sovrascrive).
ensure_dir() {
  local rel="$1"
  if [ -d "$TARGET/$rel" ]; then return 0; fi
  echo "→ ${PREFIX}crea struttura: $rel"
  if [ "$DRY" -eq 0 ]; then
    mkdir -p "$TARGET/$rel"
    touch "$TARGET/$rel/.gitkeep"
  fi
}

# ── 1. Machinery: skill, commands, scripts ────────────────────────────────────
sync_dir ".claude/skills"
sync_dir ".claude/commands"
sync_dir "_system/scripts"

# ── 2. Plugin Obsidian ────────────────────────────────────────────────────────
PLUGIN_REL=".obsidian/plugins/llm-wiki-control"
echo "→ ${PREFIX}plugin: $PLUGIN_REL"
[ "$DRY" -eq 0 ] && mkdir -p "$TARGET/$PLUGIN_REL"
for f in manifest.json main.js styles.css; do
  copy_file "$PLUGIN_REL/$f"
done

# Merge dell'id nel community-plugins.json (preserva i plugin esistenti).
CP="$TARGET/.obsidian/community-plugins.json"
echo "→ ${PREFIX}abilita plugin in community-plugins.json"
if [ "$DRY" -eq 0 ]; then
  python3 - "$CP" <<'PY'
import json, sys, os
path = sys.argv[1]
pid = "llm-wiki-control"
try:
    with open(path) as f:
        data = json.load(f)
    if not isinstance(data, list):
        data = []
except (FileNotFoundError, json.JSONDecodeError):
    data = []
if pid not in data:
    data.append(pid)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print("    aggiunto", pid)
else:
    print("    già presente")
PY
fi

# ── 3. Istruzioni (CLAUDE.md / AGENTS.md) con backup .bak ─────────────────────
update_instruction "CLAUDE.md"
update_instruction "AGENTS.md"

# ── 4. Struttura cartelle (mai sovrascrive contenuti) ─────────────────────────
for d in wiki/entities wiki/concepts wiki/sources wiki/queries wiki/synthesis \
         raw/sources _inbox/clippings; do
  ensure_dir "$d"
done

# ── 5. QMD + secrets via init-vault.sh (ora aggiornato a qmd 2.5.2) ───────────
# init-vault.sh è idempotente: crea .qmd/ (qmd init), aggiunge la collection
# wiki, fa qmd update && qmd embed, e crea secrets.json se manca.
if [ "$DRY" -eq 1 ]; then
  echo "→ ${PREFIX}eseguirei: (cd target && bash _system/scripts/init-vault.sh)"
  if [ -f "$TARGET/.llm-wiki/qmd-index.sqlite" ]; then
    echo "    nota: trovato vecchio .llm-wiki/qmd-index.sqlite (obsoleto in qmd 2.5.2, verrà ignorato)"
  fi
else
  echo "→ Inizializzazione QMD/secrets (init-vault.sh nel target)..."
  ( cd "$TARGET" && bash _system/scripts/init-vault.sh ) | sed 's/^/    /' || \
    echo "    ⚠ init-vault.sh ha riportato errori — controlla qmd/connessione"
fi

# ── Report finale ─────────────────────────────────────────────────────────────
echo ""
if [ "$DRY" -eq 1 ]; then
  echo "✓ Dry-run completato (nessuna modifica applicata)."
else
  echo "✓ Installazione/aggiornamento completato in: $TARGET"
  [ "$DO_BACKUP" -eq 1 ] && [ -d "$BACKUP_ROOT" ] && echo "  Backup machinery sostituita: .llm-wiki/backups/$TS/"
fi
echo ""
echo "Prossimi passi in Obsidian (vault target):"
echo "  1. Ricarica la vault (o riavvia Obsidian)."
echo "  2. Se è la prima installazione: Impostazioni → Plugin della community →"
echo "     abilita 'LLM Wiki Control' (e 'Fidati dell'autore' se richiesto)."
echo "  3. L'icona ribbon 'Apri pannello LLM Wiki' apre il pannello."
