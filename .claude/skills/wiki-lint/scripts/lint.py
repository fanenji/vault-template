#!/usr/bin/env python3
"""
wiki-lint — deterministic structural checks for an llm-wiki vault.

Porting fedele di src/lib/lint.ts dal backend originale, esteso con:
  - frontmatter validation (basato su schema.md / config)
  - missing-page check via QMD vsearch (evita stub duplicati)

Il check `semantic` (LLM-based) NON è qui: viene delegato all'agente che
invoca la skill. Vedi SKILL.md per i dettagli.

Uso:
    python lint.py [--vault PATH] [--json] [--fix-frontmatter] [--no-qmd]

Output:
    Stampa report markdown su stdout (default) o JSON con --json.
    Exit code 0 se nessun warning, 1 altrimenti.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

# ── Costanti ──────────────────────────────────────────────────────────────────

WIKILINK_RE = re.compile(r"\[\[([^\]|]+?)(?:\|[^\]]+?)?\]\]")
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

# Pagine escluse dai check (auto-gestite)
EXCLUDED_NAMES = {"index.md", "log.md"}

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


# ── Modelli ───────────────────────────────────────────────────────────────────

@dataclass
class LintResult:
    type: str             # orphan, broken-link, no-outlinks, frontmatter, missing-page
    severity: str         # warning | info
    page: str             # path relativo a wiki/, oppure titolo se "missing-page"
    detail: str
    affected_pages: list[str] = field(default_factory=list)
    suggestion: Optional[str] = None  # es. "ti riferivi a [[foo-bar]]?"


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
        # flow list
        if value.startswith("[") and value.endswith("]"):
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

    Replica il pattern di lint.ts buildSlugMap.
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


# ── Check ─────────────────────────────────────────────────────────────────────

def check_structural(pages: list[PageData], slug_map: dict[str, Path], wiki_root: Path) -> list[LintResult]:
    """
    Check struttura: orphan, broken-link, no-outlinks.
    Porting fedele di runStructuralLint da src/lib/lint.ts.
    """
    results: list[LintResult] = []

    # Inbound count, case-insensitive
    inbound: dict[str, int] = {}
    for p in pages:
        for link in p.outlinks:
            resolved = resolve_wikilink(link, slug_map)
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
            if resolve_wikilink(link, slug_map) is None:
                results.append(LintResult(
                    type="broken-link",
                    severity="warning",
                    page=p.rel_path,
                    detail=f"Broken link: [[{link}]] — target page not found.",
                    affected_pages=[link],
                ))

    return results


def check_frontmatter(pages: list[PageData]) -> list[LintResult]:
    """Validate frontmatter contro REQUIRED_FIELDS_BY_TYPE."""
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

    return results


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

        try:
            proc = subprocess.run(
                ["qmd", "vsearch", link, "--json", "-n", "3"],
                cwd=str(vault_root),
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if proc.returncode != 0:
                continue
            hits = json.loads(proc.stdout or "[]")
        except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
            continue

        if hits and isinstance(hits, list):
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


def render_markdown(results: list[LintResult], wiki_root: Path) -> str:
    """Report markdown raggruppato per tipo."""
    if not results:
        return "# Wiki Lint Report\n\n✓ No issues found.\n"

    by_type: dict[str, list[LintResult]] = {}
    for r in results:
        by_type.setdefault(r.type, []).append(r)

    out = ["# Wiki Lint Report", ""]
    out.append(f"_{len(results)} issue(s) found across {len(by_type)} category(ies)._")
    out.append("")

    for tname in ["broken-link", "missing-page", "frontmatter", "orphan", "no-outlinks", "semantic"]:
        items = by_type.get(tname, [])
        if not items:
            continue
        out.append(f"## {tname} ({len(items)})")
        out.append("")
        for r in items:
            sev = "⚠" if r.severity == "warning" else "ℹ"
            out.append(f"- {sev} **{r.page}** — {r.detail}")
            if r.suggestion:
                out.append(f"  - _Suggestion:_ {r.suggestion}")
        out.append("")

    return "\n".join(out)


def render_json(results: list[LintResult]) -> str:
    return json.dumps([asdict(r) for r in results], indent=2, ensure_ascii=False)


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


def main() -> int:
    ap = argparse.ArgumentParser(description="Deterministic structural lint for an llm-wiki vault.")
    ap.add_argument("--vault", type=Path, default=None, help="Vault root (default: auto-detect)")
    ap.add_argument("--json", action="store_true", help="Output JSON invece di markdown")
    ap.add_argument("--no-qmd", action="store_true", help="Salta il check missing-page via QMD")
    ap.add_argument("--similarity", type=float, default=0.85, help="Threshold per missing-page (default 0.85)")
    ap.add_argument("--report-file", type=Path, default=None, help="Scrivi il report su file invece di stdout")
    ap.add_argument("--check", choices=["all", "structural", "frontmatter", "missing-page"], default="all",
                    help="Esegui solo un subset di check")
    args = ap.parse_args()

    vault_root = args.vault.resolve() if args.vault else find_vault_root(Path.cwd())
    wiki_root = vault_root / "wiki"

    if not wiki_root.is_dir():
        print(f"Errore: {wiki_root} non esiste", file=sys.stderr)
        return 2

    pages = load_pages(wiki_root)
    slug_map = build_slug_map(pages, wiki_root)

    results: list[LintResult] = []

    if args.check in ("all", "structural"):
        results.extend(check_structural(pages, slug_map, wiki_root))

    if args.check in ("all", "frontmatter"):
        results.extend(check_frontmatter(pages))

    if args.check in ("all", "missing-page") and not args.no_qmd:
        broken = [r for r in results if r.type == "broken-link"]
        results.extend(check_missing_pages_via_qmd(broken, vault_root, args.similarity))

    # Output
    if args.json:
        out = render_json(results)
    else:
        out = render_markdown(results, wiki_root)

    if args.report_file:
        args.report_file.write_text(out, encoding="utf-8")
        print(f"✓ Report scritto in {args.report_file}", file=sys.stderr)
    else:
        print(out)

    warnings = sum(1 for r in results if r.severity == "warning")
    return 1 if warnings > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
