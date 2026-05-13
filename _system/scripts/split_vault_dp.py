#!/usr/bin/env python3
"""split_vault_dp.py — Estrae il contenuto data-platform in un nuovo vault Obsidian.

Azioni:
  1. Copia cartelle/file dp nel nuovo vault (struttura invariata)
  2. Copia gli attachment referenziati dai file dp
  3. Copia la config .obsidian nel nuovo vault
  4. Aggiorna i MOC nel vault originale (rimuove wikilink a file dp)

Imposta DRY_RUN = False per eseguire davvero.
"""

import re
import shutil
from pathlib import Path

# ── Configurazione ─────────────────────────────────────────────────────────────

VAULT_SRC = Path("/Users/S.Parodi/Library/Mobile Documents/com~apple~CloudDocs/Obsidian/Vault")
VAULT_DST = Path("/Users/S.Parodi/Library/Mobile Documents/com~apple~CloudDocs/Obsidian/DataPlatform")

DRY_RUN = False  # ← cambia a False per eseguire

# ── File/cartelle da copiare nel nuovo vault ───────────────────────────────────

# Cartelle copiate intere (tutti i file, con o senza topic: data-platform)
DP_FOLDERS = [
    "20 PROJECTS/DATA PLATFORM",
    "30 WIKI/DATA PLATFORM",
]

# File singoli da copiare
DP_FILES = [
    "30 WIKI/DATA PLATFORM.md",
    "00 TODO/DATA PLATFORM VAULT.md",
    "40 NOTE/STATISTICHE DIMENSIONI DOWNLOAD.md",
    "50 IDEE/POSTGRES_FDW.md",
    # Conversazioni AI — ChatGPT
    "30 WIKI/AI/CONVERSATIONS/CHATGPT/CDC Oracle to PostgreSQL.md",
    "30 WIKI/AI/CONVERSATIONS/CHATGPT/Errore trigger Oracle.md",
    "30 WIKI/AI/CONVERSATIONS/CHATGPT/Integrazione SDI DP Analisi.md",
    "30 WIKI/AI/CONVERSATIONS/CHATGPT/Oracle string_agg alternative.md",
    "30 WIKI/AI/CONVERSATIONS/CHATGPT/Ottimizzazione query PostgreSQL.md",
    "30 WIKI/AI/CONVERSATIONS/CHATGPT/Postgres Upsert Syntax.md",
    # Conversazioni AI — Claude
    "30 WIKI/AI/CONVERSATIONS/CLAUDE/dbt YAML schema for daily media calculations.md",
    # Conversazioni AI — Gemini
    "30 WIKI/AI/CONVERSATIONS/GEMINI/Analisi Architettura Data Lake_ .md",
    "30 WIKI/AI/CONVERSATIONS/GEMINI/Analisi Architettura Data Platform Regionale_ .md",
    "30 WIKI/AI/CONVERSATIONS/GEMINI/Architetture Open Source Simili_ .md",
    "30 WIKI/AI/CONVERSATIONS/GEMINI/CDC Oracle 11g a PostgreSQL.md",
    "30 WIKI/AI/CONVERSATIONS/GEMINI/Cataloghi Data Lake - Differenze Nessie, Polaris e Unity.md",
    "30 WIKI/AI/CONVERSATIONS/GEMINI/Connettori dbt e Python.md",
    "30 WIKI/AI/CONVERSATIONS/GEMINI/Dremio S3 REST API Access.md",
    "30 WIKI/AI/CONVERSATIONS/GEMINI/Dremio vs Trino.md",
    "30 WIKI/AI/CONVERSATIONS/GEMINI/DuckDB Postgres Query Engine.md",
    "30 WIKI/AI/CONVERSATIONS/GEMINI/Integrazione SDI_DP_ Analisi e Proposte_ .md",
    "30 WIKI/AI/CONVERSATIONS/GEMINI/Nessie vs LakeKeeper.md",
    "30 WIKI/AI/CONVERSATIONS/GEMINI/OpenMetadata for data quality.md",
    "30 WIKI/AI/CONVERSATIONS/GEMINI/Oracle 11g Materialized View Refresh Script.md",
    "30 WIKI/AI/CONVERSATIONS/GEMINI/Orchestratori Data Platform_ Analisi Comparativa 1.md",
    "30 WIKI/AI/CONVERSATIONS/GEMINI/Orchestratori Data Platform_ Analisi Comparativa 2.md",
    "30 WIKI/AI/CONVERSATIONS/GEMINI/SDI Data Integration to Data Platform.md",
    "30 WIKI/AI/CONVERSATIONS/GEMINI/Sintesi Architettura Dati e Criticità_ .md",
    # Conversazioni AI — Perplexity
    "30 WIKI/AI/CONVERSATIONS/PERPLEXITY/Come installare il server mcp di Dremio.md",
    "30 WIKI/AI/CONVERSATIONS/PERPLEXITY/Cosa è Openmetadata Unified Knowledge Graph_.md",
]

# Attachment referenziati esplicitamente da file dp
DP_ATTACHMENTS = [
    "99 System/attachments/Pasted image 20260206112552.png",
    "99 System/attachments/LD23GPS-PA7665-001-DataPlatform_v01_03 1.pdf",
    "99 System/attachments/04_09_56.jpg",
    "99 System/attachments/architettura_data_platform.html",
    "99 System/attachments/ICEBERG/Fig1-1-1024x576.png",
    "99 System/attachments/ICEBERG/catalog-1536x781.png",
    "99 System/attachments/INTEGRAZIONI/dbt-dremio.png",
]

# ── MOC da aggiornare nel vault originale ─────────────────────────────────────

# Rimozione per linea (wikilink a file dp)
MOC_LINE_FILES = [
    "30 WIKI/30 WIKI.md",
    "30 WIKI/AI/CONVERSATIONS/CHATGPT/CHATGPT.md",
    "30 WIKI/AI/CONVERSATIONS/CLAUDE/CLAUDE.md",
    "30 WIKI/AI/CONVERSATIONS/GEMINI/GEMINI.md",
    "30 WIKI/AI/CONVERSATIONS/PERPLEXITY/PERPLEXITY.md",
    "40 NOTE/40 NOTE.md",
    "50 IDEE/50 IDEE.md",
]

# Rimozione per sezione (rimuove intera sezione ## fino alla successiva ##)
MOC_SECTION_FILES = {
    "00 TODO/00 TODO.md": "DATA PLATFORM",
}

# ── Helpers ────────────────────────────────────────────────────────────────────

WIKILINK_RE = re.compile(r'\[\[([^\]|#]+?)(?:[|#][^\]]*?)?\]\]')


def log(msg: str) -> None:
    print(msg)


def copy_file(src: Path, dst: Path) -> None:
    rel = src.relative_to(VAULT_SRC)
    if DRY_RUN:
        log(f"  [DRY] {rel}")
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    log(f"  COPY  {rel}")


def build_dp_stems() -> set[str]:
    """Raccoglie i filename stem di tutti i file dp (per matching wikilink)."""
    stems: set[str] = set()
    for folder in DP_FOLDERS:
        folder_path = VAULT_SRC / folder
        if folder_path.exists():
            for f in folder_path.rglob("*.md"):
                stems.add(f.stem)
    for rel in DP_FILES:
        stems.add(Path(rel).stem)
    return stems


def line_has_dp_wikilink(line: str, dp_stems: set[str]) -> bool:
    for m in WIKILINK_RE.finditer(line):
        target = m.group(1).strip()
        # Wikilink con percorso (es. [[20 PROJECTS/DATA PLATFORM/PROCESSO/AMBIENTI]])
        if (target.startswith("20 PROJECTS/DATA PLATFORM")
                or target.startswith("30 WIKI/DATA PLATFORM")):
            return True
        # Wikilink per nome file (es. [[Dremio vs Trino]])
        stem = Path(target).stem
        if stem in dp_stems:
            return True
    return False


def remove_dp_lines(text: str, dp_stems: set[str]) -> tuple[str, list[str]]:
    """Rimuove le righe con wikilink a file dp. Ritorna (testo_pulito, righe_rimosse)."""
    kept, removed = [], []
    for line in text.splitlines(keepends=True):
        if line_has_dp_wikilink(line, dp_stems):
            removed.append(line.rstrip())
        else:
            kept.append(line)
    return "".join(kept), removed


def remove_section(text: str, section_title: str) -> tuple[str, str]:
    """Rimuove la sezione ## <section_title> fino alla prossima ## o fine file."""
    lines = text.splitlines(keepends=True)
    kept, removed_lines = [], []
    inside = False
    for line in lines:
        if re.match(rf'^## {re.escape(section_title)}\s*$', line):
            inside = True
        elif inside and re.match(r'^## ', line):
            inside = False
        if inside:
            removed_lines.append(line.rstrip())
        else:
            kept.append(line)
    return "".join(kept), "\n".join(removed_lines)


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    mode = "DRY RUN" if DRY_RUN else "LIVE"
    log(f"\n{'='*60}")
    log(f"Vault Split — {mode}")
    log(f"SRC: {VAULT_SRC}")
    log(f"DST: {VAULT_DST}")
    log(f"{'='*60}\n")

    dp_stems = build_dp_stems()
    log(f"File dp identificati: {len(dp_stems)} stem\n")

    # ── 1. Copia cartelle dp ───────────────────────────────────────────────────
    log("## 1. Copia cartelle dp")
    for folder in DP_FOLDERS:
        src_folder = VAULT_SRC / folder
        if not src_folder.exists():
            log(f"  WARNING: {folder} non trovata")
            continue
        log(f"  Cartella: {folder}")
        for src_file in sorted(src_folder.rglob("*")):
            if src_file.is_file():
                copy_file(src_file, VAULT_DST / src_file.relative_to(VAULT_SRC))

    # ── 2. Copia file dp singoli ───────────────────────────────────────────────
    log("\n## 2. Copia file dp singoli")
    for rel in DP_FILES:
        src_file = VAULT_SRC / rel
        if not src_file.exists():
            log(f"  WARNING: non trovato — {rel}")
            continue
        copy_file(src_file, VAULT_DST / rel)

    # ── 3. Copia attachment ────────────────────────────────────────────────────
    log("\n## 3. Copia attachment")
    for rel in DP_ATTACHMENTS:
        src_file = VAULT_SRC / rel
        if not src_file.exists():
            log(f"  WARNING: non trovato — {rel}")
            continue
        copy_file(src_file, VAULT_DST / rel)

    # ── 4. Copia .obsidian ─────────────────────────────────────────────────────
    log("\n## 4. Copia .obsidian config")
    obsidian_src = VAULT_SRC / ".obsidian"
    obsidian_dst = VAULT_DST / ".obsidian"
    if DRY_RUN:
        log(f"  [DRY] .obsidian/  →  {obsidian_dst}")
    else:
        if obsidian_dst.exists():
            shutil.rmtree(obsidian_dst)
        shutil.copytree(obsidian_src, obsidian_dst)
        log(f"  COPY  .obsidian/")

    # ── 5. Aggiorna MOC (rimozione per linea) ──────────────────────────────────
    log("\n## 5. Aggiorna MOC — rimozione wikilink dp")
    for moc_rel in MOC_LINE_FILES:
        moc_path = VAULT_SRC / moc_rel
        log(f"\n  {moc_rel}")
        if not moc_path.exists():
            log("    WARNING: non trovato")
            continue
        text = moc_path.read_text(encoding="utf-8")
        cleaned, removed = remove_dp_lines(text, dp_stems)
        if removed:
            for r in removed:
                log(f"    - REMOVE: {r!r}")
            if not DRY_RUN:
                moc_path.write_text(cleaned, encoding="utf-8")
                log("    → Salvato")
        else:
            log("    nessun link dp trovato")

    # ── 6. Aggiorna MOC (rimozione per sezione) ────────────────────────────────
    log("\n## 6. Aggiorna MOC — rimozione sezioni dp")
    for moc_rel, section_title in MOC_SECTION_FILES.items():
        moc_path = VAULT_SRC / moc_rel
        log(f"\n  {moc_rel}  [sezione: ## {section_title}]")
        if not moc_path.exists():
            log("    WARNING: non trovato")
            continue
        text = moc_path.read_text(encoding="utf-8")
        cleaned, removed_section = remove_section(text, section_title)
        if removed_section:
            log(f"    Rimosso ({removed_section.count(chr(10)) + 1} righe):")
            for line in removed_section.splitlines()[:5]:
                log(f"      {line!r}")
            if removed_section.count("\n") > 4:
                log(f"      ... ({removed_section.count(chr(10)) - 4} righe ulteriori)")
            if not DRY_RUN:
                moc_path.write_text(cleaned, encoding="utf-8")
                log("    → Salvato")
        else:
            log(f"    sezione '## {section_title}' non trovata")

    # ── Fine ───────────────────────────────────────────────────────────────────
    log(f"\n{'='*60}")
    if DRY_RUN:
        log("DRY RUN completato — nessun file modificato.")
        log("Imposta DRY_RUN = False per eseguire.")
    else:
        log("Completato.")
    log(f"{'='*60}")
    log("\nPassi manuali successivi:")
    log("  1. Apri VAULT_DST in Obsidian come nuovo vault")
    log("  2. cd VAULT_DST && git init && git remote add origin <nuovo-remote>")
    log("  3. Verifica/aggiorna config obsidian-git nel nuovo vault")
    log("  4. Elimina i file dp dal vault originale (cartelle + file singoli)")
    log("  5. Verifica che obsidian-git del vault originale punti ancora al remote corretto\n")


if __name__ == "__main__":
    main()
