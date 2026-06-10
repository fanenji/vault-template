#!/usr/bin/env python3
"""
web_search.py — web search con fallback chain: Tavily → DuckDuckGo.

Tavily è il default (qualità migliore, search depth advanced) ma richiede
API key e ha quota. Su quota-exceeded o key mancante, fallback automatico
a DuckDuckGo (gratis, rate-limited, qualità media).

Porting parziale di src/lib/web-search.ts (solo Tavily) + DDG come fallback.

Uso:
    python web_search.py "<query>" [--max-results 5] [--json]

Output (JSON, una entry per risultato):
    [{ "title": ..., "url": ..., "snippet": ..., "source": ... }, ...]

Config (in ordine di precedenza):
  1. env var TAVILY_API_KEY
  2. .llm-wiki/secrets.json → { "TAVILY_API_KEY": "..." }
  3. fallback DDG (se Tavily non disponibile)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse


def find_vault_root(start: Path) -> Path:
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


def default_max_results(vault_root: Path) -> int:
    return load_vault_config(vault_root).get("deep_research", {}).get("max_results_per_query", 5)


def load_tavily_key(vault_root: Path) -> str | None:
    key = os.environ.get("TAVILY_API_KEY", "").strip()
    if key:
        return key
    secrets = vault_root / ".llm-wiki" / "secrets.json"
    if secrets.exists():
        try:
            data = json.loads(secrets.read_text(encoding="utf-8"))
            key = (data.get("TAVILY_API_KEY") or "").strip()
            if key:
                return key
        except (OSError, json.JSONDecodeError):
            pass
    return None


def hostname_of(url: str) -> str:
    try:
        h = urlparse(url).hostname or ""
        return h.removeprefix("www.")
    except ValueError:
        return ""


# ── Tavily ────────────────────────────────────────────────────────────────────

class TavilyQuotaError(RuntimeError):
    """Tavily ha rifiutato la richiesta per quota/auth (innesca fallback)."""


def tavily_search(query: str, api_key: str, max_results: int = 5) -> list[dict]:
    """Porting di tavilySearch da src/lib/web-search.ts."""
    body = json.dumps({
        "api_key": api_key,
        "query": query,
        "max_results": max_results,
        "search_depth": "advanced",
        "include_answer": False,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.tavily.com/search",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        # 401/403/429 → quota/auth → fallback
        if e.code in (401, 403, 429):
            raise TavilyQuotaError(f"Tavily HTTP {e.code}: {e.reason}") from e
        raise
    except urllib.error.URLError as e:
        raise TavilyQuotaError(f"Tavily network error: {e.reason}") from e

    results = data.get("results", [])
    return [
        {
            "title": r.get("title", "Untitled"),
            "url": r.get("url", ""),
            "snippet": r.get("content", ""),
            "source": hostname_of(r.get("url", "")),
        }
        for r in results
    ]


# ── DuckDuckGo fallback ──────────────────────────────────────────────────────

def ddg_search(query: str, max_results: int = 5) -> list[dict]:
    """
    DuckDuckGo via libreria `duckduckgo_search`. Se non installata, prova
    `ddgs` (fork più recente). Se nessuna disponibile, errore esplicito.
    """
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        try:
            from ddgs import DDGS  # fork recente
        except ImportError:
            raise RuntimeError(
                "DuckDuckGo fallback richiede `duckduckgo-search` o `ddgs`. "
                "Installa con: pip install duckduckgo-search"
            )

    with DDGS() as d:
        raw = list(d.text(query, max_results=max_results))

    return [
        {
            "title": r.get("title") or r.get("heading") or "Untitled",
            "url": r.get("href") or r.get("url") or "",
            "snippet": r.get("body") or r.get("snippet") or "",
            "source": hostname_of(r.get("href") or r.get("url") or ""),
        }
        for r in raw
    ]


# ── Main ──────────────────────────────────────────────────────────────────────

def search(query: str, max_results: int = 5, vault_root: Path | None = None) -> tuple[list[dict], str]:
    """
    Esegue search. Ritorna (results, provider_used).
    Provider preferito: tavily; fallback: ddg.
    """
    vr = vault_root or find_vault_root(Path.cwd())
    tavily_key = load_tavily_key(vr)

    if tavily_key:
        try:
            return tavily_search(query, tavily_key, max_results), "tavily"
        except TavilyQuotaError as e:
            print(f"⚠ Tavily non disponibile ({e}) — fallback a DuckDuckGo", file=sys.stderr)

    return ddg_search(query, max_results), "duckduckgo"


def main() -> int:
    ap = argparse.ArgumentParser(description="Web search (Tavily → DDG fallback)")
    ap.add_argument("query", help="Search query")
    ap.add_argument("--max-results", type=int, default=None,
                    help="Risultati per query (default: config.json o 5)")
    ap.add_argument("--json", action="store_true", help="Output JSON (default)")
    ap.add_argument("--provider", choices=["auto", "tavily", "duckduckgo"], default="auto",
                    help="Forza un provider specifico")
    args = ap.parse_args()

    vault_root = find_vault_root(Path.cwd())
    if args.max_results is None:
        args.max_results = default_max_results(vault_root)

    if args.provider == "tavily":
        key = load_tavily_key(vault_root)
        if not key:
            print("Errore: TAVILY_API_KEY non configurata", file=sys.stderr)
            return 2
        results = tavily_search(args.query, key, args.max_results)
        used = "tavily"
    elif args.provider == "duckduckgo":
        results = ddg_search(args.query, args.max_results)
        used = "duckduckgo"
    else:
        results, used = search(args.query, args.max_results, vault_root)

    output = {"provider": used, "query": args.query, "results": results}
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
