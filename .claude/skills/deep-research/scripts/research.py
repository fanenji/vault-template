#!/usr/bin/env python3
"""
research.py — orchestratore deep-research.

Pipeline (porting di src/lib/deep-research.ts):
  1. Multi-query: l'agente (NON questo script) genera N query da un topic.
  2. Per ogni query: web_search.py (Tavily → DDG fallback), dedup URL.
  3. (L'agente fetcha contenuto pagine se vuole arricchire — non gestito qui)
  4. L'agente sintetizza la risposta con cross-ref via QMD su wiki esistente.
  5. save_research: scrive il risultato in wiki/queries/research-<slug>-<date>.md
  6. (L'agente può poi chiamare wiki-ingest sul file salvato per auto-ingest)

Questo script offre comandi atomici; la coreografia è in SKILL.md.

Uso:
    # Search ricco: itera su più query, dedup risultati
    python research.py search-multi "query1" "query2" "query3" [--max-results 5]

    # Save: scrivi sintesi + references nella wiki
    python research.py save-result \\
        --topic "topic" \\
        --synthesis-file /tmp/synth.md \\
        --references-json /tmp/refs.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from web_search import search, find_vault_root, default_max_results


def slugify(text: str, max_len: int = 50) -> str:
    s = text.lower()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"\s+", "-", s.strip())
    return s[:max_len].rstrip("-") or "untitled"


def search_multi(queries: list[str], max_results: int | None = None) -> dict:
    """Esegui search per ogni query, dedup per URL, ritorna risultati unificati."""
    vault_root = find_vault_root(Path.cwd())
    if max_results is None:
        max_results = default_max_results(vault_root)
    all_results: list[dict] = []
    seen_urls: set[str] = set()
    provider_counts: dict[str, int] = {}

    for q in queries:
        try:
            results, provider = search(q, max_results, vault_root)
            provider_counts[provider] = provider_counts.get(provider, 0) + 1
            for r in results:
                url = r.get("url") or ""
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    r["query"] = q
                    all_results.append(r)
        except Exception as e:
            print(f"⚠ Query '{q}' failed: {e}", file=sys.stderr)

    return {
        "queries": queries,
        "providers_used": provider_counts,
        "total_results": len(all_results),
        "results": all_results,
    }


def save_result(
    topic: str,
    synthesis: str,
    references: list[dict],
    vault_root: Path,
) -> str:
    """
    Scrivi pagina di research in wiki/queries/. Ritorna path relativo.
    """
    today = date.today().isoformat()
    slug = slugify(topic)
    filename = f"research-{slug}-{today}.md"
    rel_path = f"wiki/queries/{filename}"
    full = vault_root / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)

    # Strip <think>/<thinking> blocks (come backend originale)
    cleaned = re.sub(r"<think(?:ing)?>[\s\S]*?</think(?:ing)?>", "", synthesis, flags=re.IGNORECASE)
    cleaned = re.sub(r"<think(?:ing)?>[\s\S]*$", "", cleaned, flags=re.IGNORECASE).strip()

    refs_lines = []
    for i, r in enumerate(references, 1):
        title = r.get("title", "Untitled")
        url = r.get("url", "")
        src = r.get("source", "")
        refs_lines.append(f"{i}. [{title}]({url}) — {src}" if src else f"{i}. [{title}]({url})")
    refs_md = "\n".join(refs_lines)

    page = "\n".join([
        "---",
        "type: query",
        f'title: "Research: {topic.replace(chr(34), chr(92) + chr(34))}"',
        f"created: {today}",
        f"updated: {today}",
        "origin: deep-research",
        "tags: [research]",
        "sources: []",
        "related: []",
        "---",
        "",
        f"# Research: {topic}",
        "",
        cleaned,
        "",
        "## References",
        "",
        refs_md,
        "",
    ])

    full.write_text(page, encoding="utf-8")
    return rel_path


def main() -> int:
    ap = argparse.ArgumentParser(description="Deep research orchestrator")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ap_sm = sub.add_parser("search-multi", help="Search su più query, dedup URLs")
    ap_sm.add_argument("queries", nargs="+")
    ap_sm.add_argument("--max-results", type=int, default=None,
                       help="Risultati per query (default: config.json o 5)")

    ap_save = sub.add_parser("save-result", help="Salva sintesi research in wiki/queries/")
    ap_save.add_argument("--topic", required=True)
    ap_save.add_argument("--synthesis-file", type=Path, required=True,
                         help="File con la sintesi LLM da salvare")
    ap_save.add_argument("--references-json", type=Path, required=True,
                         help="File JSON con array di {title, url, source}")

    args = ap.parse_args()

    if args.cmd == "search-multi":
        result = search_multi(args.queries, args.max_results)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if args.cmd == "save-result":
        vault_root = find_vault_root(Path.cwd())
        synthesis = args.synthesis_file.read_text(encoding="utf-8")
        references = json.loads(args.references_json.read_text(encoding="utf-8"))
        rel_path = save_result(args.topic, synthesis, references, vault_root)
        print(rel_path)
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
