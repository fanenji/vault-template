"""Test per fix_link_sources.py — parser di `sources` e fallback di migrazione
(crea source_path dai filename in sources quando source_path è assente).
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import fix_link_sources as fls  # noqa: E402


def page_with_sources(sources_line: str) -> str:
    return (
        "---\n"
        "type: source\n"
        'title: "Source: doc"\n'
        "created: 2026-01-01\n"
        f"{sources_line}\n"
        "tags: []\n"
        "---\n\n"
        "Body.\n"
    )


def malformed_page(sources_line: str) -> str:
    """Frontmatter senza il `---` di apertura (solo chiusura)."""
    return (
        "type: source\n"
        'title: "Source: doc"\n'
        "created: 2026-01-01\n"
        f"{sources_line}\n"
        "tags: []\n"
        "---\n\n"
        "Body.\n"
    )


class TestCurrentSourcesValues(unittest.TestCase):
    def test_inline_single_quoted(self):
        self.assertEqual(
            fls.current_sources_values(page_with_sources('sources: ["a.md"]')),
            ["a.md"],
        )

    def test_inline_multiple(self):
        self.assertEqual(
            fls.current_sources_values(page_with_sources('sources: ["a.md", "b.md"]')),
            ["a.md", "b.md"],
        )

    def test_inline_comma_inside_filename(self):
        self.assertEqual(
            fls.current_sources_values(
                page_with_sources('sources: ["Iceberg, The Right Idea.md"]')
            ),
            ["Iceberg, The Right Idea.md"],
        )

    def test_inline_bare(self):
        self.assertEqual(
            fls.current_sources_values(page_with_sources("sources: [a.md, b.md]")),
            ["a.md", "b.md"],
        )

    def test_block_sequence(self):
        content = (
            "---\n"
            "type: source\n"
            "sources:\n"
            "  - a.md\n"
            '  - "b.md"\n'
            "tags: []\n"
            "---\n\nBody.\n"
        )
        self.assertEqual(fls.current_sources_values(content), ["a.md", "b.md"])

    def test_absent(self):
        content = "---\ntype: source\ntitle: T\n---\n\nBody.\n"
        self.assertEqual(fls.current_sources_values(content), [])


class TestFixPageFallback(unittest.TestCase):
    def _vault(self, tmp: str) -> Path:
        root = Path(tmp)
        (root / "wiki" / "sources").mkdir(parents=True)
        (root / "raw" / "sources").mkdir(parents=True)
        return root

    def _raw(self, root: Path, name: str, frontmatter: str = "") -> None:
        fm = f"---\n{frontmatter}\n---\n\n" if frontmatter else ""
        (root / "raw" / "sources" / name).write_text(fm + "raw body\n", encoding="utf-8")

    def _wiki(self, root: Path, name: str, content: str) -> Path:
        p = root / "wiki" / "sources" / name
        p.write_text(content, encoding="utf-8")
        return p

    def test_single_source_creates_source_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._vault(tmp)
            self._raw(root, "doc.md")
            page = self._wiki(root, "doc.md", page_with_sources('sources: ["doc.md"]'))
            self.assertEqual(fls.fix_page(root, page, dry_run=False), "updated")
            out = page.read_text(encoding="utf-8")
            self.assertIn('source_path: "[[raw/sources/doc]]"', out)
            # nessun URL nel raw → sources resta invariato
            self.assertIn('sources: ["doc.md"]', out)

    def test_multiple_sources_creates_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._vault(tmp)
            self._raw(root, "summary.md")
            self._raw(root, "transcript.md")
            page = self._wiki(
                root, "topic.md",
                page_with_sources('sources: ["summary.md", "transcript.md"]'),
            )
            self.assertEqual(fls.fix_page(root, page, dry_run=False), "updated")
            out = page.read_text(encoding="utf-8")
            self.assertIn(
                'source_path: ["[[raw/sources/summary]]", "[[raw/sources/transcript]]"]',
                out,
            )

    def test_url_in_raw_rewrites_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._vault(tmp)
            self._raw(root, "doc.md", frontmatter="source: https://example.com/x")
            page = self._wiki(root, "doc.md", page_with_sources('sources: ["doc.md"]'))
            self.assertEqual(fls.fix_page(root, page, dry_run=False), "updated")
            out = page.read_text(encoding="utf-8")
            self.assertIn('source_path: "[[raw/sources/doc]]"', out)
            self.assertIn('sources: ["https://example.com/x"]', out)

    def test_partial_url_keeps_sources(self):
        # solo uno dei due raw ha source: → non si rimpiazza sources (no data loss)
        with tempfile.TemporaryDirectory() as tmp:
            root = self._vault(tmp)
            self._raw(root, "a.md", frontmatter="source: https://example.com/a")
            self._raw(root, "b.md")
            page = self._wiki(
                root, "topic.md", page_with_sources('sources: ["a.md", "b.md"]')
            )
            self.assertEqual(fls.fix_page(root, page, dry_run=False), "updated")
            out = page.read_text(encoding="utf-8")
            self.assertIn('sources: ["a.md", "b.md"]', out)

    def test_unresolvable_sources_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._vault(tmp)
            page = self._wiki(root, "doc.md", page_with_sources('sources: ["ghost.md"]'))
            self.assertEqual(fls.fix_page(root, page, dry_run=False), "skipped")

    def test_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._vault(tmp)
            self._raw(root, "doc.md")
            original = page_with_sources('sources: ["doc.md"]')
            page = self._wiki(root, "doc.md", original)
            self.assertEqual(fls.fix_page(root, page, dry_run=True), "updated")
            self.assertEqual(page.read_text(encoding="utf-8"), original)

    def test_idempotent_after_migration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._vault(tmp)
            self._raw(root, "doc.md")
            page = self._wiki(root, "doc.md", page_with_sources('sources: ["doc.md"]'))
            fls.fix_page(root, page, dry_run=False)
            # secondo giro: ora ha source_path → ramo standard, nessun cambiamento
            self.assertEqual(fls.fix_page(root, page, dry_run=False), "unchanged")


class TestRepairMissingFence(unittest.TestCase):
    def test_repairs_missing_opening_fence(self):
        out = fls.repair_missing_fence(malformed_page('sources: ["doc.md"]'))
        self.assertIsNotNone(out)
        self.assertTrue(out.startswith("---\ntype: source\n"))

    def test_wellformed_unchanged(self):
        self.assertIsNone(fls.repair_missing_fence(page_with_sources('sources: ["doc.md"]')))

    def test_prose_body_not_touched(self):
        # un doc che inizia con prosa e ha un --- (riga orizzontale) nel body
        doc = "Questo è un testo introduttivo.\n\n---\n\nAltra sezione.\n"
        self.assertIsNone(fls.repair_missing_fence(doc))

    def test_no_closing_fence_not_touched(self):
        doc = "type: source\ntitle: x\n\nBody senza fence di chiusura.\n"
        self.assertIsNone(fls.repair_missing_fence(doc))


class TestFixPageRepairsFence(unittest.TestCase):
    def _vault(self, tmp):
        root = Path(tmp)
        (root / "wiki" / "sources").mkdir(parents=True)
        (root / "raw" / "sources").mkdir(parents=True)
        return root

    def test_malformed_with_resolvable_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._vault(tmp)
            (root / "raw" / "sources" / "doc.md").write_text("raw\n", encoding="utf-8")
            page = root / "wiki" / "sources" / "doc.md"
            page.write_text(malformed_page('sources: ["doc.md"]'), encoding="utf-8")
            self.assertEqual(fls.fix_page(root, page, dry_run=False), "updated")
            out = page.read_text(encoding="utf-8")
            self.assertTrue(out.startswith("---\n"))           # fence riparato
            self.assertIn('source_path: "[[raw/sources/doc]]"', out)

    def test_malformed_without_resolvable_source_still_repairs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._vault(tmp)
            page = root / "wiki" / "sources" / "doc.md"
            page.write_text(malformed_page('sources: ["ghost.md"]'), encoding="utf-8")
            self.assertEqual(fls.fix_page(root, page, dry_run=False), "updated")
            out = page.read_text(encoding="utf-8")
            self.assertTrue(out.startswith("---\n"))           # fence riparato
            self.assertNotIn("source_path:", out)              # nessun source_path derivabile

    def test_malformed_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._vault(tmp)
            (root / "raw" / "sources" / "doc.md").write_text("raw\n", encoding="utf-8")
            page = root / "wiki" / "sources" / "doc.md"
            page.write_text(malformed_page('sources: ["doc.md"]'), encoding="utf-8")
            fls.fix_page(root, page, dry_run=False)
            self.assertEqual(fls.fix_page(root, page, dry_run=False), "unchanged")


if __name__ == "__main__":
    unittest.main()
