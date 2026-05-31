#!/usr/bin/env python3
"""
finalize.py — finalizza l'ingest scrivendo i FILE blocks su disco.

Riceve in input il testo grezzo dello "step-2 generation" (FILE/REVIEW blocks)
e fa:
  1. Parse + sanitize + path safety check
  2. Merge con pagine esistenti (se servono, segnala "merge_needed")
  3. Write to disk (entities, concepts, sources, queries, synthesis)
  4. Append a log.md
  5. Overwrite di index.md e overview.md
  6. Save cache SHA256
  7. Aggiorna l'indice QMD (qmd update && qmd embed)

Stampa su stdout un riassunto JSON: { written_paths, warnings, reviews,
merge_needed: [{path, existing, incoming}, ...] }.

Uso:
    python finalize.py \\
        --source <path/to/source.pdf> \\
        --generation-file /tmp/gen.txt \\
        [--skip-cache] [--skip-qmd-update]
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

# Import moduli locali
sys.path.insert(0, str(Path(__file__).parent))
from _parse_file_blocks import parse_blocks, ParsedFileBlock
from _sanitize import sanitize_ingested_content
from _merge_pages import merge_pages, MergeOutcome
import cache as cache_mod


# ── Helpers ────────────────────────────────────────────────────────────────────

def find_vault_root(start: Path) -> Path:
    cur = start.resolve()
    while True:
        if (cur / "wiki").is_dir() and (cur / ".llm-wiki").exists():
            return cur
        if cur.parent == cur:
            raise SystemExit(f"Non trovo una vault llm-wiki risalendo da {start}")
        cur = cur.parent


def append_log(vault_root: Path, line: str) -> None:
    log_path = vault_root / "wiki" / "log.md"
    existing = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    log_path.write_text(existing.rstrip() + "\n" + line + "\n", encoding="utf-8")


def write_file(vault_root: Path, rel_path: str, content: str) -> None:
    full = vault_root / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")


def is_overwrite_target(rel_path: str) -> bool:
    """Index e overview vengono sempre sovrascritti (no merge)."""
    return rel_path in ("wiki/index.md", "wiki/overview.md") or \
           rel_path.endswith("/index.md") or rel_path.endswith("/overview.md")


def is_log_target(rel_path: str) -> bool:
    return rel_path == "wiki/log.md" or rel_path.endswith("/log.md")


# ── Main pipeline ──────────────────────────────────────────────────────────────

def finalize(
    vault_root: Path,
    source_path: Path,
    generation_text: str,
    skip_cache: bool = False,
    skip_qmd_update: bool = False,
    skip_archive: bool = False,
) -> dict:
    """
    Esegue il finalize. Ritorna un dict con:
      - written_paths: list[str] (rel a vault)
      - warnings: list[str]
      - reviews: list[dict]
      - merge_needed: list[{path, existing, incoming}] — pagine che richiedono LLM merge body
      - hard_failures: list[str]
    """
    parse_result = parse_blocks(generation_text)
    blocks = parse_result.blocks
    warnings = list(parse_result.warnings)
    reviews = [
        {
            "type": r.type,
            "title": r.title,
            "body": r.body,
            "options": r.options,
            "pages": r.pages,
            "search": r.search,
        }
        for r in parse_result.reviews
    ]
    merge_needed: list[dict] = []
    written_paths: list[str] = []
    hard_failures: list[str] = []

    for block in blocks:
        rel = block.path
        raw = block.content
        sanitized = sanitize_ingested_content(raw)
        full = vault_root / rel

        try:
            if is_log_target(rel):
                existing = full.read_text(encoding="utf-8") if full.exists() else ""
                merged = (existing.rstrip() + "\n\n" + sanitized.strip() + "\n") if existing else sanitized
                write_file(vault_root, rel, merged)
            elif is_overwrite_target(rel):
                write_file(vault_root, rel, sanitized)
            else:
                # Content page: merge con esistente se presente
                existing = full.read_text(encoding="utf-8") if full.exists() else None
                outcome: MergeOutcome = merge_pages(sanitized, existing, source_path.name)
                write_file(vault_root, rel, outcome.content)
                if outcome.merge_body_needed:
                    merge_needed.append({
                        "path": rel,
                        "existing_body": outcome.existing_body,
                        "incoming_body": outcome.incoming_body,
                    })
                    warnings.append(
                        f"`{rel}` merged with array-union only — LLM body merge recommended (use prompts/merge.md)"
                    )

            written_paths.append(rel)
        except OSError as e:
            warnings.append(f'Failed to write "{rel}": {e}')
            hard_failures.append(rel)

    # Append log entry
    from datetime import datetime
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    append_log(vault_root, f"- {ts} — ingest: {source_path.name} → {len(written_paths)} files")

    # Cache save (solo se 0 hard failures)
    if not skip_cache and written_paths and not hard_failures:
        try:
            cache_mod.save_entry(vault_root, source_path.resolve(), written_paths)
        except Exception as e:
            warnings.append(f"Failed to save cache: {e}")

    # QMD index update (qmd 2.5.2: indice project-local .qmd/, discovery dal cwd).
    # `qmd update` re-indicizza le collection (rileva i file nuovi/rimossi),
    # `qmd embed` genera i vettori mancanti. cwd = vault_root → usa l'indice locale.
    if not skip_qmd_update and written_paths:
        try:
            for cmd in (["qmd", "update"], ["qmd", "embed"]):
                subprocess.run(
                    cmd,
                    cwd=str(vault_root),
                    timeout=300,
                    check=False,
                    capture_output=True,
                )
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            warnings.append(f"QMD index update failed: {e} (run `qmd update && qmd embed` manually)")

    # Archiviazione sorgente (solo su ingest pienamente riuscito): sposta
    # l'originale da _inbox a raw/sources/ (raw/ = source of truth immutabile).
    # Se l'originale è già sotto raw/sources/ non si tocca.
    archived_source: str | None = None
    if not skip_archive and written_paths and not hard_failures:
        try:
            src = source_path.resolve()
            raw_sources = (vault_root / "raw" / "sources").resolve()
            already_archived = raw_sources in src.parents
            if src.exists() and not already_archived:
                raw_sources.mkdir(parents=True, exist_ok=True)
                dest = raw_sources / src.name
                if dest.exists():
                    # Copia già archiviata: rimuovo solo l'originale da _inbox.
                    src.unlink()
                else:
                    shutil.move(str(src), str(dest))
                archived_source = str(dest.relative_to(vault_root))
        except OSError as e:
            warnings.append(f"Archiviazione sorgente fallita: {e} (sposta manualmente in raw/sources/)")

    return {
        "written_paths": written_paths,
        "warnings": warnings,
        "reviews": reviews,
        "merge_needed": merge_needed,
        "hard_failures": hard_failures,
        "archived_source": archived_source,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Finalize an ingest: parse FILE blocks → write to disk → update QMD")
    ap.add_argument("--source", type=Path, required=True, help="Original source file path")
    ap.add_argument("--generation-file", type=Path, required=True,
                    help="File con l'output grezzo dello step-2 generation")
    ap.add_argument("--skip-cache", action="store_true", help="Non salvare la cache SHA256")
    ap.add_argument("--skip-qmd-update", action="store_true", help="Non aggiornare l'indice QMD")
    ap.add_argument("--no-archive", action="store_true",
                    help="Non spostare il sorgente in raw/sources/ dopo l'ingest")
    args = ap.parse_args()

    vault_root = find_vault_root(Path.cwd())

    generation_text = args.generation_file.read_text(encoding="utf-8")
    result = finalize(
        vault_root=vault_root,
        source_path=args.source,
        generation_text=generation_text,
        skip_cache=args.skip_cache,
        skip_qmd_update=args.skip_qmd_update,
        skip_archive=args.no_archive,
    )

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if not result["hard_failures"] else 1


if __name__ == "__main__":
    sys.exit(main())
