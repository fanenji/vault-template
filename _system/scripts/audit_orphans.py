#!/usr/bin/env python3
"""Check 3: Find orphan notes (zero inbound wikilinks)."""
import os, re, json

VAULT = "/Users/S.Parodi/Library/Mobile Documents/com~apple~CloudDocs/Obsidian/Vault"
LINK_RE = re.compile(r'\[\[([^\]|#\n]+?)(?:[|#][^\]]*?)?\]\]')

all_files = []
stem_to_rel = {}
for root, dirs, files in os.walk(VAULT):
    dirs[:] = [d for d in dirs if not d.startswith('.')]
    for fname in files:
        if fname.endswith('.md'):
            fpath = os.path.join(root, fname)
            rel = os.path.relpath(fpath, VAULT)
            all_files.append(rel)
            stem = os.path.splitext(fname)[0].lower()
            stem_to_rel[stem] = rel

inbound = {rel: 0 for rel in all_files}

for rel in all_files:
    fpath = os.path.join(VAULT, rel)
    try:
        content = open(fpath, encoding='utf-8').read()
    except Exception:
        continue
    for m in LINK_RE.finditer(content):
        target = m.group(1).strip()
        stem = os.path.splitext(os.path.basename(target.lower()))[0]
        if stem in stem_to_rel:
            target_rel = stem_to_rel[stem]
            if target_rel != rel:
                inbound[target_rel] = inbound.get(target_rel, 0) + 1

orphans = [{"file": f, "inbound_links": 0} for f, count in inbound.items() if count == 0]
print(json.dumps(orphans))
