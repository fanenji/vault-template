"""
_sanitize.py — pulisce l'output LLM prima del write a disco.

Porting fedele di src/lib/ingest-sanitize.ts (3 fix ricorrenti emersi dall'audit
del backend originale su 67 entity pages):

  1. Code fence esterno che avvolge tutta la pagina (```yaml ... ```)
  2. Prefisso `frontmatter:` prima del vero `---` block
  3. Wikilink list inline nel frontmatter (`related: [[a]], [[b]]`)

Conservativo: agisce solo su pattern ancorati a inizio documento o all'interno
del blocco frontmatter — mai sul body.
"""

from __future__ import annotations

import re


_OPEN_FENCE_RE = re.compile(r"^[ \t]*```(?:yaml|md|markdown)?[ \t]*\r?\n")
_CLOSE_FENCE_RE = re.compile(r"\r?\n[ \t]*```[ \t]*\r?\n?\s*$")
_FM_PREFIX_RE = re.compile(r"^[ \t]*frontmatter\s*:\s*\r?\n(?=[ \t]*---\s*\r?\n)")
_FM_BLOCK_RE = re.compile(r"^---\s*\r?\n(.*?)\r?\n---\s*(\r?\n|$)", re.DOTALL)
_WIKILINK_LIST_LINE_RE = re.compile(
    r"^(\s*[A-Za-z_][\w-]*\s*:\s*)(\[\[[^\]]+\]\](?:\s*,\s*\[\[[^\]]+\]\])+)\s*$"
)


def sanitize_ingested_content(content: str) -> str:
    """Applica le tre passate di sanitizzazione in ordine."""
    cleaned = _strip_outer_code_fence(content)
    cleaned = _strip_frontmatter_key_prefix(cleaned)
    cleaned = _repair_wikilink_lists_in_frontmatter(cleaned)
    return cleaned


def _strip_outer_code_fence(content: str) -> str:
    """Rimuove un fence ```yaml/md ``` che avvolge l'intero documento."""
    open_match = _OPEN_FENCE_RE.match(content)
    if not open_match:
        return content
    after_open = content[open_match.end():]
    close_match = _CLOSE_FENCE_RE.search(after_open)
    if not close_match:
        return content
    # close_match consuma anche il newline che precede il fence: ripristinalo
    return after_open[:close_match.start()] + "\n"


def _strip_frontmatter_key_prefix(content: str) -> str:
    """Rimuove una riga `frontmatter:` che precede il vero `---` block."""
    m = _FM_PREFIX_RE.match(content)
    if not m:
        return content
    return content[m.end():]


def _repair_wikilink_lists_in_frontmatter(content: str) -> str:
    """
    Dentro il blocco frontmatter, riscrive righe `key: [[a]], [[b]], [[c]]`
    in flow YAML valido `key: ["[[a]]", "[[b]]", "[[c]]"]`. Lascia il body intatto.
    """
    m = _FM_BLOCK_RE.match(content)
    if not m:
        return content

    fm_payload = m.group(1)
    repaired_lines = []
    for line in fm_payload.split("\n"):
        lm = _WIKILINK_LIST_LINE_RE.match(line)
        if not lm:
            repaired_lines.append(line)
            continue
        key_part = lm.group(1)
        items_raw = lm.group(2)
        items = [s.strip() for s in items_raw.split(",") if s.strip()]
        items_yaml = ", ".join(f'"{it}"' for it in items)
        repaired_lines.append(f"{key_part}[{items_yaml}]")

    repaired_payload = "\n".join(repaired_lines)
    # Sostituisci solo il payload, preserva i delimitatori `---\n` e la coda
    fm_start = m.start()
    fm_open_end = fm_start + len("---\n")  # primo `---\n`
    return (
        content[:fm_open_end]
        + repaired_payload
        + content[fm_open_end + len(fm_payload):]
    )
