"""Test per _source_meta.py — normalizzazione frontmatter pagine wiki/sources/."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _source_meta import raw_wikilink, extract_source_url, apply_source_meta


def source_page(extra_fm: str = "") -> str:
    return (
        "---\n"
        "type: source\n"
        "title: Test Page\n"
        "created: 2026-01-01\n"
        "sources: [doc.md]\n"
        "source_path: raw/sources/doc.md\n"
        f"{extra_fm}"
        "---\n"
        "\n# Test Page\n\nBody con [[wikilink]].\n"
    )


class TestRawWikilink(unittest.TestCase):
    def test_md_drops_extension(self):
        self.assertEqual(raw_wikilink("doc.md"), "[[raw/sources/doc]]")

    def test_markdown_drops_extension(self):
        self.assertEqual(raw_wikilink("doc.markdown"), "[[raw/sources/doc]]")

    def test_other_formats_keep_extension(self):
        self.assertEqual(raw_wikilink("paper.pdf"), "[[raw/sources/paper.pdf]]")

    def test_name_with_spaces_and_parens(self):
        self.assertEqual(
            raw_wikilink("7 Local LLM Families To Replace Claude -Codex (for everyday tasks).md"),
            "[[raw/sources/7 Local LLM Families To Replace Claude -Codex (for everyday tasks)]]",
        )


class TestExtractSourceUrl(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, name: str, content: str) -> Path:
        p = self.dir / name
        p.write_text(content, encoding="utf-8")
        return p

    def test_url_extracted(self):
        p = self._write("clip.md", "---\nsource: https://example.com/page\n---\nbody\n")
        self.assertEqual(extract_source_url(p), "https://example.com/page")

    def test_quoted_url_extracted(self):
        p = self._write("clip.md", '---\nsource: "https://example.com/page"\n---\nbody\n')
        self.assertEqual(extract_source_url(p), "https://example.com/page")

    def test_no_frontmatter(self):
        p = self._write("clip.md", "# Solo body\n")
        self.assertIsNone(extract_source_url(p))

    def test_source_field_not_url(self):
        p = self._write("clip.md", "---\nsource: il mio archivio\n---\nbody\n")
        self.assertIsNone(extract_source_url(p))

    def test_non_markdown_returns_none(self):
        p = self._write("doc.pdf", "binario finto")
        self.assertIsNone(extract_source_url(p))

    def test_missing_file_returns_none(self):
        self.assertIsNone(extract_source_url(self.dir / "inesistente.md"))


class TestApplySourceMeta(unittest.TestCase):
    LINK = "[[raw/sources/doc]]"
    URL = "https://example.com/original"

    def test_rewrites_source_path_as_quoted_wikilink(self):
        out = apply_source_meta(source_page(), self.LINK, None)
        self.assertIn('source_path: "[[raw/sources/doc]]"', out)
        self.assertNotIn("source_path: raw/sources/doc.md", out)

    def test_rewrites_sources_with_url(self):
        out = apply_source_meta(source_page(), self.LINK, self.URL)
        self.assertIn(f'sources: ["{self.URL}"]', out)
        self.assertNotIn("sources: [doc.md]", out)

    def test_without_url_sources_untouched(self):
        out = apply_source_meta(source_page(), self.LINK, None)
        self.assertIn("sources: [doc.md]", out)

    def test_adds_source_path_when_missing(self):
        page = "---\ntype: source\ntitle: T\ncreated: 2026-01-01\n---\n\nbody\n"
        out = apply_source_meta(page, self.LINK, None)
        self.assertIn('source_path: "[[raw/sources/doc]]"', out)

    def test_preserves_other_fields_and_body(self):
        out = apply_source_meta(source_page(extra_fm="custom_field: valore\n"),
                                self.LINK, self.URL)
        self.assertIn("custom_field: valore", out)
        self.assertIn("title: Test Page", out)
        self.assertIn("Body con [[wikilink]].", out)

    def test_idempotent(self):
        once = apply_source_meta(source_page(), self.LINK, self.URL)
        twice = apply_source_meta(once, self.LINK, self.URL)
        self.assertEqual(once, twice)

    def test_no_frontmatter_unchanged(self):
        page = "# Pagina senza frontmatter\n"
        self.assertEqual(apply_source_meta(page, self.LINK, self.URL), page)

    def test_source_path_as_list_when_multiple(self):
        links = ["[[raw/sources/a]]", "[[raw/sources/b]]"]
        out = apply_source_meta(source_page(), links, None)
        self.assertIn('source_path: ["[[raw/sources/a]]", "[[raw/sources/b]]"]', out)

    def test_sources_as_list_when_multiple_urls(self):
        urls = ["https://example.com/a", "https://example.com/b"]
        out = apply_source_meta(source_page(), self.LINK, urls)
        self.assertIn('sources: ["https://example.com/a", "https://example.com/b"]', out)

    def test_single_string_rendering_unchanged(self):
        # la forma a stringa singola deve restare identica (retrocompat)
        out = apply_source_meta(source_page(), self.LINK, self.URL)
        self.assertIn('source_path: "[[raw/sources/doc]]"', out)
        self.assertIn(f'sources: ["{self.URL}"]', out)


if __name__ == "__main__":
    unittest.main()
