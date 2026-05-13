#!/usr/bin/env python3
"""Check 2: Find broken [[wikilinks]] (note links and image refs)."""
import os, re, json

VAULT = "/Users/S.Parodi/Library/Mobile Documents/com~apple~CloudDocs/Obsidian/Vault"
LINK_RE = re.compile(r'\[\[([^\]|#\n]+?)(?:[|#][^\]]*?)?\]\]')

# Build stem index from all .md files
stem_map = {}
all_files = []
for root, dirs, files in os.walk(VAULT):
    dirs[:] = [d for d in dirs if not d.startswith('.')]
    for fname in files:
        if fname.endswith('.md'):
            fpath = os.path.join(root, fname)
            rel = os.path.relpath(fpath, VAULT)
            all_files.append(rel)
            stem = os.path.splitext(fname)[0].lower()
            stem_map[stem] = rel

broken = []
for rel in all_files:
    fpath = os.path.join(VAULT, rel)
    try:
        content = open(fpath, encoding='utf-8').read()
    except Exception:
        continue
    for m in LINK_RE.finditer(content):
        target = m.group(1).strip()
        stem = os.path.splitext(os.path.basename(target.lower()))[0]
        if stem not in stem_map:
            found = any(
                os.path.exists(os.path.join(VAULT, c))
                for c in [target + '.md', target]
            )
            if not found:
                broken.append({"file": rel, "link": target})

print(json.dumps(broken))
