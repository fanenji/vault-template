#!/usr/bin/env python3
"""
preprocess.py — converte un file sorgente (PDF/DOCX/PPTX/XLSX/HTML/MD/TXT)
in markdown plain via MarkItDown.

Sostituisce il preprocessing Rust del backend originale (pdfium / calamine /
docx-rs / pptx). Output: markdown su stdout.

Uso:
    python preprocess.py <path> [--max-chars 50000]

Il cap di caratteri si legge (in ordine): --max-chars, `.llm-wiki/config.json`
(ingest.max_chars), default 50000. Su troncamento viene emesso un warning
su stderr (il contenuto oltre il cap NON viene ingerito).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def find_vault_root(start: Path) -> Path | None:
    cur = start.resolve()
    while True:
        if (cur / "wiki").is_dir() and (cur / ".llm-wiki").exists():
            return cur
        if cur.parent == cur:
            return None
        cur = cur.parent


def load_vault_config(vault_root: Path | None) -> dict:
    """Legge `.llm-wiki/config.json` (best-effort, {} se assente/corrotto)."""
    if vault_root is None:
        return {}
    p = vault_root / ".llm-wiki" / "config.json"
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def preprocess(path: Path, max_chars: int | None = None) -> str:
    """Converti `path` in markdown.

    - Per .md/.txt: legge direttamente.
    - Per altri formati: usa MarkItDown.
    - Tronca a `max_chars` se specificato (replica del cap a 50_000 dell'originale).
    """
    suffix = path.suffix.lower()

    if suffix in (".md", ".markdown", ".txt"):
        content = path.read_text(encoding="utf-8", errors="replace")
    else:
        try:
            from markitdown import MarkItDown
        except ImportError:
            print(
                "Errore: markitdown non installato. Esegui:\n"
                "    pip install 'markitdown[all]'",
                file=sys.stderr,
            )
            sys.exit(2)

        md = MarkItDown()
        try:
            result = md.convert(str(path))
            content = result.text_content
        except Exception as e:
            print(f"Errore conversione {path}: {e}", file=sys.stderr)
            sys.exit(3)

    if max_chars and len(content) > max_chars:
        print(
            f"⚠ {path.name}: contenuto troncato a {max_chars} char "
            f"(originale: {len(content)}). Il testo oltre il cap NON viene ingerito — "
            f"valuta di alzare ingest.max_chars in config.json o spezzare il documento.",
            file=sys.stderr,
        )
        content = content[:max_chars] + "\n\n[...truncated...]"

    return content


def main() -> int:
    ap = argparse.ArgumentParser(description="Preprocess a document → markdown")
    ap.add_argument("path", type=Path, help="Source file path")
    ap.add_argument("--max-chars", type=int, default=None,
                    help="Tronca a N caratteri (default: config.json o 50000)")
    args = ap.parse_args()

    if not args.path.is_file():
        print(f"Errore: file non trovato: {args.path}", file=sys.stderr)
        return 1

    config = load_vault_config(find_vault_root(Path.cwd()))
    max_chars = args.max_chars if args.max_chars is not None else \
        config.get("ingest", {}).get("max_chars", 50_000)

    print(preprocess(args.path, max_chars))
    return 0


if __name__ == "__main__":
    sys.exit(main())
