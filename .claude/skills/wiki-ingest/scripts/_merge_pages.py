"""
_merge_pages.py — merge soft di una pagina esistente con una nuova generata.

Porting parziale di src/lib/page-merge.ts. Replica:
  - Array fields union (sources, tags, related) — sempre
  - Locked fields (type, title, created) — sempre preservati dall'esistente
  - Updated stamp = oggi

Il merge LLM-based del body (terzo layer del backend originale) è DELEGATO
all'agente: questo modulo emette un flag `merge_body_needed` quando i bodies
differiscono. L'agente legge il flag, esegue il merge nel suo contesto LLM,
e ri-invoca lo script con il body risultante.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

UNION_FIELDS = ("sources", "tags", "related")
LOCKED_FIELDS = ("type", "title", "created")
MANAGED_FIELDS = UNION_FIELDS + LOCKED_FIELDS + ("updated",)
BODY_SHRINK_THRESHOLD = 0.7  # come backend originale

_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
# Top-level key YAML a colonna 0 (inizio di un nuovo segmento di frontmatter)
_TOP_KEY_RE = re.compile(r"^([A-Za-z_][\w.-]*)\s*:")


@dataclass
class MergeOutcome:
    """Esito del merge."""
    content: str                       # Contenuto finale (potrebbe necessitare LLM body merge)
    merge_body_needed: bool            # True se i bodies differiscono e serve LLM merge
    existing_body: str = ""            # Body esistente (se merge_body_needed)
    incoming_body: str = ""            # Body incoming (array-merged, se merge_body_needed)
    fallback_used: bool = False        # True se il merge è stato un fallback semplice


def fm_payload(content: str) -> tuple[str | None, str]:
    """Estrae il payload grezzo del frontmatter (testo fra i `---`) e il body."""
    m = _FM_RE.match(content)
    if not m:
        return None, content
    return m.group(1), content[m.end():]


def _split_fm_segments(payload: str) -> list[tuple[str | None, list[str]]]:
    """
    Spezza il payload frontmatter in segmenti top-level: (key, righe).

    Un segmento inizia a ogni `key:` a colonna 0; righe indentate, item di
    block sequence (`- ...`) e commenti/righe vuote si attaccano al segmento
    corrente. Righe orfane prima della prima key → segmento con key=None.
    Serve a manipolare singoli campi preservando il resto byte-per-byte
    (incluse strutture nested che il parser semplificato non capisce).
    """
    segments: list[tuple[str | None, list[str]]] = []
    cur_key: str | None = None
    cur_lines: list[str] = []
    started = False

    for line in payload.split("\n"):
        m = _TOP_KEY_RE.match(line)
        if m:
            if started:
                segments.append((cur_key, cur_lines))
            cur_key, cur_lines, started = m.group(1), [line], True
        else:
            if not started:
                started = True  # righe orfane iniziali (commenti, ecc.)
            cur_lines.append(line)
    if started:
        segments.append((cur_key, cur_lines))
    return segments


def _render_field(key: str, value) -> str:
    """Renderizza un singolo campo gestito in YAML flow style."""
    if value is None:
        return f"{key}:"
    if isinstance(value, list):
        items = ", ".join(
            f'"{x}"' if isinstance(x, str) and (":" in x or "[" in x) else str(x)
            for x in value
        )
        return f"{key}: [{items}]"
    if isinstance(value, bool):
        return f"{key}: {str(value).lower()}"
    if isinstance(value, str) and ":" in value:
        return f'{key}: "{value}"'
    return f"{key}: {value}"


def render_merged_frontmatter(
    primary_payload: str | None,
    secondary_payload: str | None,
    managed: dict,
) -> str:
    """
    Costruisce il payload frontmatter del merge:
      - campi NON gestiti del primary (pagina nuova / output LLM): verbatim
      - campi NON gestiti presenti SOLO nel secondary (pagina esistente):
        verbatim in coda (i campi custom non si perdono mai)
      - campi gestiti (union/locked/updated): renderizzati da `managed`

    Lavorare sulle righe grezze preserva valori nested/multi-riga che il
    parser semplificato non sa fare roundtrip.
    """
    managed_keys = set(managed)
    out_lines: list[str] = []
    primary_keys: set[str] = set()

    for key, lines in _split_fm_segments(primary_payload or ""):
        if key is not None:
            primary_keys.add(key)
        if key in managed_keys:
            continue
        out_lines.extend(lines)

    for key, lines in _split_fm_segments(secondary_payload or ""):
        if key is None or key in managed_keys or key in primary_keys:
            continue
        out_lines.extend(lines)

    # Rimuovi righe vuote in coda ai segmenti preservati
    while out_lines and not out_lines[-1].strip():
        out_lines.pop()

    for key in MANAGED_FIELDS:
        if key in managed:
            out_lines.append(_render_field(key, managed[key]))

    return "\n".join(out_lines)


def _managed_values(old_fm: dict, new_fm: dict, today_str: str,
                    extra_unions: dict | None = None) -> dict:
    """Calcola i valori dei campi gestiti: locked dall'esistente, array union, updated."""
    managed: dict = {}
    for f in UNION_FIELDS:
        base = merge_array_field(old_fm.get(f), new_fm.get(f))
        if extra_unions and f in extra_unions:
            base = merge_array_field(base, extra_unions.get(f))
        managed[f] = base
    for f in LOCKED_FIELDS:
        val = old_fm.get(f) if old_fm.get(f) else new_fm.get(f)
        if val is not None:
            managed[f] = val
    managed["updated"] = today_str
    return managed


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """
    Parse frontmatter best-effort. Ritorna (dict, body).
    Gestisce scalari, flow list `[a, b]` e block list (`key:` seguito da
    righe `- item`). Strutture nested più complesse restano fuori dal dict
    (ma sopravvivono comunque al merge via render_merged_frontmatter).
    """
    m = _FM_RE.match(content)
    if not m:
        return {}, content
    raw = m.group(1)
    body = content[m.end():]

    fm: dict = {}
    lines = raw.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        i += 1
        if not line or line.lstrip().startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        if value.startswith("[") and value.endswith("]"):
            items = [v.strip().strip('"').strip("'") for v in value[1:-1].split(",") if v.strip()]
            fm[key] = items
        elif value == "":
            # Possibile block list: righe successive `- item`
            items = []
            j = i
            while j < len(lines):
                im = re.match(r"^\s*-\s+(.*?)\s*$", lines[j])
                if not im:
                    break
                items.append(im.group(1).strip().strip('"').strip("'"))
                j += 1
            if items:
                fm[key] = items
                i = j
            else:
                fm[key] = None
        else:
            fm[key] = value
    return fm, body


def merge_array_field(existing: list | None, incoming: list | None) -> list:
    """Union deterministico, mantiene ordine: prima existing, poi incoming nuovi."""
    seen: set[str] = set()
    out: list = []
    for v in (existing or []) + (incoming or []):
        key = str(v).strip()
        if key and key not in seen:
            seen.add(key)
            out.append(v)
    return out


def merge_pages(
    new_content: str,
    existing_content: str | None,
    source_filename: str = "",
    today: str | None = None,
) -> MergeOutcome:
    """
    Merge soft. Casistica:
      1. existing == None → ritorna new_content as-is.
      2. byte-identical → ritorna existing.
      3. solo array fields differiscono → array union, ritorna risultato.
      4. bodies differiscono → ritorna stato che richiede LLM merge.
    """
    if existing_content is None:
        return MergeOutcome(content=new_content, merge_body_needed=False)

    if new_content == existing_content:
        return MergeOutcome(content=existing_content, merge_body_needed=False)

    today_str = today or date.today().isoformat()

    old_fm, old_body = parse_frontmatter(existing_content)
    new_fm, new_body = parse_frontmatter(new_content)
    old_payload, _ = fm_payload(existing_content)
    new_payload, _ = fm_payload(new_content)

    managed = _managed_values(old_fm, new_fm, today_str)
    merged_payload = render_merged_frontmatter(new_payload, old_payload, managed)
    merged = _wrap(merged_payload, new_body)

    # Body merge: se i bodies sono uguali (modulo whitespace), no LLM needed
    if old_body.strip() == new_body.strip():
        return MergeOutcome(content=merged, merge_body_needed=False)

    # Bodies differiscono → segnala bisogno LLM merge
    return MergeOutcome(
        content=merged,  # fallback: usa new body con fm merged
        merge_body_needed=True,
        existing_body=old_body,
        incoming_body=new_body,
        fallback_used=True,
    )


def apply_llm_merge_result(
    llm_output: str,
    existing_content: str,
    incoming_content: str,
    today: str | None = None,
) -> str:
    """
    Applica deterministicamente le regole post-LLM:
      - Sanity check body length (≥70% del max)
      - Lock back type/title/created
      - Re-union sources/tags/related
      - Updated = oggi

    Se sanity check fallisce, ritorna fallback (incoming + array union).
    """
    today_str = today or date.today().isoformat()

    old_fm, old_body = parse_frontmatter(existing_content)
    new_fm, new_body = parse_frontmatter(incoming_content)
    old_payload, _ = fm_payload(existing_content)
    new_payload, _ = fm_payload(incoming_content)

    llm_fm, llm_body = parse_frontmatter(llm_output)
    llm_payload, _ = fm_payload(llm_output)

    def _fallback() -> str:
        managed = _managed_values(old_fm, new_fm, today_str)
        payload = render_merged_frontmatter(new_payload, old_payload, managed)
        return _wrap(payload, new_body)

    if not llm_fm:
        # Output LLM senza frontmatter → reject, fallback
        return _fallback()

    # Sanity check body length
    threshold = max(len(old_body), len(new_body)) * BODY_SHRINK_THRESHOLD
    if len(llm_body) < threshold:
        # LLM ha probabilmente troncato. Fallback.
        return _fallback()

    # OK: apply post-processing all'output LLM (union include anche i valori LLM)
    managed = _managed_values(old_fm, new_fm, today_str,
                              extra_unions={f: llm_fm.get(f) for f in UNION_FIELDS})
    payload = render_merged_frontmatter(llm_payload, old_payload, managed)
    return _wrap(payload, llm_body)


def _wrap(fm_payload_text: str, body: str) -> str:
    """Avvolge payload frontmatter + body in markdown standard."""
    return "---\n" + fm_payload_text + "\n---\n" + body.lstrip("\n")
