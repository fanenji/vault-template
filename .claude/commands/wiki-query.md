---
description: Search the vault and answer a question using accumulated knowledge
argument-hint: <question in natural language>
---

I'll answer **$ARGUMENTS** by consulting the vault.

Strategy:

1. **Candidate search** (no full reads):
   - Use `grep -r -l --include="*.md"` in vault to find files
     with question terms
   - Start with wiki/ zone (most synthesized). If insufficient, expand
     to _notes/ and raw/

2. **Focused reading:**
   - Read up to 10 candidate files (prioritize wiki/)
   - If more than 10 are relevant, mention in answer and read most relevant
   - DO NOT read entire vault — for that I use Obsidian's search directly

3. **Answer synthesis:**
   - Answer in direct prose (not bullet point unless question asks)
   - ALWAYS cite consulted files via [[wikilinks]] in the format:
     "Per [[wiki/concepts/X]], ... In [[dev/adr/ADR-0007]], I decided..."
   - If answer requires inference (not literally in the vault),
     SIGNAL: "Inferring from [[X]] and [[Y]]: ..."
   - If the vault doesn't have enough info, SAY SO. Don't make stuff up.

4. **Suggest next steps** when relevant:
   - "There's no synthesis on X yet. Want me to run /wiki-ingest on Y to
     fill that in?"