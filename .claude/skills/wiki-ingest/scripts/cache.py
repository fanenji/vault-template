#!/usr/bin/env python3
"""
cache.py — gestione cache SHA256 dell'ingest.

Porting di src/lib/ingest-cache.ts.

Cache file: `.llm-wiki/ingest-cache.json` con shape:
    { "entries": { "<filename>@<sha256[:12]>": { "hash": "<sha256>", "timestamp": ..., "files_written": [...] } } }

La chiave include un prefisso dell'hash del contenuto: due sorgenti omonime
in cartelle diverse (contenuto diverso) coesistono senza sovrascriversi, e
un file archiviato da _inbox/ a raw/sources/ (stesso contenuto) continua a
fare HIT. Cache hit: entry presente per (nome, hash) AND tutti i
files_written esistono ancora sul disco.

Uso:
    python cache.py check <source_path>           # exit 0 se hit (stampa files), 1 se miss
    python cache.py save <source_path> <file1> <file2> ...   # salva entry
    python cache.py remove <source_filename>      # rimuovi entry
    python cache.py list                          # dump cache su stdout
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path


def find_vault_root(start: Path) -> Path:
    cur = start.resolve()
    while True:
        if (cur / "wiki").is_dir() and (cur / ".llm-wiki").exists():
            return cur
        if cur.parent == cur:
            raise SystemExit(f"Non trovo una vault llm-wiki risalendo da {start}")
        cur = cur.parent


def cache_path(vault_root: Path) -> Path:
    return vault_root / ".llm-wiki" / "ingest-cache.json"


def load_cache(vault_root: Path) -> dict:
    p = cache_path(vault_root)
    if not p.exists():
        return {"entries": {}}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"entries": {}}


def save_cache(vault_root: Path, cache: dict) -> None:
    p = cache_path(vault_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def entry_key(source_filename: str, content_hash: str) -> str:
    return f"{source_filename}@{content_hash[:12]}"


def check_cache(vault_root: Path, source_path: Path) -> list[str] | None:
    """Ritorna lista files cached se hit, None se miss."""
    cache = load_cache(vault_root)
    current_hash = sha256_file(source_path)
    entries = cache.get("entries", {})
    # Lookup per chiave nome@hash; fallback sul formato legacy (solo nome)
    entry = entries.get(entry_key(source_path.name, current_hash)) or entries.get(source_path.name)
    if not entry:
        return None

    if entry.get("hash") != current_hash:
        return None

    files_written = entry.get("files_written", [])
    for rel in files_written:
        full = vault_root / rel if not Path(rel).is_absolute() else Path(rel)
        if not full.exists():
            # Cache stale: file cancellato dal disco. Treat as miss.
            return None

    return files_written


def save_entry(vault_root: Path, source_path: Path, files_written: list[str]) -> None:
    cache = load_cache(vault_root)
    content_hash = sha256_file(source_path)
    cache.setdefault("entries", {})[entry_key(source_path.name, content_hash)] = {
        "hash": content_hash,
        "timestamp": time.time(),
        "files_written": files_written,
    }
    save_cache(vault_root, cache)


def remove_entry(vault_root: Path, source_filename: str) -> bool:
    """Rimuove tutte le entry per quel basename (qualunque hash) — forza re-ingest."""
    cache = load_cache(vault_root)
    entries = cache.get("entries", {})
    to_remove = [k for k in entries
                 if k == source_filename or k.startswith(f"{source_filename}@")]
    if not to_remove:
        return False
    for k in to_remove:
        del entries[k]
    save_cache(vault_root, cache)
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="Ingest cache management")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ap_check = sub.add_parser("check", help="Check if source is cached")
    ap_check.add_argument("source_path", type=Path)

    ap_save = sub.add_parser("save", help="Save cache entry")
    ap_save.add_argument("source_path", type=Path)
    ap_save.add_argument("files_written", nargs="+", help="Relative wiki paths written")

    ap_remove = sub.add_parser("remove", help="Remove a cache entry")
    ap_remove.add_argument("source_filename")

    sub.add_parser("list", help="Dump cache to stdout")

    args = ap.parse_args()
    vault_root = find_vault_root(Path.cwd())

    if args.cmd == "check":
        result = check_cache(vault_root, args.source_path.resolve())
        if result is None:
            print("MISS", file=sys.stderr)
            return 1
        print(json.dumps(result))
        return 0

    if args.cmd == "save":
        save_entry(vault_root, args.source_path.resolve(), args.files_written)
        print(f"✓ Cached {args.source_path.name} → {len(args.files_written)} file(s)", file=sys.stderr)
        return 0

    if args.cmd == "remove":
        ok = remove_entry(vault_root, args.source_filename)
        print(f"{'✓ Removed' if ok else '⚠ Not found'}: {args.source_filename}", file=sys.stderr)
        return 0 if ok else 1

    if args.cmd == "list":
        print(json.dumps(load_cache(vault_root), indent=2, ensure_ascii=False))
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
