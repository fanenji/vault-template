"""Test per _sanitize.py — i 3 fix ricorrenti su output LLM."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _sanitize import sanitize_ingested_content

CLEAN_PAGE = """---
type: entity
title: Foo
---

# Foo

Body con [[wikilink]].
"""


class TestSanitize(unittest.TestCase):
    def test_clean_content_untouched(self):
        self.assertEqual(sanitize_ingested_content(CLEAN_PAGE), CLEAN_PAGE)

    def test_strips_outer_yaml_fence(self):
        wrapped = "```yaml\n" + CLEAN_PAGE + "```\n"
        self.assertEqual(sanitize_ingested_content(wrapped), CLEAN_PAGE)

    def test_strips_frontmatter_key_prefix(self):
        prefixed = "frontmatter:\n" + CLEAN_PAGE
        self.assertEqual(sanitize_ingested_content(prefixed), CLEAN_PAGE)

    def test_repairs_wikilink_list_in_frontmatter(self):
        broken = (
            "---\n"
            "type: entity\n"
            "related: [[foo]], [[bar-baz]]\n"
            "---\n"
            "Body.\n"
        )
        fixed = sanitize_ingested_content(broken)
        self.assertIn('related: ["[[foo]]", "[[bar-baz]]"]', fixed)
        self.assertIn("Body.", fixed)

    def test_wikilinks_in_body_untouched(self):
        page = "---\ntype: entity\n---\nrelated: [[a]], [[b]] nel body resta com'è\n"
        self.assertEqual(sanitize_ingested_content(page), page)

    def test_fence_in_body_not_stripped(self):
        page = CLEAN_PAGE + "\n```python\ncode\n```\n"
        self.assertEqual(sanitize_ingested_content(page), page)


if __name__ == "__main__":
    unittest.main()
