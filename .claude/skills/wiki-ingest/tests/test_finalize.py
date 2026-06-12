"""Test per finalize.py — confinamento delle scritture dentro la vault."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from finalize import write_file


class TestWriteFileContainment(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.vault = Path(self._tmp.name).resolve()
        (self.vault / ".llm-wiki").mkdir()
        (self.vault / "wiki" / "entities").mkdir(parents=True)
        self._outside = tempfile.TemporaryDirectory()
        self.outside = Path(self._outside.name).resolve()

    def tearDown(self):
        self._tmp.cleanup()
        self._outside.cleanup()

    def test_normal_write_inside_vault(self):
        write_file(self.vault, "wiki/entities/foo.md", "content")
        self.assertEqual(
            (self.vault / "wiki" / "entities" / "foo.md").read_text(encoding="utf-8"),
            "content",
        )

    def test_write_creates_missing_parents(self):
        write_file(self.vault, "wiki/concepts/bar.md", "content")
        self.assertTrue((self.vault / "wiki" / "concepts" / "bar.md").is_file())

    def test_symlinked_dir_escaping_vault_rejected(self):
        # wiki/evil → directory fuori dalla vault: la scrittura deve fallire.
        (self.vault / "wiki" / "evil").symlink_to(self.outside)
        with self.assertRaises(OSError):
            write_file(self.vault, "wiki/evil/x.md", "evil")
        self.assertEqual(list(self.outside.iterdir()), [])

    def test_symlinked_file_escaping_vault_rejected(self):
        target = self.outside / "target.md"
        target.write_text("original", encoding="utf-8")
        (self.vault / "wiki" / "entities" / "link.md").symlink_to(target)
        with self.assertRaises(OSError):
            write_file(self.vault, "wiki/entities/link.md", "evil")
        self.assertEqual(target.read_text(encoding="utf-8"), "original")

    def test_symlink_within_vault_allowed(self):
        # Symlink interni alla vault (pattern vault-test) restano leciti.
        (self.vault / "shared").mkdir()
        (self.vault / "wiki" / "alias").symlink_to(self.vault / "shared")
        write_file(self.vault, "wiki/alias/ok.md", "content")
        self.assertEqual(
            (self.vault / "shared" / "ok.md").read_text(encoding="utf-8"),
            "content",
        )


if __name__ == "__main__":
    unittest.main()
