#!/usr/bin/env python3
"""
fix_link_sources.py — migra il frontmatter delle pagine wiki/sources/ esistenti
al formato normalizzato (vedi _source_meta.py):

  - `source_path: raw/sources/foo.md`  →  `source_path: "[[raw/sources/foo]]"`
  - `sources: [foo.md]`                →  `sources: ["<url>"]` se il documento
    raw è un markdown con campo `source:` (URL pagina originale) nel
    frontmatter; altrimenti `sources` resta invariato.

Idempotente: ri-eseguirlo su pagine già migrate non cambia nulla. Le pagine
il cui documento raw non esiste su disco vengono saltate con warning (le
segnala già wiki-lint come frontmatter-ref).

Uso:
    python fix_link_sources.py [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _merge_pages import fm_payload, _split_fm_segments
from _source_meta import RAW_SOURCES_DIR, raw_wikilink, extract_source_url, apply_source_meta


def find_vault_root(start: Path) -> Path:
    cur = start.resolve()
    while True:
        if (cur / "wiki").is_dir() and (cur / ".llm-wiki").exists():
            return cur
        if cur.parent == cur:
            raise SystemExit(f"Non trovo una vault llm-wiki risalendo da {start}")
        cur = cur.parent


def current_source_path_value(content: str) -> str | None:
    """Valore grezzo del campo source_path dal frontmatter (None se assente)."""
    payload, _ = fm_payload(content)
    if payload is None:
        return None
    for key, lines in _split_fm_segments(payload):
        if key == "source_path":
            value = lines[0].partition(":")[2].strip()
            return value.strip("\"'") or None
    return None


def resolve_raw_file(vault_root: Path, source_path_value: str) -> Path | None:
    """
    Risolve il documento in raw/sources/ a partire dal valore corrente di
    source_path (path semplice, wikilink già migrato, o bare filename).
    Il wikilink dei markdown omette `.md`: si prova anche con il suffisso.
    """
    target = source_path_value.strip()
    if target.startswith("[[") and target.endswith("]]"):
        target = target[2:-2].strip()
    candidates = [target, f"{RAW_SOURCES_DIR}/{Path(target).name}"]
    candidates += [f"{c}.md" for c in candidates]
    for c in candidates:
        p = vault_root / c
        if p.is_file():
            return p
    return None


def fix_page(vault_root: Path, page: Path, dry_run: bool) -> str:
    """Migra una pagina. Ritorna l'esito: 'updated' | 'unchanged' | 'skipped'."""
    rel = page.relative_to(vault_root)
    content = page.read_text(encoding="utf-8")

    sp_value = current_source_path_value(content)
    if sp_value is None:
        print(f"  ⚠ {rel}: nessun campo source_path — saltata", file=sys.stderr)
        return "skipped"

    raw_file = resolve_raw_file(vault_root, sp_value)
    if raw_file is None:
        print(f"  ⚠ {rel}: documento raw non trovato per source_path "
              f"`{sp_value}` — saltata (vedi wiki-lint frontmatter-ref)", file=sys.stderr)
        return "skipped"

    url = extract_source_url(raw_file)
    fixed = apply_source_meta(content, raw_wikilink(raw_file.name), url)
    if fixed == content:
        return "unchanged"

    if dry_run:
        print(f"  → {rel}: source_path → {raw_wikilink(raw_file.name)}"
              + (f", sources → [\"{url}\"]" if url else ""))
    else:
        page.write_text(fixed, encoding="utf-8")
        print(f"  ✓ {rel}" + (f" (url: {url})" if url else ""))
    return "updated"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Migra source_path/sources delle pagine wiki/sources/ al formato wikilink/URL")
    ap.add_argument("--dry-run", action="store_true",
                    help="Mostra le modifiche senza scrivere")
    args = ap.parse_args()

    vault_root = find_vault_root(Path.cwd())
    sources_dir = vault_root / "wiki" / "sources"
    if not sources_dir.is_dir():
        print(f"Nessuna directory {sources_dir}", file=sys.stderr)
        return 1

    pages = sorted(p for p in sources_dir.glob("*.md") if p.name != "index.md")
    if not pages:
        print("Nessuna pagina in wiki/sources/.")
        return 0

    counts = {"updated": 0, "unchanged": 0, "skipped": 0}
    for page in pages:
        counts[fix_page(vault_root, page, args.dry_run)] += 1

    label = "da aggiornare" if args.dry_run else "aggiornate"
    print(f"\nDone — {counts['updated']} {label}, {counts['unchanged']} già a posto, "
          f"{counts['skipped']} saltate.")
    if counts["updated"] and not args.dry_run:
        print("Ricorda: `qmd update && qmd embed` dalla vault root per riallineare l'indice.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
