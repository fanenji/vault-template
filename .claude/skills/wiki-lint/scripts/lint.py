#!/usr/bin/env python3
"""
wiki-lint — deterministic structural checks for an llm-wiki vault.

Porting di src/lib/lint.ts dal backend originale, esteso con:
  - frontmatter validation (presenza campi, formato date, type↔cartella)
  - duplicate-slug check (schema: gli slug sono unici cross-folder)
  - validazione riferimenti frontmatter (`related:`, `source_path`)
  - raw/sources non ingeriti
  - missing-page check via QMD vsearch (evita stub duplicati)
  - similar-pairs via QMD (coppie candidate per il check contraddizioni LLM)
  - check code pendenti (.llm-wiki/pending-merges.json, review/items.json)
  - storico run in .llm-wiki/lint/history/ + diff nuove/risolte
  - soppressione per-pagina via frontmatter `lint_ignore: [orphan, ...]`

Il check `semantic` (LLM-based) NON è qui: viene delegato all'agente che
invoca la skill. Vedi SKILL.md per i dettagli.

Uso:
    python lint.py [--vault PATH] [--json] [--no-qmd] [--similarity 0.9]
                   [--pages wiki/a.md wiki/b.md] [--no-history]
                   [--check all|structural|frontmatter|schema|missing-page|pending|similar-pairs]
                   [--report-file _notes/lint/lint-report.md]

Config (`.llm-wiki/config.json`, sezione `lint`):
    semantic_similarity_threshold  (default 0.85, per missing-page)
    pair_similarity_threshold      (default 0.90, per similar-pairs)
    pending_max_age_days           (default 7)

Output:
    Stampa report markdown su stdout (default) o JSON con --json.
    Exit code 0 se nessun warning, 1 altrimenti.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── Costanti ──────────────────────────────────────────────────────────────────

WIKILINK_RE = re.compile(r"\[\[([^\]|]+?)(?:\|[^\]]+?)?\]\]")
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
KEBAB_RE = re.compile(r"^[a-z0-9][a-z0-9-]*\.md$")

# Pagine auto-gestite: escluse dai check, ma i link verso di esse sono validi.
EXCLUDED_NAMES = {"index.md", "log.md", "overview.md"}
MANAGED_SLUGS = {"index", "log", "overview"}

# Required frontmatter fields per type — derivabile da schema.md ma
# replicato qui per non dover parsare schema.md ad ogni run.
REQUIRED_FIELDS_BY_TYPE = {
    "entity":    ["type", "title", "created"],
    "concept":   ["type", "title", "created"],
    "source":    ["type", "title", "created", "source_path"],
    "query":     ["type", "title", "created"],
    "synthesis": ["type", "title", "created"],
}

VALID_TYPES = set(REQUIRED_FIELDS_BY_TYPE.keys()) | {"index", "log", "overview"}

# Cartella attesa per type (schema.md)
FOLDER_BY_TYPE = {
    "entity": "entities",
    "concept": "concepts",
    "source": "sources",
    "query": "queries",
    "synthesis": "synthesis",
}

# Ordine di presentazione nel report
TYPE_ORDER = [
    "broken-link", "duplicate-slug", "frontmatter-ref", "missing-page",
    "frontmatter", "type-folder", "naming", "not-ingested", "pending",
    "orphan", "no-outlinks", "similar-pair", "semantic",
]


# ── Modelli ───────────────────────────────────────────────────────────────────

@dataclass
class LintResult:
    type: str             # vedi TYPE_ORDER
    severity: str         # warning | info
    page: str             # path relativo a wiki/, oppure titolo se "missing-page"
    detail: str
    affected_pages: list[str] = field(default_factory=list)
    suggestion: Optional[str] = None  # es. "ti riferivi a [[foo-bar]]?"
    status: Optional[str] = None      # new | persistent (valorizzato dal diff storico)


@dataclass
class PageData:
    path: Path            # absolute
    rel_path: str         # relative a wiki/
    slug: str             # rel_path senza .md
    content: str
    body: str             # senza frontmatter
    frontmatter: dict     # parsed YAML (best-effort)
    outlinks: list[str]   # raw wikilink targets


# ── Helpers ───────────────────────────────────────────────────────────────────

def parse_frontmatter(content: str) -> tuple[dict, str]:
    """
    Parser frontmatter best-effort senza dipendenze esterne.
    Ritorna (dict, body). Se non c'è frontmatter, dict vuoto e body = content.
    Gestisce solo scalari su una riga + flow sequences `[a, b, c]`.
    Per casi edge (multi-line, ancore) restituisce il valore raw come stringa.
    """
    m = FRONTMATTER_RE.match(content)
    if not m:
        return {}, content
    raw_fm = m.group(1)
    body = content[m.end():]

    fm: dict = {}
    for line in raw_fm.split("\n"):
        line = line.rstrip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        # rimuovi quote
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        # wikilink scalare (es. source_path: "[[raw/sources/foo]]"): è una
        # stringa, non va confuso con una flow list
        if value.startswith("[[") and value.endswith("]]"):
            fm[key] = value
        # flow list
        elif value.startswith("[") and value.endswith("]"):
            items = [v.strip().strip('"').strip("'") for v in value[1:-1].split(",") if v.strip()]
            fm[key] = items
        elif value == "":
            fm[key] = None
        elif value.lower() in ("true", "false"):
            fm[key] = value.lower() == "true"
        else:
            fm[key] = value
    return fm, body


def extract_wikilinks(content: str) -> list[str]:
    return [m.group(1).strip() for m in WIKILINK_RE.finditer(content)]


def flatten_md_files(wiki_root: Path) -> list[Path]:
    return [p for p in wiki_root.rglob("*.md") if p.name not in EXCLUDED_NAMES]


def build_slug_map(pages: list[PageData], wiki_root: Path) -> dict[str, Path]:
    """Map case-insensitive: slug → absolute path.

    Indicizza per:
      - rel_path senza .md (`entities/anthropic`)
      - basename senza .md (`anthropic`)

    Replica il pattern di lint.ts buildSlugMap. NB: i basename duplicati
    sovrascrivono (ultimo vince) — il check duplicate-slug li segnala.
    """
    m: dict[str, Path] = {}
    for p in pages:
        m[p.slug.lower()] = p.path
        m[p.path.stem.lower()] = p.path
    return m


def resolve_wikilink(link: str, slug_map: dict[str, Path]) -> Optional[Path]:
    """Risolvi un wikilink → path. Case-insensitive, prova full slug poi basename."""
    lookup = link.lower()
    if lookup in slug_map:
        return slug_map[lookup]
    basename = Path(link).stem.lower()
    return slug_map.get(basename)


def is_managed_link(link: str) -> bool:
    """Link a pagine auto-gestite (index/log/overview): validi, non contenuto."""
    return Path(link).stem.lower() in MANAGED_SLUGS


# ── Check strutturali ─────────────────────────────────────────────────────────

def check_structural(pages: list[PageData], slug_map: dict[str, Path], wiki_root: Path) -> list[LintResult]:
    """
    Check struttura: orphan, broken-link, no-outlinks.
    Porting di runStructuralLint da src/lib/lint.ts, con fix:
      - self-link non conta come inbound (non maschera orphan)
      - link a index/log/overview non sono broken (pagine auto-gestite)
    """
    results: list[LintResult] = []

    # Inbound count, case-insensitive. Self-link esclusi.
    inbound: dict[str, int] = {}
    for p in pages:
        for link in p.outlinks:
            if is_managed_link(link):
                continue
            resolved = resolve_wikilink(link, slug_map)
            if resolved == p.path:
                continue  # self-link
            target = resolved and str(resolved.relative_to(wiki_root)).removesuffix(".md").lower()
            target = target or link.lower()
            inbound[target] = inbound.get(target, 0) + 1

    for p in pages:
        # Orphan
        if inbound.get(p.slug.lower(), 0) == 0:
            results.append(LintResult(
                type="orphan",
                severity="info",
                page=p.rel_path,
                detail="No other pages link to this page.",
            ))

        # No outbound links
        if not p.outlinks:
            results.append(LintResult(
                type="no-outlinks",
                severity="info",
                page=p.rel_path,
                detail="This page has no [[wikilink]] references to other pages.",
            ))

        # Broken links
        for link in p.outlinks:
            if is_managed_link(link):
                continue
            if resolve_wikilink(link, slug_map) is None:
                results.append(LintResult(
                    type="broken-link",
                    severity="warning",
                    page=p.rel_path,
                    detail=f"Broken link: [[{link}]] — target page not found.",
                    affected_pages=[link],
                ))

    return results


def check_duplicate_slugs(pages: list[PageData]) -> list[LintResult]:
    """Slug (basename) unici cross-folder — regola di schema.md."""
    results: list[LintResult] = []
    by_stem: dict[str, list[PageData]] = {}
    for p in pages:
        by_stem.setdefault(p.path.stem.lower(), []).append(p)

    for stem, ps in sorted(by_stem.items()):
        if len(ps) < 2:
            continue
        paths = sorted(p.rel_path for p in ps)
        results.append(LintResult(
            type="duplicate-slug",
            severity="warning",
            page=paths[0],
            detail=f"Slug `{stem}` duplicato in: {', '.join(paths)} — "
                   f"i wikilink [[{stem}]] risolvono in modo ambiguo.",
            affected_pages=paths,
            suggestion="Rinomina una delle pagine o uniscile (gli slug devono essere unici, vedi schema.md).",
        ))
    return results


# ── Check frontmatter / schema ────────────────────────────────────────────────

def check_frontmatter(pages: list[PageData]) -> list[LintResult]:
    """Validate frontmatter contro REQUIRED_FIELDS_BY_TYPE + formato date."""
    results: list[LintResult] = []

    for p in pages:
        if not p.frontmatter:
            results.append(LintResult(
                type="frontmatter",
                severity="warning",
                page=p.rel_path,
                detail="Page has no YAML frontmatter.",
            ))
            continue

        page_type = p.frontmatter.get("type")
        if not page_type:
            results.append(LintResult(
                type="frontmatter",
                severity="warning",
                page=p.rel_path,
                detail="Missing required field: `type`.",
            ))
            continue

        if page_type not in VALID_TYPES:
            results.append(LintResult(
                type="frontmatter",
                severity="warning",
                page=p.rel_path,
                detail=f"Unknown type `{page_type}`. Valid: {sorted(VALID_TYPES)}",
            ))
            continue

        required = REQUIRED_FIELDS_BY_TYPE.get(page_type, [])
        missing = [f for f in required if not p.frontmatter.get(f)]
        if missing:
            results.append(LintResult(
                type="frontmatter",
                severity="warning",
                page=p.rel_path,
                detail=f"Missing required field(s): {', '.join(missing)}",
            ))

        # Formato date (solo se presenti)
        for date_field in ("created", "updated"):
            val = p.frontmatter.get(date_field)
            if val and isinstance(val, str) and not DATE_RE.match(val):
                results.append(LintResult(
                    type="frontmatter",
                    severity="info",
                    page=p.rel_path,
                    detail=f"Field `{date_field}` is not in YYYY-MM-DD format: `{val}`.",
                ))

    return results


def check_schema_rules(pages: list[PageData], slug_map: dict[str, Path],
                       vault_root: Path) -> list[LintResult]:
    """
    Regole di schema.md non coperte dagli altri check:
      - type ↔ cartella coerenti
      - naming kebab-case lowercase
      - `related:` deve contenere slug risolvibili
      - `source_path` deve esistere su disco (per type: source)
      - file in raw/sources/ senza pagina source → mai ingerito
    """
    results: list[LintResult] = []
    referenced_sources: set[str] = set()

    for p in pages:
        page_type = p.frontmatter.get("type")

        # type ↔ cartella
        expected_folder = FOLDER_BY_TYPE.get(page_type)
        top_folder = p.rel_path.split("/")[0] if "/" in p.rel_path else ""
        if expected_folder and top_folder and top_folder != expected_folder:
            results.append(LintResult(
                type="type-folder",
                severity="warning",
                page=p.rel_path,
                detail=f"Page has `type: {page_type}` but lives in `{top_folder}/` "
                       f"(expected `{expected_folder}/`).",
                suggestion=f"Sposta in wiki/{expected_folder}/ o correggi il type.",
            ))

        # naming kebab-case
        if not KEBAB_RE.match(p.path.name):
            results.append(LintResult(
                type="naming",
                severity="info",
                page=p.rel_path,
                detail="Filename is not lowercase kebab-case (see schema.md naming convention).",
            ))

        # related: slugs risolvibili
        related = p.frontmatter.get("related")
        if isinstance(related, list):
            for slug in related:
                s = str(slug).strip().strip("[]").strip()
                if not s or is_managed_link(s):
                    continue
                if resolve_wikilink(s, slug_map) is None:
                    results.append(LintResult(
                        type="frontmatter-ref",
                        severity="warning",
                        page=p.rel_path,
                        detail=f"`related:` references `{s}` but no such page exists.",
                        affected_pages=[s],
                    ))

        # source_path esistente — formato wikilink `[[raw/sources/foo]]`
        # (canonico, senza .md per i markdown) o path semplice (legacy)
        if page_type == "source":
            sp = p.frontmatter.get("source_path")
            if sp and isinstance(sp, str):
                target = sp.strip()
                if target.startswith("[[") and target.endswith("]]"):
                    target = target[2:-2].strip()
                resolved_src = next(
                    (c for c in (target, f"{target}.md")
                     if (vault_root / c).is_file()),
                    None,
                )
                if resolved_src:
                    referenced_sources.add(Path(resolved_src).name)
                else:
                    referenced_sources.add(Path(target).name)
                    results.append(LintResult(
                        type="frontmatter-ref",
                        severity="warning",
                        page=p.rel_path,
                        detail=f"`source_path: {sp}` does not exist on disk.",
                        suggestion="Il documento è stato spostato/rinominato? Aggiorna il path o re-ingerisci.",
                    ))

        # sources: array di filename (per il check not-ingested)
        sources = p.frontmatter.get("sources")
        if isinstance(sources, list):
            referenced_sources.update(Path(str(s)).name for s in sources if str(s).strip())

    # raw/sources/ senza pagina corrispondente
    raw_sources = vault_root / "raw" / "sources"
    if raw_sources.is_dir():
        for f in sorted(raw_sources.rglob("*")):
            if not f.is_file() or f.name.startswith(".") or f.name == ".gitkeep":
                continue
            if f.name not in referenced_sources:
                results.append(LintResult(
                    type="not-ingested",
                    severity="info",
                    page=str(f.relative_to(vault_root)),
                    detail="File in raw/sources/ non referenziato da nessuna pagina wiki.",
                    suggestion="Esegui wiki-ingest su questo file (o rimuovilo se non serve).",
                ))

    return results


# ── Check code pendenti ───────────────────────────────────────────────────────

def check_pending(vault_root: Path, max_age_days: float = 7) -> list[LintResult]:
    """
    Quality debt nelle code di .llm-wiki/: merge pendenti = contenuto della
    wiki che vive solo nella coda; review pendenti = decisioni mai prese.
    Warning se più vecchi di max_age_days, info altrimenti.
    """
    results: list[LintResult] = []
    now = time.time()
    queues = (
        (vault_root / ".llm-wiki" / "pending-merges.json", "pending merge", "page"),
        (vault_root / ".llm-wiki" / "review" / "items.json", "pending review", "title"),
    )

    for path, label, key in queues:
        if not path.exists():
            continue
        try:
            items = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(items, list):
            continue
        pending = [it for it in items if it.get("status") == "pending"]
        for it in pending:
            age_days = (now - it.get("created_at", now)) / 86400
            ident = it.get(key) or it.get("id", "?")
            if age_days > max_age_days:
                results.append(LintResult(
                    type="pending",
                    severity="warning",
                    page=str(ident),
                    detail=f"{label} `{it.get('id', '?')}` aperto da {age_days:.0f} giorni "
                           f"(soglia: {max_age_days:g}).",
                    suggestion="Risolvi con pending.py (wiki-ingest Step 6 per i merge).",
                ))
        if pending:
            results.append(LintResult(
                type="pending",
                severity="info",
                page=str(path.relative_to(vault_root)),
                detail=f"{len(pending)} {label}(s) in coda.",
            ))

    return results


# ── Check QMD-based ───────────────────────────────────────────────────────────

def _qmd_vsearch(query: str, vault_root: Path, n: int = 3) -> list[dict]:
    try:
        proc = subprocess.run(
            ["qmd", "vsearch", query, "--json", "-n", str(n)],
            cwd=str(vault_root),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if proc.returncode != 0:
            return []
        hits = json.loads(proc.stdout or "[]")
        return hits if isinstance(hits, list) else []
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return []


def check_missing_pages_via_qmd(
    broken_link_results: list[LintResult],
    vault_root: Path,
    similarity_threshold: float = 0.85,
) -> list[LintResult]:
    """
    Per ogni broken-link, chiede a QMD se esiste una pagina semanticamente
    simile. Se sì → suggerisce di correggere il wikilink. Se no → vero
    missing-page (candidato per stub).

    QMD 2.5.2 usa un indice project-local in `.qmd/` (discovery dal cwd): qui
    eseguiamo `qmd` con cwd=vault_root e nessun flag `--db` (obsoleto).
    """
    if not (vault_root / ".qmd").is_dir():
        return []

    results: list[LintResult] = []
    seen: set[str] = set()

    for r in broken_link_results:
        if r.type != "broken-link":
            continue
        link = r.affected_pages[0] if r.affected_pages else None
        if not link or link.lower() in seen:
            continue
        seen.add(link.lower())

        hits = _qmd_vsearch(link, vault_root, n=3)
        if hits:
            top = hits[0]
            score = top.get("score", 0)
            if score >= similarity_threshold:
                # Esiste già una pagina simile → suggerisci fix wikilink
                existing = top.get("path", "?")
                existing_slug = Path(existing).stem
                results.append(LintResult(
                    type="missing-page",
                    severity="info",
                    page=link,
                    detail=f"`[[{link}]]` doesn't exist but `{existing}` is semantically close (score={score:.2f}).",
                    suggestion=f"Fix wikilink to [[{existing_slug}]]",
                ))
                continue

        # Nessuna pagina vicina → vero candidato per stub
        results.append(LintResult(
            type="missing-page",
            severity="warning",
            page=link,
            detail=f"`[[{link}]]` is referenced but no page exists (and no semantically-close page found).",
            suggestion=f"Create stub page (entity or concept).",
        ))

    return results


def check_similar_pairs(
    pages: list[PageData],
    vault_root: Path,
    threshold: float = 0.90,
    max_pages: int = 200,
) -> list[LintResult]:
    """
    Trova coppie di pagine ad alta similarità semantica via QMD: sono le
    candidate per il check contraddizioni/duplicazione dell'agente (Step 2
    della skill), che le legge integralmente invece di campionare 500 char
    da tutta la wiki. Opt-in (--check similar-pairs): costa una vsearch per
    pagina.
    """
    if not (vault_root / ".qmd").is_dir():
        return []

    results: list[LintResult] = []
    seen_pairs: set[tuple[str, str]] = set()

    for p in pages[:max_pages]:
        title = p.frontmatter.get("title") or p.path.stem
        query = f"{title} {p.body.strip()[:200]}".strip()
        for hit in _qmd_vsearch(query, vault_root, n=4):
            score = hit.get("score", 0)
            if score < threshold:
                continue
            hp = hit.get("path", "")
            if hp.startswith("wiki/"):
                hp = hp[len("wiki/"):]
            if not hp or hp == p.rel_path or Path(hp).name in EXCLUDED_NAMES:
                continue
            pair = tuple(sorted((p.rel_path, hp)))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            results.append(LintResult(
                type="similar-pair",
                severity="info",
                page=pair[0],
                detail=f"`{pair[0]}` e `{pair[1]}` sono semanticamente molto simili (score={score:.2f}).",
                affected_pages=[pair[1]],
                suggestion="Leggi entrambe integralmente: contraddizioni? duplicazione da unire?",
            ))

    return results


# ── Soppressione, filtro incrementale, storico ────────────────────────────────

def apply_lint_ignore(results: list[LintResult], pages: list[PageData]) -> tuple[list[LintResult], int]:
    """
    Frontmatter `lint_ignore: [orphan, no-outlinks, ...]` su una pagina
    sopprime quei tipi di issue per quella pagina (acknowledgment esplicito,
    vedi schema.md). Ritorna (results filtrati, n soppressi).
    """
    ignore_by_page: dict[str, set[str]] = {}
    for p in pages:
        raw = p.frontmatter.get("lint_ignore")
        if isinstance(raw, list) and raw:
            ignore_by_page[p.rel_path] = {str(t).strip().lower() for t in raw}

    if not ignore_by_page:
        return results, 0

    kept: list[LintResult] = []
    suppressed = 0
    for r in results:
        if r.type.lower() in ignore_by_page.get(r.page, set()):
            suppressed += 1
        else:
            kept.append(r)
    return kept, suppressed


def filter_to_pages(results: list[LintResult], targets: list[str]) -> list[LintResult]:
    """
    Lint incrementale: tiene solo le issue che riguardano le pagine target
    (path rel a wiki/, accetta anche il prefisso `wiki/`) o che le citano
    in affected_pages.
    """
    norm = set()
    for t in targets:
        t = t.strip()
        if t.startswith("wiki/"):
            t = t[len("wiki/"):]
        norm.add(t.lower())

    def matches(r: LintResult) -> bool:
        # Match per path completo: lo stem non basta (slug duplicati in
        # cartelle diverse non devono attrarre le issue l'uno dell'altro).
        if r.page.lower() in norm:
            return True
        return any(a.lower() in norm for a in r.affected_pages)

    return [r for r in results if matches(r)]


def _fingerprint(r: LintResult) -> str:
    return f"{r.type}|{r.page}|{'|'.join(sorted(r.affected_pages))}"


def history_dir(vault_root: Path) -> Path:
    return vault_root / ".llm-wiki" / "lint" / "history"


def load_previous_run(vault_root: Path) -> Optional[dict]:
    d = history_dir(vault_root)
    if not d.is_dir():
        return None
    runs = sorted(d.glob("*.json"))
    if not runs:
        return None
    try:
        return json.loads(runs[-1].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def diff_results(results: list[LintResult], previous: Optional[dict]) -> dict:
    """
    Confronta col run precedente. Valorizza r.status (new|persistent) e
    ritorna {new: [...], resolved: [fingerprint, ...], previous_ts}.
    """
    if not previous:
        for r in results:
            r.status = "new"
        return {"new": results[:], "resolved": [], "previous_ts": None}

    prev_fps = {i["fingerprint"]: i for i in previous.get("issues", [])}
    cur_fps = set()
    new: list[LintResult] = []
    for r in results:
        fp = _fingerprint(r)
        cur_fps.add(fp)
        if fp in prev_fps:
            r.status = "persistent"
        else:
            r.status = "new"
            new.append(r)
    resolved = [i for fp, i in prev_fps.items() if fp not in cur_fps]
    return {"new": new, "resolved": resolved, "previous_ts": previous.get("timestamp")}


def save_run(vault_root: Path, results: list[LintResult], total_pages: int) -> None:
    d = history_dir(vault_root)
    d.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    payload = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "total_pages": total_pages,
        "warnings": sum(1 for r in results if r.severity == "warning"),
        "info": sum(1 for r in results if r.severity == "info"),
        "issues": [
            {"fingerprint": _fingerprint(r), **asdict(r)}
            for r in results
        ],
    }
    (d / f"{ts}.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    # Ritenzione: tieni gli ultimi 30 run
    runs = sorted(d.glob("*.json"))
    for old in runs[:-30]:
        old.unlink(missing_ok=True)


# ── I/O ───────────────────────────────────────────────────────────────────────

def load_pages(wiki_root: Path) -> list[PageData]:
    pages: list[PageData] = []
    for path in flatten_md_files(wiki_root):
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        fm, body = parse_frontmatter(content)
        rel = str(path.relative_to(wiki_root))
        slug = rel.removesuffix(".md")
        outlinks = extract_wikilinks(body)
        pages.append(PageData(
            path=path,
            rel_path=rel,
            slug=slug,
            content=content,
            body=body,
            frontmatter=fm,
            outlinks=outlinks,
        ))
    return pages


def render_markdown(
    results: list[LintResult],
    total_pages: int = 0,
    diff: Optional[dict] = None,
    suppressed: int = 0,
) -> str:
    """Report markdown: summary con diff, poi issue raggruppate per tipo."""
    out = ["# Wiki Lint Report", ""]
    out.append(f"_Run: {datetime.now().strftime('%Y-%m-%d %H:%M')}_")
    out.append("")

    warnings = sum(1 for r in results if r.severity == "warning")
    infos = sum(1 for r in results if r.severity == "info")
    pages_with_issues = len({r.page for r in results})

    out.append("## Summary")
    out.append("")
    out.append(f"- Pagine analizzate: **{total_pages}** ({pages_with_issues} con issue)")
    out.append(f"- ⚠ Warning: **{warnings}** — ℹ Info: **{infos}**"
               + (f" — 🔕 Soppresse via `lint_ignore`: {suppressed}" if suppressed else ""))
    if diff:
        prev = diff.get("previous_ts")
        new_n = len(diff.get("new", []))
        res_n = len(diff.get("resolved", []))
        if prev:
            out.append(f"- Rispetto al run precedente ({prev}): "
                       f"**{new_n} nuove**, **{res_n} risolte**")
        else:
            out.append("- Primo run con storico: tutte le issue sono marcate nuove.")
    out.append("")

    if diff and diff.get("new") and diff.get("previous_ts"):
        out.append(f"## 🆕 Nuove dal run precedente ({len(diff['new'])})")
        out.append("")
        for r in diff["new"]:
            sev = "⚠" if r.severity == "warning" else "ℹ"
            out.append(f"- {sev} `{r.type}` **{r.page}** — {r.detail}")
        out.append("")

    if diff and diff.get("resolved"):
        out.append(f"## ✅ Risolte ({len(diff['resolved'])})")
        out.append("")
        for i in diff["resolved"]:
            out.append(f"- `{i.get('type')}` **{i.get('page')}** — {i.get('detail')}")
        out.append("")

    if not results:
        out.append("✓ No issues found.")
        out.append("")
        return "\n".join(out)

    by_type: dict[str, list[LintResult]] = {}
    for r in results:
        by_type.setdefault(r.type, []).append(r)

    out.append("## Tutte le issue")
    out.append("")
    for tname in TYPE_ORDER + sorted(set(by_type) - set(TYPE_ORDER)):
        items = by_type.get(tname, [])
        if not items:
            continue
        out.append(f"### {tname} ({len(items)})")
        out.append("")
        for r in items:
            sev = "⚠" if r.severity == "warning" else "ℹ"
            badge = " 🆕" if r.status == "new" else ""
            out.append(f"- {sev}{badge} **{r.page}** — {r.detail}")
            if r.suggestion:
                out.append(f"  - _Suggestion:_ {r.suggestion}")
        out.append("")

    return "\n".join(out)


def render_json(results: list[LintResult]) -> str:
    return json.dumps([asdict(r) for r in results], indent=2, ensure_ascii=False)


def build_summary(results: list[LintResult], total_pages: int,
                  diff: Optional[dict]) -> dict:
    """Summary compatto del run (una riga JSON su stdout con --report-file)."""
    summary = {
        "total_pages": total_pages,
        "warnings": sum(1 for r in results if r.severity == "warning"),
        "info": sum(1 for r in results if r.severity == "info"),
        "new": None,
        "new_warnings": None,
        "resolved": None,
    }
    if diff and diff.get("previous_ts"):
        new = diff.get("new", [])
        summary["new"] = len(new)
        summary["new_warnings"] = sum(1 for r in new if r.severity == "warning")
        summary["resolved"] = len(diff.get("resolved", []))
    return summary


# ── Main ──────────────────────────────────────────────────────────────────────

def find_vault_root(start: Path) -> Path:
    """Risale dall'attuale dir cercando una vault valida (wiki/ + .llm-wiki/)."""
    cur = start.resolve()
    while True:
        if (cur / "wiki").is_dir() and (cur / ".llm-wiki").exists():
            return cur
        if cur.parent == cur:
            raise SystemExit(f"Non trovo una vault llm-wiki risalendo da {start}")
        cur = cur.parent


def load_vault_config(vault_root: Path) -> dict:
    """Legge `.llm-wiki/config.json` (best-effort, {} se assente/corrotto)."""
    p = vault_root / ".llm-wiki" / "config.json"
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def main() -> int:
    ap = argparse.ArgumentParser(description="Deterministic structural lint for an llm-wiki vault.")
    ap.add_argument("--vault", type=Path, default=None, help="Vault root (default: auto-detect)")
    ap.add_argument("--json", action="store_true", help="Output JSON invece di markdown")
    ap.add_argument("--no-qmd", action="store_true", help="Salta i check via QMD (missing-page, similar-pairs)")
    ap.add_argument("--similarity", type=float, default=None,
                    help="Threshold per missing-page (default: config.json o 0.85)")
    ap.add_argument("--report-file", type=Path, default=None,
                    help="Scrivi il report su file invece di stdout (es. _notes/lint/lint-report.md)")
    ap.add_argument("--check",
                    choices=["all", "structural", "frontmatter", "schema",
                             "missing-page", "pending", "similar-pairs"],
                    default="all",
                    help="Esegui solo un subset di check (similar-pairs NON è incluso in `all`: opt-in)")
    ap.add_argument("--pages", nargs="+", default=None, metavar="PAGE",
                    help="Lint incrementale: riporta solo le issue che riguardano queste pagine "
                         "(path rel a wiki/). Disabilita lo storico.")
    ap.add_argument("--no-history", action="store_true",
                    help="Non salvare il run in .llm-wiki/lint/history/ e non calcolare il diff")
    args = ap.parse_args()

    vault_root = args.vault.resolve() if args.vault else find_vault_root(Path.cwd())
    wiki_root = vault_root / "wiki"

    if not wiki_root.is_dir():
        print(f"Errore: {wiki_root} non esiste", file=sys.stderr)
        return 2

    config = load_vault_config(vault_root).get("lint", {})
    similarity = args.similarity if args.similarity is not None else \
        config.get("semantic_similarity_threshold", 0.85)
    pair_threshold = config.get("pair_similarity_threshold", 0.90)
    pending_max_age = config.get("pending_max_age_days", 7)

    pages = load_pages(wiki_root)
    slug_map = build_slug_map(pages, wiki_root)

    results: list[LintResult] = []

    if args.check in ("all", "structural"):
        results.extend(check_structural(pages, slug_map, wiki_root))
        results.extend(check_duplicate_slugs(pages))

    if args.check in ("all", "frontmatter"):
        results.extend(check_frontmatter(pages))

    if args.check in ("all", "schema"):
        results.extend(check_schema_rules(pages, slug_map, vault_root))

    if args.check in ("all", "pending"):
        results.extend(check_pending(vault_root, pending_max_age))

    if args.check in ("all", "missing-page") and not args.no_qmd:
        broken = [r for r in results if r.type == "broken-link"]
        if args.check == "missing-page" and not broken:
            broken = check_structural(pages, slug_map, wiki_root)
        results.extend(check_missing_pages_via_qmd(
            [r for r in broken if r.type == "broken-link"], vault_root, similarity))

    if args.check == "similar-pairs" and not args.no_qmd:
        results.extend(check_similar_pairs(pages, vault_root, pair_threshold))

    # Soppressione esplicita via frontmatter lint_ignore
    results, suppressed = apply_lint_ignore(results, pages)

    # Lint incrementale: filtra alle pagine target, niente storico
    incremental = bool(args.pages)
    if incremental:
        results = filter_to_pages(results, args.pages)

    # Storico + diff (solo per run completi)
    diff: Optional[dict] = None
    if args.check == "all" and not incremental and not args.no_history:
        diff = diff_results(results, load_previous_run(vault_root))
        save_run(vault_root, results, len(pages))

    # Output
    if args.json:
        out = render_json(results)
    else:
        out = render_markdown(results, total_pages=len(pages), diff=diff, suppressed=suppressed)

    if args.report_file:
        args.report_file.parent.mkdir(parents=True, exist_ok=True)
        args.report_file.write_text(out, encoding="utf-8")
        print(f"✓ Report scritto in {args.report_file}", file=sys.stderr)
        # Summary machine-readable su stdout: consumato dal plugin Obsidian
        # (lint schedulato) per la Notice e per decidere l'escalation LLM.
        print(json.dumps(build_summary(results, len(pages), diff), ensure_ascii=False))
    else:
        print(out)

    warnings = sum(1 for r in results if r.severity == "warning")
    return 1 if warnings > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
