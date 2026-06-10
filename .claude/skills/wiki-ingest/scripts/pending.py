#!/usr/bin/env python3
"""
pending.py — code persistenti per item che richiedono un secondo passaggio.

Due code, entrambe in `.llm-wiki/`:

  pending-merges.json   Pagine scritte da finalize.py con body nuovo ma il cui
                        body esistente differiva: serve il merge LLM (Step 6
                        della skill). Il body esistente è conservato QUI, non
                        sul disco — finché l'entry è pending, è l'unica copia.

  review/items.json     REVIEW blocks emessi dall'LLM in fase di generation
                        (contraddizioni, duplicati, suggerimenti) che
                        richiedono una decisione umana (vedi schema.md).

Uso:
    python pending.py merges list [--all]
    python pending.py merges resolve <id>
    python pending.py reviews list [--all]
    python pending.py reviews resolve <id> [--decision "..."]

`list` mostra solo gli item pending (--all per includere i resolved).
`resolve` marca l'item come gestito (non lo cancella: resta come storico).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path


def find_vault_root(start: Path) -> Path:
    cur = start.resolve()
    while True:
        if (cur / "wiki").is_dir() and (cur / ".llm-wiki").exists():
            return cur
        if cur.parent == cur:
            raise SystemExit(f"Non trovo una vault llm-wiki risalendo da {start}")
        cur = cur.parent


def _merges_path(vault_root: Path) -> Path:
    return vault_root / ".llm-wiki" / "pending-merges.json"


def _reviews_path(vault_root: Path) -> Path:
    return vault_root / ".llm-wiki" / "review" / "items.json"


def _load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _save(path: Path, items: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")


def _new_id(prefix: str) -> str:
    return f"{prefix}-{int(time.time())}-{uuid.uuid4().hex[:6]}"


# ── API usata da finalize.py ──────────────────────────────────────────────────

def add_merge(vault_root: Path, *, page: str, existing_body: str,
              incoming_body: str, source: str) -> str:
    """Accoda un merge pendente. Ritorna l'id assegnato."""
    items = _load(_merges_path(vault_root))
    # Se c'è già un pending per la stessa pagina, sostituiscilo (l'ultimo
    # finalize ha già scritto il body più recente su disco).
    items = [it for it in items if not (it.get("page") == page and it.get("status") == "pending")]
    entry = {
        "id": _new_id("merge"),
        "page": page,
        "existing_body": existing_body,
        "incoming_body": incoming_body,
        "source": source,
        "created_at": time.time(),
        "status": "pending",
    }
    items.append(entry)
    _save(_merges_path(vault_root), items)
    return entry["id"]


def add_review(vault_root: Path, *, review: dict, source: str) -> str:
    """Accoda un REVIEW block. `review` è il dict prodotto dal parser."""
    items = _load(_reviews_path(vault_root))
    entry = {
        "id": _new_id("review"),
        **review,
        "source": source,
        "created_at": time.time(),
        "status": "pending",
    }
    items.append(entry)
    _save(_reviews_path(vault_root), items)
    return entry["id"]


def resolve(path: Path, item_id: str, decision: str | None = None) -> bool:
    items = _load(path)
    for it in items:
        if it.get("id") == item_id:
            it["status"] = "resolved"
            it["resolved_at"] = time.time()
            if decision:
                it["decision"] = decision
            _save(path, items)
            return True
    return False


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="Code persistenti merge/review")
    sub = ap.add_subparsers(dest="queue", required=True)

    for name in ("merges", "reviews"):
        q = sub.add_parser(name)
        qsub = q.add_subparsers(dest="cmd", required=True)
        q_list = qsub.add_parser("list", help="Elenca item (pending di default)")
        q_list.add_argument("--all", action="store_true", help="Includi anche i resolved")
        q_res = qsub.add_parser("resolve", help="Marca un item come gestito")
        q_res.add_argument("item_id")
        if name == "reviews":
            q_res.add_argument("--decision", help="Decisione presa (es. 'Create Page')")

    args = ap.parse_args()
    vault_root = find_vault_root(Path.cwd())
    path = _merges_path(vault_root) if args.queue == "merges" else _reviews_path(vault_root)

    if args.cmd == "list":
        items = _load(path)
        if not args.all:
            items = [it for it in items if it.get("status") == "pending"]
        print(json.dumps(items, indent=2, ensure_ascii=False))
        return 0

    if args.cmd == "resolve":
        decision = getattr(args, "decision", None)
        ok = resolve(path, args.item_id, decision)
        print(f"{'✓ Resolved' if ok else '⚠ Not found'}: {args.item_id}", file=sys.stderr)
        return 0 if ok else 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
