# Data Platform LLM Wiki

Obsidian vault documenting the Data Platform architecture, technologies, decisions, and research. Managed via LLM-based tooling.

See `schema.md` for page types, frontmatter requirements, naming conventions, and the contradiction workflow.

The wiki is based on this OpenSource project: https://github.com/nashsu/llm_wiki and extends it with custom dirs and commands.

The /raw/ and /wiki/ folders and purpose.md and schema.md files pertain to the llm-wiki system and are managed by the system.

The \_inbox,\_notes and \_system older are personal folders managed with Obsidian and Claude/OpenCode agents.


---
## Commands

These slash commands are available in both `.claude/commands/` and `.opencode/commands/`.

### `/wiki-lint [--fix] [--report-only] [--section <name>]`

Full health check on the wiki. Runs seven checks: missing pages, orphans, frontmatter completeness, source integrity, contradictions, glossary gaps, and index counts.

- `--fix` — create stub pages for missing wikilinks, fix frontmatter issues
- `--report-only` — print to console only, skip writing `wiki/lint-report.md`
- `--section <name>` — run a single check: `orphans`, `missing`, `frontmatter`, `contradictions`, `glossary`, `sources`

### `/graph-analyze [--console-only]`

Analyze the wiki as a directed graph (pages = nodes, `[[wikilinks]]` = edges). Computes node/edge counts, degree, density, orphans, sinks, broken links, and top-10 hubs.

- `--console-only` — print to console only, skip writing `_notes/graph-analysis-YYYY-MM-DD.md`

### `/transcript [<filename>] [--lang it|en] [--summary]`

Transcribe audio/video files from `_inbox/transcription/` using mlx_whisper. Supported formats: `.mp4`, `.mov`, `.mkv`, `.webm`, `.avi`, `.mp3`, `.m4a`, `.wav`, `.ogg`, `.aac`, `.flac`.

- `<filename>` — transcribe only that file (omit to transcribe all pending files)
- `--lang` — language code for whisper (auto-detect if not set)
- `--summary` — after transcription, generate a structured summary (`_SUMMARY.txt`). Meeting content uses Italian format with sections for decisions and action items; general content uses English format with entities and notable quotes.
