"""
_source_meta.py — normalizzazione frontmatter delle pagine wiki/sources/.

Due regole, applicate deterministicamente da finalize.py dopo il merge
(e retroattivamente da fix_link_sources.py sul pregresso):

  1. `source_path` è un wikilink al documento in raw/sources/, quotato per
     essere YAML valido: `source_path: "[[raw/sources/<nome>]]"`. Per i file
     markdown il wikilink omette l'estensione (convenzione Obsidian); per gli
     altri formati (pdf, docx, …) la mantiene.
  2. Se il documento sorgente è un markdown con frontmatter contenente un
     campo `source:` con la URL della pagina originale (pattern Obsidian Web
     Clipper), `sources` della pagina wiki/sources/ diventa `["<url>"]` —
     il filename è ridondante, c'è già source_path. Senza URL, `sources`
     resta invariato.
"""

from __future__ import annotations

import re
from pathlib import Path

from _merge_pages import _split_fm_segments, fm_payload, _wrap

RAW_SOURCES_DIR = "raw/sources"

_MD_SUFFIXES = (".md", ".markdown")
_URL_RE = re.compile(r"^https?://\S+$")
_SOURCE_FIELD_RE = re.compile(
    r'^source\s*:\s*["\']?(https?://[^\s"\']+)["\']?\s*$', re.MULTILINE
)
_FM_BLOCK_RE = re.compile(r"^---\s*\n(.*?)\n---\s*(\n|$)", re.DOTALL)


def raw_wikilink(source_filename: str) -> str:
    """Wikilink al documento in raw/sources/ (senza .md per i markdown)."""
    name = source_filename
    for suf in _MD_SUFFIXES:
        if name.lower().endswith(suf):
            name = name[: -len(suf)]
            break
    return f"[[{RAW_SOURCES_DIR}/{name}]]"


def extract_source_url(source_file: Path) -> str | None:
    """
    URL della pagina originale dal frontmatter del documento sorgente
    (campo `source:`). Solo per file markdown; None se assente o non-URL.
    """
    if source_file.suffix.lower() not in _MD_SUFFIXES:
        return None
    try:
        content = source_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    m = _FM_BLOCK_RE.match(content)
    if not m:
        return None
    sm = _SOURCE_FIELD_RE.search(m.group(1))
    return sm.group(1) if sm else None


def apply_source_meta(content: str, wikilink: str, url: str | None) -> str:
    """
    Riscrive nel frontmatter di una pagina wiki/sources/:
      - `source_path` → wikilink quotato (sostituito o aggiunto)
      - `sources` → `["<url>"]` se url è presente (altrimenti invariato)
    Gli altri campi sono preservati riga-per-riga. Senza frontmatter,
    il contenuto torna invariato (la pagina è già segnalata dal lint).
    """
    payload, body = fm_payload(content)
    if payload is None:
        return content

    source_path_line = f'source_path: "{wikilink}"'
    sources_line = f'sources: ["{url}"]' if url else None

    out_lines: list[str] = []
    seen_source_path = False
    seen_sources = False
    for key, lines in _split_fm_segments(payload):
        if key == "source_path":
            out_lines.append(source_path_line)
            seen_source_path = True
        elif key == "sources" and sources_line:
            out_lines.append(sources_line)
            seen_sources = True
        else:
            out_lines.extend(lines)

    if not seen_source_path:
        out_lines.append(source_path_line)
    if sources_line and not seen_sources:
        out_lines.append(sources_line)

    return _wrap("\n".join(out_lines), body)
