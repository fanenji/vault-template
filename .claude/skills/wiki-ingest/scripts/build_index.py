#!/usr/bin/env python3
"""
build_index.py — rigenera wiki/index.md deterministicamente dal filesystem.

L'indice è una funzione pura delle pagine presenti in wiki/: farlo generare
all'LLM (come nel backend originale) rischiava di perdere voci esistenti su
generazioni troncate o pigre. Qui si scandisce wiki/, si raggruppa per type
(dal frontmatter, con fallback sulla cartella) e si emette un indice stabile.

Uso:
    python build_index.py            # riscrive wiki/index.md
    python build_index.py --stdout   # stampa senza scrivere

Chiamato automaticamente da finalize.py dopo ogni ingest.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

# Sezioni in ordine di presentazione: (type, cartella, intestazione)
SECTIONS = [
    ("entity", "entities", "Entities"),
    ("concept", "concepts", "Concepts"),
    ("source", "sources", "Sources"),
    ("query", "queries", "Queries"),
    ("synthesis", "synthesis", "Synthesis"),
]

EXCLUDED_NAMES = {"index.md", "log.md", "overview.md"}

_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_TITLE_RE = re.compile(r"^title:\s*(.+)\s*$", re.MULTILINE)
_TYPE_RE = re.compile(r"^type:\s*(\S+)\s*$", re.MULTILINE)


def find_vault_root(start: Path) -> Path:
    cur = start.resolve()
    while True:
        if (cur / "wiki").is_dir() and (cur / ".llm-wiki").exists():
            return cur
        if cur.parent == cur:
            raise SystemExit(f"Non trovo una vault llm-wiki risalendo da {start}")
        cur = cur.parent


def _page_meta(path: Path) -> tuple[str | None, str]:
    """Ritorna (type, title) dal frontmatter, best-effort."""
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None, path.stem
    m = _FM_RE.match(content)
    if not m:
        return None, path.stem
    fm = m.group(1)
    tm = _TYPE_RE.search(fm)
    ttl = _TITLE_RE.search(fm)
    title = ttl.group(1).strip().strip('"').strip("'") if ttl else path.stem
    return (tm.group(1).strip() if tm else None), title


def build_index(vault_root: Path) -> str:
    wiki_root = vault_root / "wiki"
    # type → list di (slug, title), slug = basename senza .md
    pages_by_type: dict[str, list[tuple[str, str]]] = {}
    folder_to_type = {folder: t for t, folder, _ in SECTIONS}

    for path in sorted(wiki_root.rglob("*.md")):
        if path.name in EXCLUDED_NAMES:
            continue
        page_type, title = _page_meta(path)
        if page_type not in folder_to_type.values() and page_type not in dict(
            (t, t) for t, _, _ in SECTIONS
        ):
            # type assente/sconosciuto: fallback sulla cartella di primo livello
            rel_parts = path.relative_to(wiki_root).parts
            page_type = folder_to_type.get(rel_parts[0]) if len(rel_parts) > 1 else None
        if page_type is None:
            page_type = "other"
        pages_by_type.setdefault(page_type, []).append((path.stem, title))

    total = sum(len(v) for v in pages_by_type.values())

    out = [
        "---",
        "type: index",
        'title: "Wiki Index"',
        "auto_generated: true",
        f"updated: {date.today().isoformat()}",
        "---",
        "",
        "# Wiki Index",
        "",
        "> Generato automaticamente da `build_index.py` — non modificare a mano.",
        "",
    ]

    if total == 0:
        out.append("_(Vuoto — esegui il primo ingest per popolare l'indice.)_")
        out.append("")
        return "\n".join(out)

    for page_type, _folder, heading in SECTIONS:
        entries = pages_by_type.get(page_type, [])
        if not entries:
            continue
        out.append(f"## {heading} ({len(entries)})")
        out.append("")
        for slug, title in sorted(entries, key=lambda e: e[0]):
            label = f" — {title}" if title and title != slug else ""
            out.append(f"- [[{slug}]]{label}")
        out.append("")

    extra = pages_by_type.get("other", [])
    if extra:
        out.append(f"## Other ({len(extra)})")
        out.append("")
        for slug, title in sorted(extra, key=lambda e: e[0]):
            out.append(f"- [[{slug}]] — {title}")
        out.append("")

    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="Rigenera wiki/index.md dal filesystem")
    ap.add_argument("--stdout", action="store_true", help="Stampa senza scrivere su file")
    args = ap.parse_args()

    vault_root = find_vault_root(Path.cwd())
    content = build_index(vault_root)

    if args.stdout:
        print(content)
    else:
        (vault_root / "wiki" / "index.md").write_text(content, encoding="utf-8")
        print("✓ wiki/index.md rigenerato", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
