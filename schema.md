# Schema

Regole strutturali della wiki. Le skill (ingest, lint) leggono questo file per decidere come classificare e validare le pagine.

## Tipi di pagina

Ogni pagina markdown in `wiki/` deve avere frontmatter YAML con il campo `type`:

| Type | Cartella | Cosa contiene |
|---|---|---|
| `entity` | `wiki/entities/` | Persone, organizzazioni, prodotti, luoghi — soggetti referenziabili |
| `concept` | `wiki/concepts/` | Teorie, metodi, tecniche, framework — oggetti astratti |
| `source` | `wiki/sources/` | Riassunto di un documento in `raw/sources/` |
| `query` | `wiki/queries/` | Risposta salvata da chat o deep-research |
| `synthesis` | `wiki/synthesis/` | Analisi trasversale fra più fonti / pagine |

## Frontmatter richiesto

Tutte le pagine:

```yaml
---
type: entity | concept | source | query | synthesis
title: "Titolo umano"
created: YYYY-MM-DD
updated: YYYY-MM-DD     # opzionale ma raccomandato
tags: []                # opzionale
---
```

Per `source`:

```yaml
source_path: "[[raw/sources/...]]" # wikilink al documento originale (quotato;
                                   # senza .md per i markdown, con estensione
                                   # per gli altri formati). Se la pagina deriva
                                   # da più documenti raw: lista inline di
                                   # wikilink, es.
                                   # source_path: ["[[raw/sources/a]]", "[[raw/sources/b]]"]
sources: ["https://..."]           # URL della pagina web originale, se il
                                   # documento sorgente la dichiara nel proprio
                                   # frontmatter (campo `source:`); altrimenti
                                   # il filename del documento
source_sha256: <hash>              # cache invalidation
```

Il formato di `source_path`/`sources` è normalizzato deterministicamente da
`finalize.py` a ogni ingest; per il pregresso esiste
`.claude/skills/wiki-ingest/scripts/fix_link_sources.py` (che sa anche derivare
un `source_path` mancante dai filename in `sources`, vedi il suo header).

Per `query`:

```yaml
origin: chat | deep-research
query: "domanda originale"
```

## Naming convention

- File: kebab-case, lowercase. Es. `anthropic.md`, `transformer-architecture.md`.
- Pagine sono **uniche per slug** — `entities/anthropic.md` e `concepts/anthropic.md` confliggono.
- Wikilink risolti case-insensitive: `[[Anthropic]]` matcha `anthropic.md`.

## Soppressione lint per-pagina

Una pagina può dichiarare nel frontmatter quali tipi di issue lint sono intenzionali e non vanno ri-segnalati (acknowledgment esplicito):

```yaml
lint_ignore: [orphan, no-outlinks]
```

Esempio tipico: le pagine `query` sono spesso orfane per natura. I tipi sopprimibili sono quelli riportati da `wiki-lint` (`orphan`, `no-outlinks`, `naming`, ...). Usalo con parsimonia: sopprimere `broken-link` o `duplicate-slug` nasconde problemi reali.

## Workflow contraddizioni

Quando l'ingest produce un'affermazione che contraddice una pagina esistente:

1. La skill **non sovrascrive** automaticamente.
2. Aggiunge l'affermazione contraddittoria alla coda di review in `.llm-wiki/review/`.
3. L'utente riceve un report al termine dell'ingest e decide cosa tenere.

## File auto-gestiti

Non modificare a mano (sono rigenerati dalle skill):

- `wiki/index.md` — catalogo automatico
- `wiki/log.md` — storico operazioni
- `wiki/overview.md` — sintesi globale aggiornata da ingest

## Personalizzazione

Puoi:
- Aggiungere nuovi tipi pagina (definisci qui type + cartella).
- Aggiungere campi frontmatter custom (le skill li preservano).
- Modificare le regole di naming (le skill leggono questo file ad ogni run).

Non puoi (senza modificare le skill):
- Cambiare la cartella `raw/sources/` (hardcoded nelle skill).
- Cambiare il prefix `wiki/` (hardcoded nei controlli di sicurezza path).
