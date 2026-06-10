# .llm-wiki/

Stato interno delle skill llm-wiki. Tutto qui dentro è **rigenerabile o ricostruibile** dalle skill stesse e ignorato da git (vedi `.gitignore` della vault root) — con un'eccezione: i body in `pending-merges.json` sono l'unica copia del contenuto pre-merge finché l'entry è pending.

L'indice di ricerca QMD **non** vive qui: è project-local in `.qmd/` alla vault root (qmd 2.5.2, rigenerabile con `qmd update && qmd embed`).

## Contenuto

| Path | Cosa contiene |
|---|---|
| `queue/items.json` | Coda persistente dell'ingest (pending / running / done / failed) |
| `ingest-cache.json` | Cache SHA256 per file sorgente: skip su file invariati |
| `pending-merges.json` | Pagine in attesa di body merge LLM (Step 6 di wiki-ingest). Contiene il body esistente pre-overwrite |
| `review/items.json` | REVIEW blocks emessi dall'ingest che richiedono decisione umana |
| `config.json` | Config locale della vault (override del template) |
| `secrets.json` | Chiavi API (Tavily, ecc.) — **mai committare** |

Le code `pending-merges.json` e `review/items.json` si gestiscono con:

```bash
python .claude/skills/wiki-ingest/scripts/pending.py merges list
python .claude/skills/wiki-ingest/scripts/pending.py merges resolve <id>
python .claude/skills/wiki-ingest/scripts/pending.py reviews list
python .claude/skills/wiki-ingest/scripts/pending.py reviews resolve <id> --decision "..."
```

## Configurazione

Copia `config.example.json` in `config.json` e modifica i valori. Chiavi effettivamente lette dagli script:

| Chiave | Letta da | Default |
|---|---|---|
| `ingest.max_chars` | `preprocess.py` (cap caratteri per documento) | 50000 |
| `deep_research.max_queries` | agente (Step 1 di deep-research) | 3 |
| `deep_research.max_results_per_query` | `web_search.py`, `research.py` | 5 |
| `lint.semantic_similarity_threshold` | `lint.py` (check missing-page) | 0.85 |

I flag CLI hanno sempre precedenza sul config. Per i secrets la cascata è: variabili ambiente (es. `TAVILY_API_KEY`) → `.llm-wiki/secrets.json`.

## Reset

Per resettare completamente lo stato (mantenendo `wiki/` e `raw/`):

```bash
rm -rf .llm-wiki/queue .llm-wiki/ingest-cache.json .llm-wiki/pending-merges.json .llm-wiki/review
rm -rf .qmd && qmd init && qmd collection add ./wiki && qmd update && qmd embed
```

⚠ Prima di cancellare `pending-merges.json`, verifica che non ci siano merge pending: i body esistenti pre-merge vivono solo lì.
