"""Test per _parse_file_blocks.py — parser FILE/REVIEW blocks e path safety."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _parse_file_blocks import parse_blocks, is_safe_ingest_path


def block(path: str, content: str) -> str:
    return f"---FILE: {path}---\n{content}\n---END FILE---"


class TestParseBlocks(unittest.TestCase):
    def test_single_block(self):
        result = parse_blocks(block("wiki/entities/foo.md", "# Foo"))
        self.assertEqual(len(result.blocks), 1)
        self.assertEqual(result.blocks[0].path, "wiki/entities/foo.md")
        self.assertEqual(result.blocks[0].content, "# Foo")
        self.assertEqual(result.warnings, [])

    def test_multiple_blocks(self):
        text = block("wiki/a.md", "A") + "\n\n" + block("wiki/b.md", "B")
        result = parse_blocks(text)
        self.assertEqual([b.path for b in result.blocks], ["wiki/a.md", "wiki/b.md"])

    def test_crlf_normalization(self):
        text = block("wiki/a.md", "line1\nline2").replace("\n", "\r\n")
        result = parse_blocks(text)
        self.assertEqual(len(result.blocks), 1)
        self.assertEqual(result.blocks[0].content, "line1\nline2")

    def test_truncated_block_dropped_with_warning(self):
        text = "---FILE: wiki/a.md---\ncontenuto senza closer"
        result = parse_blocks(text)
        self.assertEqual(result.blocks, [])
        self.assertEqual(len(result.warnings), 1)
        self.assertIn("truncation", result.warnings[0])

    def test_closer_inside_code_fence_ignored(self):
        content = "```\n---END FILE---\n```\nreale"
        result = parse_blocks(block("wiki/a.md", content))
        self.assertEqual(len(result.blocks), 1)
        self.assertIn("---END FILE---", result.blocks[0].content)
        self.assertIn("reale", result.blocks[0].content)

    def test_marker_case_and_space_variants(self):
        text = "--- FILE: wiki/a.md ---\nX\n---end file---"
        result = parse_blocks(text)
        self.assertEqual(len(result.blocks), 1)

    def test_unsafe_path_rejected_with_warning(self):
        result = parse_blocks(block("../../etc/passwd", "evil"))
        self.assertEqual(result.blocks, [])
        self.assertTrue(any("unsafe path" in w for w in result.warnings))

    def test_review_block_parsed(self):
        text = (
            block("wiki/a.md", "A")
            + "\n\n---REVIEW: contradiction | Titolo---\n"
            + "Descrizione.\nOPTIONS: Create Page | Skip\nPAGES: wiki/a.md, wiki/b.md\n"
            + "---END REVIEW---"
        )
        result = parse_blocks(text)
        self.assertEqual(len(result.reviews), 1)
        r = result.reviews[0]
        self.assertEqual(r.type, "contradiction")
        self.assertEqual(r.title, "Titolo")
        self.assertEqual(r.options, ["Create Page", "Skip"])
        self.assertEqual(r.pages, ["wiki/a.md", "wiki/b.md"])

    def test_unknown_review_type_becomes_confirm(self):
        text = "---REVIEW: banana | T---\nbody\n---END REVIEW---"
        result = parse_blocks(text)
        self.assertEqual(result.reviews[0].type, "confirm")


class TestIsSafeIngestPath(unittest.TestCase):
    def test_valid_wiki_paths(self):
        self.assertTrue(is_safe_ingest_path("wiki/entities/foo.md"))
        self.assertTrue(is_safe_ingest_path("wiki/concepts/foo-bar.md"))

    def test_rejects_outside_wiki(self):
        self.assertFalse(is_safe_ingest_path("raw/sources/x.md"))
        self.assertFalse(is_safe_ingest_path("CLAUDE.md"))

    def test_rejects_traversal_and_absolute(self):
        self.assertFalse(is_safe_ingest_path("wiki/../secrets.json"))
        self.assertFalse(is_safe_ingest_path("/etc/passwd"))
        self.assertFalse(is_safe_ingest_path("C:/Windows/system32"))
        self.assertFalse(is_safe_ingest_path("wiki\\..\\x.md"))

    def test_rejects_windows_invalid(self):
        self.assertFalse(is_safe_ingest_path("wiki/CON.md"))
        self.assertFalse(is_safe_ingest_path("wiki/foo|bar.md"))
        self.assertFalse(is_safe_ingest_path("wiki/foo. "))

    def test_rejects_empty_and_control(self):
        self.assertFalse(is_safe_ingest_path(""))
        self.assertFalse(is_safe_ingest_path("   "))
        self.assertFalse(is_safe_ingest_path("wiki/foo\x00.md"))


if __name__ == "__main__":
    unittest.main()
