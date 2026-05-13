#!/usr/bin/env python3
"""Fix missing frontmatter fields without modifying existing values.

Usage:
    python3 fix_frontmatter.py [frontmatter_results.json]

If no argument is given, re-runs audit_frontmatter.py automatically.
"""
import os, re, json, sys, subprocess
from datetime import datetime

VAULT = "/Users/S.Parodi/Library/Mobile Documents/com~apple~CloudDocs/Obsidian/Vault"
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
REQUIRED = ['title', 'created', 'tags', 'type']
FM_RE = re.compile(r'^(---\s*\n)(.*?)(\n---)', re.DOTALL)

SKIP_PREFIXES = ['CLAUDE.md', 'Templates/']

def get_birthtime(path):
    try:
        return datetime.fromtimestamp(os.stat(path).st_birthtime).strftime('%Y-%m-%d')
    except Exception:
        return datetime.fromtimestamp(os.path.getmtime(path)).strftime('%Y-%m-%d')

def should_skip(rel):
    return any(rel.startswith(p) or rel == p.rstrip('/') for p in SKIP_PREFIXES)

def make_default(field, fpath):
    if field == 'title':
        stem = os.path.splitext(os.path.basename(fpath))[0]
        return f'title: "{stem}"'
    if field == 'type':
        return 'type: note'
    if field == 'created':
        return f'created: {get_birthtime(fpath)}'
    if field == 'tags':
        return 'tags: []'

# Load issues — from argument or by running the audit script
if len(sys.argv) > 1:
    fm_issues = json.load(open(sys.argv[1]))
else:
    result = subprocess.run(
        ['python3', os.path.join(SCRIPTS_DIR, 'audit_frontmatter.py')],
        capture_output=True, text=True
    )
    fm_issues = json.loads(result.stdout)

fixed_count = 0
added_fields = {f: 0 for f in REQUIRED}
errors = []

for item in fm_issues:
    rel = item['file']
    if should_skip(rel):
        continue
    fpath = os.path.join(VAULT, rel)
    if not os.path.exists(fpath):
        continue
    try:
        content = open(fpath, encoding='utf-8').read()
    except Exception as e:
        errors.append(f"{rel}: read error — {e}")
        continue

    missing = item['missing']
    if not missing:
        continue

    if not item['has_frontmatter']:
        lines = [make_default(f, fpath) for f in REQUIRED]
        new_content = '---\n' + '\n'.join(lines) + '\n---\n' + content
    else:
        m = FM_RE.match(content)
        if not m:
            errors.append(f"{rel}: FM regex mismatch")
            continue
        new_lines = [make_default(f, fpath) for f in missing]
        new_fm_body = '\n'.join(new_lines) + '\n' + m.group(2)
        new_content = m.group(1) + new_fm_body + m.group(3) + content[m.end():]

    try:
        with open(fpath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        fixed_count += 1
        for field in missing:
            added_fields[field] += 1
    except Exception as e:
        errors.append(f"{rel}: write error — {e}")

print(f"Fixed: {fixed_count} files")
print(f"Fields added: {added_fields}")
if errors:
    print(f"\nErrors ({len(errors)}):")
    for e in errors[:20]:
        print(f"  {e}")
