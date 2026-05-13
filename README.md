# Data Platform LLM Wiki

Obsidian vault documenting the Data Platform architecture, technologies, decisions, and research. Managed via LLM-based tooling.

The vault is divided in 2 parts:
- The LLM Wiki part
- The personal part

## LLM Wiki Part

The wiki is based on this OpenSource project: https://github.com/nashsu/llm_wiki

See `schema.md` for page types, frontmatter requirements, naming conventions, and the contradiction workflow.

See `purpose.md` for `<TODO>`

The /raw/ and /wiki/ folders and purpose.md and schema.md files pertain to the llm-wiki system and are managed by the LLM-Wiki system.

The `.llm-wiki/` directory contains internal tooling state (LanceDB, ingest queues, conversation history). These are managed automatically; do not modify directly unless you understand the full toolchain.

## Personal Part

This part extends the base LLM Wiki part with custom dir and commands.

The `_inbox`,`_notes` and `_system` folder are personal folders managed with the help of Claude/OpenCode agents.

Key conventions for operating in the personal folders:
- Notes use YAML frontmatter
- Cross-links use [[wikilink]] syntax
- Templater plugin is used for auto-insertion
- Do not assume plugin capabilities without checking documentation first
- Use the Obsidian CLI whenever possible

This is the hierarchy of the personal folders
- `_inbox/` - Inbox for new, unsorted items
	- `_inbox/clippings` - Clipping from web pages via Obsidian Web Clipper
	- `_inbox/Journal` - Temporary location for daily and journal notes
	- `_inbox/transcription` - Location for audio/video transcriptions made with the `/transcript` command
- `_notes/` - Notes personally redacted about projects, meetings and todos
	- `_notes/01.todo` — Active task and to-do tracking with Kanban view
	- `_notes/02.notes` — Work and operational notes
	- `_notes/03.meetings` — Notes about meetings
	- `_notes/04.projects` — Notes about active working projects
	- `_notes/90.archive` — Notes about archived projects
 - `_system/` - Obsidian system config, attachments, templates, canvas files
	 - `_system/scripts` - Contains custom scripts for managing the vault
	 - `_system/templates` - Obsidian note templates, do not move


## RULES
- NEVER delete files without explicit confirmation.

----

## Git Workflow

The **obsidian-git** plugin commit and sync on demand with the message format `vault backup: {{date}} - {{hostname}}`. Manual git operations are fine but avoid force-pushing or rebasing since the vault may be open on another device simultaneously. When committing manually, use descriptive messages.

---

## Available skills  
  
Skills loaded in `.claude/skills/`:  
- `obsidian-markdown` — Obsidian native syntax (ALWAYS use)  
- `obsidian-bases` — databases via .base  
- `json-canvas` — visual whiteboards  
- `obsidian-cli` — automation via obsdmd command  
- `defuddle` — clean web content extraction  
  
Before creating `.canvas` or `.base` files, consult the corresponding skill.  
Before fetching a URL, consult `defuddle`.


---
## Commands

Defined in `.claude/commands/` (Claude) and `.opencode/commands/` (OpenCode), backed by Python scripts in `_system/scripts/`.


| Command                           | Purpose                                                                                      |
| --------------------------------- | -------------------------------------------------------------------------------------------- |
| `/transcript [<file>]`            | Transcribe audio/video files from `_inbox/transcription/` with mlx_whisper                   |
| `/wiki-lint`                      | Seven-check health audit; writes `wiki/lint-report.md`                                       |
| `/graph-analyze [--console-only]` | Directed graph analysis of wiki link structure; writes `_notes/graph-analysis-YYYY-MM-DD.md` |
| `/wiki-qwery`                     | Search the vault and answer a question using accumulated knowledge                           |


### `/transcript [<filename>] [--lang it|en] [--summary]`

Transcribe audio/video files from `_inbox/transcription/` using mlx_whisper. Supported formats: `.mp4`, `.mov`, `.mkv`, `.webm`, `.avi`, `.mp3`, `.m4a`, `.wav`, `.ogg`, `.aac`, `.flac`.

- `<filename>` — transcribe only that file (omit to transcribe all pending files)
- `--lang` — language code for whisper (auto-detect if not set)
- `--summary` — after transcription, generate a structured summary (`_SUMMARY.txt`). Meeting content uses Italian format with sections for decisions and action items; general content uses English format with entities and notable quotes.

### `/wiki-lint [--fix] [--report-only] [--section <name>]`

Full health check on the wiki. Runs seven checks: missing pages, orphans, frontmatter completeness, source integrity, contradictions, glossary gaps, and index counts.

- `--fix` — create stub pages for missing wikilinks, fix frontmatter issues
- `--report-only` — print to console only, skip writing `wiki/lint-report.md`
- `--section <name>` — run a single check: `orphans`, `missing`, `frontmatter`, `contradictions`, `glossary`, `sources`

### `/graph-analyze [--console-only]`

Analyze the wiki as a directed graph (pages = nodes, `[[wikilinks]]` = edges). Computes node/edge counts, degree, density, orphans, sinks, broken links, and top-10 hubs.

- `--console-only` — print to console only, skip writing `_notes/graph-analysis-YYYY-MM-DD.md`

----

