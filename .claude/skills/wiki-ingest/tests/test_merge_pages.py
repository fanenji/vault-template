"""Test per _merge_pages.py — merge soft, locked fields, preservazione custom."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _merge_pages import (
    merge_pages,
    apply_llm_merge_result,
    merge_array_field,
    parse_frontmatter,
)

TODAY = "2026-06-10"

EXISTING = """---
type: entity
title: Foo Corp
created: 2026-01-01
tags: [alpha]
custom_scalar: tenuto
---

# Foo Corp

Body esistente.
"""

INCOMING_SAME_BODY = """---
type: entity
title: Foo Corporation
created: 2026-06-10
tags: [beta]
sources: ["doc.pdf"]
---

# Foo Corp

Body esistente.
"""

INCOMING_NEW_BODY = INCOMING_SAME_BODY.replace("Body esistente.", "Body nuovo, diverso.")


class TestMergeArrayField(unittest.TestCase):
    def test_union_keeps_order_and_dedups(self):
        self.assertEqual(merge_array_field(["a", "b"], ["b", "c"]), ["a", "b", "c"])

    def test_handles_none(self):
        self.assertEqual(merge_array_field(None, ["x"]), ["x"])
        self.assertEqual(merge_array_field(["x"], None), ["x"])


class TestMergePages(unittest.TestCase):
    def test_no_existing_returns_new(self):
        out = merge_pages("nuovo", None)
        self.assertEqual(out.content, "nuovo")
        self.assertFalse(out.merge_body_needed)

    def test_identical_returns_existing(self):
        out = merge_pages(EXISTING, EXISTING)
        self.assertEqual(out.content, EXISTING)
        self.assertFalse(out.merge_body_needed)

    def test_locked_fields_preserved_and_arrays_unioned(self):
        out = merge_pages(INCOMING_SAME_BODY, EXISTING, "doc.pdf", today=TODAY)
        fm, _ = parse_frontmatter(out.content)
        self.assertEqual(fm["title"], "Foo Corp")           # locked dall'esistente
        self.assertEqual(fm["created"], "2026-01-01")        # locked dall'esistente
        self.assertEqual(fm["tags"], ["alpha", "beta"])      # union
        self.assertEqual(fm["sources"], ["doc.pdf"])
        self.assertEqual(fm["updated"], TODAY)
        self.assertFalse(out.merge_body_needed)

    def test_custom_field_from_existing_survives(self):
        out = merge_pages(INCOMING_SAME_BODY, EXISTING, today=TODAY)
        self.assertIn("custom_scalar: tenuto", out.content)

    def test_nested_custom_field_survives_verbatim(self):
        existing = (
            "---\n"
            "type: entity\n"
            "title: Foo\n"
            "created: 2026-01-01\n"
            "meta:\n"
            "  nested: true\n"
            "  level: 2\n"
            "block_list:\n"
            "- uno\n"
            "- due\n"
            "---\n"
            "Body.\n"
        )
        incoming = "---\ntype: entity\ntitle: Foo\ncreated: 2026-06-10\n---\nBody.\n"
        out = merge_pages(incoming, existing, today=TODAY)
        self.assertIn("meta:\n  nested: true\n  level: 2", out.content)
        self.assertIn("block_list:\n- uno\n- due", out.content)

    def test_managed_block_style_list_replaced_not_duplicated(self):
        existing = "---\ntype: entity\ntitle: Foo\ncreated: 2026-01-01\ntags:\n  - alpha\n---\nBody.\n"
        incoming = "---\ntype: entity\ntitle: Foo\ncreated: 2026-06-10\ntags: [beta]\n---\nBody.\n"
        out = merge_pages(incoming, existing, today=TODAY)
        fm, _ = parse_frontmatter(out.content)
        self.assertEqual(fm["tags"], ["alpha", "beta"])
        self.assertEqual(out.content.count("tags:"), 1)

    def test_different_bodies_flag_merge_needed(self):
        out = merge_pages(INCOMING_NEW_BODY, EXISTING, today=TODAY)
        self.assertTrue(out.merge_body_needed)
        self.assertIn("Body esistente.", out.existing_body)
        self.assertIn("Body nuovo", out.incoming_body)
        # Su disco va il body nuovo (l'esistente è nella coda pending)
        self.assertIn("Body nuovo", out.content)


class TestApplyLlmMergeResult(unittest.TestCase):
    def _llm_output(self, body: str) -> str:
        return (
            "---\n"
            "type: entity\n"
            "title: Titolo LLM\n"
            "created: 2026-06-10\n"
            "tags: [gamma]\n"
            "---\n" + body
        )

    def test_good_output_locked_and_unioned(self):
        body = "Body fuso lungo che combina esistente e nuovo. " * 3
        final = apply_llm_merge_result(
            self._llm_output(body), EXISTING, INCOMING_NEW_BODY, today=TODAY
        )
        fm, out_body = parse_frontmatter(final)
        self.assertEqual(fm["title"], "Foo Corp")            # locked back
        self.assertEqual(fm["created"], "2026-01-01")
        self.assertIn("alpha", fm["tags"])                   # union old+new+llm
        self.assertIn("beta", fm["tags"])
        self.assertIn("gamma", fm["tags"])
        self.assertIn("Body fuso", out_body)
        self.assertIn("custom_scalar: tenuto", final)        # custom old-only

    def test_shrunk_body_falls_back_to_incoming(self):
        final = apply_llm_merge_result(
            self._llm_output("x"), EXISTING, INCOMING_NEW_BODY, today=TODAY
        )
        _, out_body = parse_frontmatter(final)
        self.assertIn("Body nuovo", out_body)

    def test_no_frontmatter_falls_back(self):
        final = apply_llm_merge_result(
            "solo testo senza frontmatter", EXISTING, INCOMING_NEW_BODY, today=TODAY
        )
        fm, out_body = parse_frontmatter(final)
        self.assertEqual(fm["title"], "Foo Corp")
        self.assertIn("Body nuovo", out_body)


if __name__ == "__main__":
    unittest.main()
