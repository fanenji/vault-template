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

Riparazione frontmatter: se al frontmatter manca il `---` di apertura (pattern
pregresso: il file inizia con `type: ...` e ha solo il `---` di chiusura), viene
premesso il delimitatore mancante — in modo conservativo, solo quando il blocco
iniziale ha davvero la forma di un frontmatter — e poi si procede normalmente.
Senza un `source_path` derivabile, la sola riparazione del fence viene comunque
salvata (frontmatter rotto → valido).

Idempotente: ri-eseguirlo su pagine già migrate non cambia nulla. Le pagine
senza né `source_path` né un `sources` risolvibile (e senza frontmatter da
riparare) vengono saltate con warning (le segnala già wiki-lint come
frontmatter-ref).

Uso:
    python fix_link_sources.py [--dry-run]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _merge_pages import fm_payload, _split_fm_segments, _TOP_KEY_RE
from _source_meta import RAW_SOURCES_DIR, raw_wikilink, extract_source_url, apply_source_meta

_QUOTED_RE = re.compile(r'"([^"]*)"|\'([^\']*)\'')


def _looks_like_fm_line(line: str) -> bool:
    """Una riga plausibile dentro un frontmatter YAML: key top-level, item di
    block sequence, riga indentata (continuazione/nested), vuota o commento."""
    stripped = line.strip()
    if stripped == "" or stripped.startswith("#"):
        return True
    if line != line.lstrip():            # indentata → continuazione/nested
        return True
    if stripped.startswith("- "):        # item di block sequence
        return True
    return bool(_TOP_KEY_RE.match(line))  # key: a colonna 0


def repair_missing_fence(content: str) -> str | None:
    """Ripara il frontmatter a cui manca il `---` di apertura (pattern pregresso:
    il file inizia direttamente con `type: ...` e ha solo il `---` di chiusura).

    Ritorna il contenuto riparato (con `---\\n` premesso) solo se il blocco
    iniziale ha davvero la forma di un frontmatter; altrimenti None. Conservativo:
    non tocca file con frontmatter già valido né body che iniziano con prosa.
    """
    if fm_payload(content)[0] is not None:
        return None                      # frontmatter già valido
    lines = content.split("\n")
    if not lines or not _TOP_KEY_RE.match(lines[0]):
        return None                      # non inizia con una key YAML
    fence_idx = next((i for i, ln in enumerate(lines) if ln.strip() == "---"), None)
    if not fence_idx:                    # nessun `---` di chiusura, o è la riga 0
        return None
    if not all(_looks_like_fm_line(ln) for ln in lines[:fence_idx]):
        return None                      # qualcosa prima del fence non è frontmatter
    repaired = "---\n" + content
    return repaired if fm_payload(repaired)[0] is not None else None


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


def _resolve_sources(vault_root: Path, content: str) -> tuple[list[Path], list[str]]:
    """Risolve i documenti raw dai filename in `sources` (fallback quando
    `source_path` è assente). Ritorna (trovati, mancanti)."""
    names = [v for v in current_sources_values(content) if not _is_url(v)]
    found: list[Path] = []
    missing: list[str] = []
    for name in names:
        rf = resolve_raw_file(vault_root, name)
        (found if rf is not None else missing).append(rf if rf is not None else name)
    return found, missing


def fix_page(vault_root: Path, page: Path, dry_run: bool) -> str:
    """Migra una pagina. Ritorna l'esito: 'updated' | 'unchanged' | 'skipped'."""
    rel = page.relative_to(vault_root)
    content = page.read_text(encoding="utf-8")

    # Ripara il frontmatter privo del `---` di apertura, poi opera sul riparato.
    repaired = repair_missing_fence(content)
    working = repaired if repaired is not None else content
    fence_note = " (+ frontmatter riparato)" if repaired is not None else ""

    sp_value = current_source_path_value(working)
    if sp_value is not None:
        raw_file = resolve_raw_file(vault_root, sp_value)
        if raw_file is None:
            print(f"  ⚠ {rel}: documento raw non trovato per source_path "
                  f"`{sp_value}` — saltata (vedi wiki-lint frontmatter-ref)", file=sys.stderr)
            return "skipped"
        raw_files = [raw_file]
    else:
        # Fallback: nessun source_path → derivalo dai filename in `sources`.
        raw_files, missing = _resolve_sources(vault_root, working)
        if missing:
            print(f"  ⚠ {rel}: file di `sources` non trovati in raw/sources/ "
                  f"({', '.join(missing)})", file=sys.stderr)
        if not raw_files:
            # Nessun source_path derivabile. Se però abbiamo riparato il fence,
            # scriviamo comunque la riparazione (frontmatter rotto → valido).
            if repaired is not None:
                if dry_run:
                    print(f"  → {rel}: ripara frontmatter (--- di apertura); "
                          f"source_path non derivabile da `sources`")
                else:
                    page.write_text(working, encoding="utf-8")
                    print(f"  ✓ {rel}: frontmatter riparato (--- di apertura); "
                          f"source_path non derivabile da `sources`")
                return "updated"
            print(f"  ⚠ {rel}: nessun source_path e nessun file di `sources` "
                  f"risolvibile in raw/sources/ — saltata", file=sys.stderr)
            return "skipped"

    wikilinks = [raw_wikilink(rf.name) for rf in raw_files]
    urls = [extract_source_url(rf) for rf in raw_files]

    wl_arg: str | list[str] = wikilinks[0] if len(wikilinks) == 1 else wikilinks
    # Sostituisci `sources` con gli URL solo se TUTTI i raw ne hanno uno: così
    # non si perde la provenienza quando alcuni documenti non dichiarano source:.
    if urls and all(urls):
        url_arg: str | list[str] | None = urls[0] if len(urls) == 1 else urls
    else:
        url_arg = None

    fixed = apply_source_meta(working, wl_arg, url_arg)
    if fixed == content:
        return "unchanged"

    sp_repr = wikilinks[0] if len(wikilinks) == 1 else "[" + ", ".join(wikilinks) + "]"
    if dry_run:
        print(f"  → {rel}: source_path → {sp_repr}{fence_note}"
              + (f", sources → {url_arg}" if url_arg else ""))
    else:
        page.write_text(fixed, encoding="utf-8")
        print(f"  ✓ {rel}{fence_note}" + (f" (url: {url_arg})" if url_arg else ""))
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
