"""Test per cache.py — hit/miss, collisioni basename, remove."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import cache as cache_mod


class TestCache(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.vault = Path(self._tmp.name)
        (self.vault / "wiki").mkdir()
        (self.vault / ".llm-wiki").mkdir()
        (self.vault / "wiki" / "out.md").write_text("pagina", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def _make_source(self, rel: str, content: str) -> Path:
        p = self.vault / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return p

    def test_miss_then_hit(self):
        src = self._make_source("_inbox/doc.txt", "contenuto")
        self.assertIsNone(cache_mod.check_cache(self.vault, src))
        cache_mod.save_entry(self.vault, src, ["wiki/out.md"])
        self.assertEqual(cache_mod.check_cache(self.vault, src), ["wiki/out.md"])

    def test_changed_content_is_miss(self):
        src = self._make_source("_inbox/doc.txt", "v1")
        cache_mod.save_entry(self.vault, src, ["wiki/out.md"])
        src.write_text("v2", encoding="utf-8")
        self.assertIsNone(cache_mod.check_cache(self.vault, src))

    def test_deleted_output_is_miss(self):
        src = self._make_source("_inbox/doc.txt", "contenuto")
        cache_mod.save_entry(self.vault, src, ["wiki/out.md"])
        (self.vault / "wiki" / "out.md").unlink()
        self.assertIsNone(cache_mod.check_cache(self.vault, src))

    def test_same_basename_different_content_coexist(self):
        a = self._make_source("_inbox/a/doc.txt", "contenuto A")
        b = self._make_source("_inbox/b/doc.txt", "contenuto B")
        cache_mod.save_entry(self.vault, a, ["wiki/out.md"])
        cache_mod.save_entry(self.vault, b, ["wiki/out.md"])
        # Entrambe le entry sopravvivono (prima del fix B sovrascriveva A)
        self.assertEqual(cache_mod.check_cache(self.vault, a), ["wiki/out.md"])
        self.assertEqual(cache_mod.check_cache(self.vault, b), ["wiki/out.md"])

    def test_archived_copy_still_hits(self):
        # Stesso nome e stesso contenuto in path diverso (es. _inbox → raw/sources)
        src = self._make_source("_inbox/doc.txt", "contenuto")
        cache_mod.save_entry(self.vault, src, ["wiki/out.md"])
        archived = self._make_source("raw/sources/doc.txt", "contenuto")
        self.assertEqual(cache_mod.check_cache(self.vault, archived), ["wiki/out.md"])

    def test_remove_by_basename_clears_all_hashes(self):
        a = self._make_source("_inbox/a/doc.txt", "contenuto A")
        b = self._make_source("_inbox/b/doc.txt", "contenuto B")
        cache_mod.save_entry(self.vault, a, ["wiki/out.md"])
        cache_mod.save_entry(self.vault, b, ["wiki/out.md"])
        self.assertTrue(cache_mod.remove_entry(self.vault, "doc.txt"))
        self.assertIsNone(cache_mod.check_cache(self.vault, a))
        self.assertIsNone(cache_mod.check_cache(self.vault, b))

    def test_remove_missing_returns_false(self):
        self.assertFalse(cache_mod.remove_entry(self.vault, "inesistente.txt"))

    def test_legacy_name_only_entry_still_hits(self):
        src = self._make_source("_inbox/doc.txt", "contenuto")
        legacy = {
            "entries": {
                "doc.txt": {
                    "hash": cache_mod.sha256_file(src),
                    "timestamp": 0,
                    "files_written": ["wiki/out.md"],
                }
            }
        }
        cache_mod.save_cache(self.vault, legacy)
        self.assertEqual(cache_mod.check_cache(self.vault, src), ["wiki/out.md"])


if __name__ == "__main__":
    unittest.main()
