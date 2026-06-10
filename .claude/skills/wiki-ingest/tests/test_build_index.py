"""Test per build_index.py — indice deterministico dal filesystem."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_index import build_index


def page(page_type: str, title: str) -> str:
    return f"---\ntype: {page_type}\ntitle: {title}\ncreated: 2026-01-01\n---\n\n# {title}\n"


class TestBuildIndex(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.vault = Path(self._tmp.name)
        (self.vault / ".llm-wiki").mkdir()
        for sub in ("entities", "concepts", "sources", "queries", "synthesis"):
            (self.vault / "wiki" / sub).mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, rel: str, content: str):
        (self.vault / "wiki" / rel).write_text(content, encoding="utf-8")

    def test_empty_wiki(self):
        out = build_index(self.vault)
        self.assertIn("Vuoto", out)

    def test_groups_by_type_with_counts(self):
        self._write("entities/foo.md", page("entity", "Foo Corp"))
        self._write("entities/bar.md", page("entity", "Bar Inc"))
        self._write("concepts/baz.md", page("concept", "Baz Theory"))
        out = build_index(self.vault)
        self.assertIn("## Entities (2)", out)
        self.assertIn("## Concepts (1)", out)
        self.assertIn("- [[foo]] — Foo Corp", out)
        self.assertIn("- [[bar]] — Bar Inc", out)

    def test_excludes_managed_files(self):
        self._write("index.md", "vecchio indice")
        self._write("log.md", "log")
        self._write("overview.md", "overview")
        self._write("entities/foo.md", page("entity", "Foo"))
        out = build_index(self.vault)
        self.assertNotIn("[[index]]", out)
        self.assertNotIn("[[log]]", out)
        self.assertNotIn("[[overview]]", out)

    def test_missing_type_falls_back_to_folder(self):
        self._write("concepts/no-fm.md", "# Senza frontmatter\n")
        out = build_index(self.vault)
        self.assertIn("## Concepts (1)", out)
        self.assertIn("[[no-fm]]", out)

    def test_deterministic_output(self):
        self._write("entities/foo.md", page("entity", "Foo"))
        self.assertEqual(build_index(self.vault), build_index(self.vault))


if __name__ == "__main__":
    unittest.main()
