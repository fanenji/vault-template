#!/usr/bin/env python3
"""
generate_moc.py — Generate static MOC (Map of Content) for folder-note index files.

For each folder that has a folder-note index (a .md file named after its parent folder),
this script inserts a wikilink list of:
  - direct .md files in that folder (excluding the index note itself)
  - direct subfolders that have their own index note (linked via [[SUBFOLDER]])

The MOC section is delimited by markers so the script is safe to re-run.

Usage (from vault root or any location):
    python3 "99 System/Scripts/generate_moc.py"

Or from the Obsidian terminal plugin:
    python3 "/Users/S.Parodi/Library/Mobile Documents/com~apple~CloudDocs/Obsidian/Vault/99 System/Scripts/generate_moc.py"
"""

import os
import re

# ── Configuration ────────────────────────────────────────────────────────────

VAULT = "/Users/S.Parodi/Library/Mobile Documents/com~apple~CloudDocs/Obsidian/Vault"

# Top-level folders to process (subfolders are discovered automatically)
INCLUDE_ROOTS = ["20 PROGETTI", "30 WIKI", "40 NOTE", "50 IDEE"]

# Folders to skip entirely (e.g. large auto-imported bookmark dumps)
SKIP_DIRS = {"00 BOOKMARKS", ".obsidian", ".git", ".trash"}

# MOC section delimiters written into each folder-note
MOC_START = "%% MOC START %%"
MOC_END   = "%% MOC END %%"

# ── Helpers ──────────────────────────────────────────────────────────────────

def get_folder_note(dirpath):
    """Return path to the folder-note index if it exists, else None."""
    folder_name = os.path.basename(dirpath)
    candidate = os.path.join(dirpath, folder_name + ".md")
    return candidate if os.path.exists(candidate) else None


def build_moc_links(dirpath, index_filename):
    """
    Collect direct children to include in the MOC:
      - .md files in dirpath (excluding the index note itself)
      - subfolders that have their own index note
    Returns a sorted list of wikilink strings.
    """
    links = []

    with os.scandir(dirpath) as entries:
        for entry in entries:
            if entry.name.startswith("."):
                continue
            if entry.name in SKIP_DIRS:
                continue

            if entry.is_file() and entry.name.endswith(".md"):
                if entry.name == index_filename:
                    continue  # skip the index note itself
                note_name = entry.name[:-3]  # strip .md
                links.append(note_name)

            elif entry.is_dir():
                # Include subfolder only if it has its own index note
                sub_index = os.path.join(entry.path, entry.name + ".md")
                if os.path.exists(sub_index):
                    links.append(entry.name)

    return sorted(links, key=lambda s: s.lower())


def format_moc_section(links):
    """Render the MOC block to insert into the folder-note."""
    lines = [MOC_START]
    if links:
        for name in links:
            lines.append(f"- [[{name}]]")
    else:
        lines.append("_empty folder_")
    lines.append(MOC_END)
    return "\n".join(lines)


def update_folder_note(note_path, moc_block):
    """Insert or replace the MOC section in the folder-note."""
    with open(note_path, "r", encoding="utf-8") as f:
        content = f.read()

    pattern = re.compile(
        re.escape(MOC_START) + r".*?" + re.escape(MOC_END),
        re.DOTALL,
    )

    if pattern.search(content):
        new_content = pattern.sub(moc_block, content)
    else:
        # Append after existing content
        new_content = content.rstrip("\n") + "\n\n" + moc_block + "\n"

    if new_content != content:
        with open(note_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        return True
    return False


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    updated = 0
    skipped = 0

    for root_name in INCLUDE_ROOTS:
        root_path = os.path.join(VAULT, root_name)
        if not os.path.isdir(root_path):
            print(f"  [WARN] Root not found: {root_name}")
            continue

        for dirpath, dirs, files in os.walk(root_path):
            # Prune dirs in-place to skip unwanted subtrees
            dirs[:] = sorted(
                d for d in dirs
                if not d.startswith(".") and d not in SKIP_DIRS
            )

            note_path = get_folder_note(dirpath)
            if not note_path:
                continue

            index_filename = os.path.basename(note_path)
            links = build_moc_links(dirpath, index_filename)
            moc_block = format_moc_section(links)

            changed = update_folder_note(note_path, moc_block)
            rel = os.path.relpath(note_path, VAULT)

            if changed:
                print(f"  ✓  {rel}  ({len(links)} entries)")
                updated += 1
            else:
                skipped += 1

    print(f"\nDone — {updated} updated, {skipped} already up to date.")


if __name__ == "__main__":
    main()
