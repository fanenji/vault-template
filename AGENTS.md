
## What this repo is

An **Obsidian vault**, not a software project — there is no build, test, lint, or typecheck step. The vault documents the Data Platform's architecture, technologies, decisions, and research, and is maintained collaboratively by a human curator and an LLM. It extends the open-source pattern at https://github.com/nashsu/llm_wiki.


## Before any wiki operation

Read `schema.md` first. It defines page types, frontmatter requirements, naming conventions, and the contradiction-handling workflow. Assumptions from other vaults do not apply.

## Directory invariants

| Path | Purpose | Rule |
|------|---------|------|
| `wiki/` | Main content (entities, concepts, sources, queries, comparisons, synthesis) | Active workspace |
| `raw/` | Original copies of ingested source files | **Read-only.** Never modify. |
| `_inbox/` | Staging for new files to ingest | Processed files are deleted after copying to `raw/` |
| `_notes/` | Output of graph analysis | Write-only location for `/graph-analyze` reports |
| `_system/templates/` | Obsidian note templates | Reference for page structure, do not move |
| `_system/scripts/` | Reusable Python scripts for wiki operations | Run from vault root (e.g. `python3 _system/scripts/graph-analyze.py`). See command files for context. |
| `.opencode/commands/` | OpenCode slash commands | Shared with `.claude/commands/` |

## OpenCode slash commands

| Command | Purpose |
|---------|---------|
| `/inbox-ingest` | Bulk ingest all files from `_inbox/` into wiki (copy → process → delete originals) |
| `/meeting-ingest <file>` | Transcribe and ingest meeting recordings/transcripts |
| `/url-ingest <URL>` | Fetch and ingest content from a URL |
| `/yt-ingest <URL>` | Download YouTube metadata/transcripts and ingest |
| `/transcript [<file>]` | Transcribe audio/video files from `_inbox/transcription/` with mlx_whisper |
| `/wiki-lint` | Full health check: missing wikilinks, orphans, frontmatter, source integrity, contradictions, glossary gaps, index counts |
| `/graph-analyze` | Directed graph analysis of wiki link structure → `_notes/` |

## Wiki content conventions

- Page files: `kebab-case.md`
- Source pages: `author-year-slug.md`
- Queries: question as slug (e.g., `does-scale-improve-reasoning.md`)
- All pages require YAML frontmatter: `type`, `title`, `tags`, `created`, `updated`
- Page `type` must match its subdirectory (`wiki/entities/` → `type: entity`, etc.)
- Cross-reference with `[[page-slug]]` syntax
- Every entity and concept must appear in `wiki/index.md`
- Source pages additionally require: `authors`, `year`, `url`, `venue`

## Contradiction workflow

When sources conflict: (1) note in relevant concept/entity page, (2) create/update a query page, (3) link both sources from query, (4) resolve in a synthesis page once evidence is sufficient.

## Fallback paths

The `.llm-wiki/` directory contains internal tooling state (LanceDB, ingest queues, conversation history). These are managed automatically; do not modify directly unless you understand the full toolchain.
