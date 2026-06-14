#!/usr/bin/env python3
"""
fix_link_sources.py — migra il frontmatter delle pagine wiki/sources/ esistenti
al formato normalizzato (vedi _source_meta.py):

  - `source_path: raw/sources/foo.md`  →  `source_path: "[[raw/sources/foo]]"`
  - `sources: [foo.md]`                →  `sources: ["<url>"]` se il documento
    raw è un markdown con campo `source:` (URL pagina originale) nel
    frontmatter; altrimenti `sources` resta invariato.

Fallback per le vault senza `source_path` (formato pregresso diverso): se la
pagina non ha `source_path` ma ha `sources` con uno o più nomi di file
risolvibili in `raw/sources/`, il `source_path` viene creato e valorizzato da
quei filename (wikilink singolo, o lista di wikilink se i file sono più d'uno),
e l'elaborazione prosegue normalmente (regola URL inclusa).

Idempotente: ri-eseguirlo su pagine già migrate non cambia nulla. Le pagine
senza né `source_path` né un `sources` risolvibile vengono saltate con warning
(le segnala già wiki-lint come frontmatter-ref).

Uso:
    python fix_link_sources.py [--dry-run]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _merge_pages import fm_payload, _split_fm_segments
from _source_meta import RAW_SOURCES_DIR, raw_wikilink, extract_source_url, apply_source_meta

_QUOTED_RE = re.compile(r'"([^"]*)"|\'([^\']*)\'')


def current_sources_values(content: str) -> list[str]:
    """Valori del campo `sources` dal frontmatter (lista vuota se assente).

    Gestisce sia la forma inline (`sources: ["a.md", "b.md"]` o `[a.md, b.md]`)
    sia la block sequence YAML (`- a.md` su righe successive). Per le liste
    inline gli item quotati sono estratti rispettando le virgole dentro i nomi
    file (es. `"Iceberg, The Right Idea.md"`).
    """
    payload, _ = fm_payload(content)
    if payload is None:
        return []
    for key, lines in _split_fm_segments(payload):
        if key != "sources":
            continue
        values: list[str] = []
        first = lines[0].partition(":")[2].strip()
        if first.startswith("["):
            inner = first[1:]
            if inner.endswith("]"):
                inner = inner[:-1]
            quoted = _QUOTED_RE.findall(inner)
            if quoted:
                values.extend(a or b for a, b in quoted)
            else:
                values.extend(p.strip() for p in inner.split(",") if p.strip())
        elif first and not first.startswith("#"):
            values.append(first.strip("\"'"))
        for ln in lines[1:]:
            s = ln.strip()
            if s.startswith("- "):
                item = s[2:].strip().strip("\"'")
                if item:
                    values.append(item)
        return values
    return []


def _is_url(value: str) -> bool:
    return value.startswith(("http://", "https://"))


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


def _resolve_sources(vault_root: Path, page: Path, rel: Path,
                     content: str) -> list[Path] | None:
    """Risolve i documenti raw a partire dai filename in `sources` (fallback
    quando `source_path` è assente). Ritorna la lista dei file trovati, o None
    se non c'è alcun filename risolvibile."""
    names = [v for v in current_sources_values(content) if not _is_url(v)]
    raw_files: list[Path] = []
    missing: list[str] = []
    for name in names:
        rf = resolve_raw_file(vault_root, name)
        if rf is not None:
            raw_files.append(rf)
        else:
            missing.append(name)
    if not raw_files:
        print(f"  ⚠ {rel}: nessun source_path e nessun file di `sources` "
              f"risolvibile in raw/sources/ — saltata", file=sys.stderr)
        return None
    if missing:
        print(f"  ⚠ {rel}: alcuni file di `sources` non trovati in raw/sources/ "
              f"({', '.join(missing)}) — uso solo i {len(raw_files)} trovati",
              file=sys.stderr)
    return raw_files


def fix_page(vault_root: Path, page: Path, dry_run: bool) -> str:
    """Migra una pagina. Ritorna l'esito: 'updated' | 'unchanged' | 'skipped'."""
    rel = page.relative_to(vault_root)
    content = page.read_text(encoding="utf-8")

    sp_value = current_source_path_value(content)
    if sp_value is not None:
        raw_file = resolve_raw_file(vault_root, sp_value)
        if raw_file is None:
            print(f"  ⚠ {rel}: documento raw non trovato per source_path "
                  f"`{sp_value}` — saltata (vedi wiki-lint frontmatter-ref)", file=sys.stderr)
            return "skipped"
        raw_files = [raw_file]
    else:
        # Fallback: nessun source_path → derivalo dai filename in `sources`.
        resolved = _resolve_sources(vault_root, page, rel, content)
        if resolved is None:
            return "skipped"
        raw_files = resolved

    wikilinks = [raw_wikilink(rf.name) for rf in raw_files]
    urls = [extract_source_url(rf) for rf in raw_files]

    wl_arg: str | list[str] = wikilinks[0] if len(wikilinks) == 1 else wikilinks
    # Sostituisci `sources` con gli URL solo se TUTTI i raw ne hanno uno: così
    # non si perde la provenienza quando alcuni documenti non dichiarano source:.
    if urls and all(urls):
        url_arg: str | list[str] | None = urls[0] if len(urls) == 1 else urls
    else:
        url_arg = None

    fixed = apply_source_meta(content, wl_arg, url_arg)
    if fixed == content:
        return "unchanged"

    sp_repr = wikilinks[0] if len(wikilinks) == 1 else "[" + ", ".join(wikilinks) + "]"
    if dry_run:
        print(f"  → {rel}: source_path → {sp_repr}"
              + (f", sources → {url_arg}" if url_arg else ""))
    else:
        page.write_text(fixed, encoding="utf-8")
        print(f"  ✓ {rel}" + (f" (url: {url_arg})" if url_arg else ""))
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
