"""Test per lint.py — check strutturali, schema, soppressione, storico."""

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import lint


def page(page_type: str, title: str, body: str = "", extra_fm: str = "") -> str:
    return (
        f"---\ntype: {page_type}\ntitle: {title}\ncreated: 2026-01-01\n{extra_fm}---\n\n{body}\n"
    )


class LintVaultTestCase(unittest.TestCase):
    """Base: vault temporanea con struttura minima."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.vault = Path(self._tmp.name)
        (self.vault / ".llm-wiki").mkdir()
        for sub in ("entities", "concepts", "sources", "queries", "synthesis"):
            (self.vault / "wiki" / sub).mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, rel: str, content: str):
        p = self.vault / "wiki" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    def run_checks(self, *fns):
        pages = lint.load_pages(self.vault / "wiki")
        slug_map = lint.build_slug_map(pages, self.vault / "wiki")
        results = []
        for fn in fns:
            if fn is lint.check_structural:
                results.extend(fn(pages, slug_map, self.vault / "wiki"))
            elif fn is lint.check_duplicate_slugs:
                results.extend(fn(pages))
            elif fn is lint.check_frontmatter:
                results.extend(fn(pages))
            elif fn is lint.check_schema_rules:
                results.extend(fn(pages, slug_map, self.vault))
        return pages, results

    def types(self, results):
        return [r.type for r in results]


class TestStructuralFixes(LintVaultTestCase):
    def test_link_to_overview_not_broken(self):
        self.write("entities/a.md", page("entity", "A", "Vedi [[overview]] e [[index]]."))
        _, results = self.run_checks(lint.check_structural)
        self.assertNotIn("broken-link", self.types(results))

    def test_overview_not_linted_and_grants_no_inbound(self):
        # b è linkata SOLO da overview.md → deve risultare orphan
        self.write("overview.md", "---\ntype: overview\n---\nVedi [[b]].")
        self.write("entities/b.md", page("entity", "B", "Body."))
        _, results = self.run_checks(lint.check_structural)
        orphans = [r.page for r in results if r.type == "orphan"]
        self.assertIn("entities/b.md", orphans)
        self.assertNotIn("overview.md", orphans)

    def test_self_link_does_not_mask_orphan(self):
        self.write("entities/a.md", page("entity", "A", "Io sono [[a]]."))
        _, results = self.run_checks(lint.check_structural)
        self.assertIn("entities/a.md", [r.page for r in results if r.type == "orphan"])

    def test_inbound_link_clears_orphan(self):
        self.write("entities/a.md", page("entity", "A", "Vedi [[b]]."))
        self.write("entities/b.md", page("entity", "B", "Vedi [[a]]."))
        _, results = self.run_checks(lint.check_structural)
        self.assertEqual([r for r in results if r.type == "orphan"], [])

    def test_broken_link_detected(self):
        self.write("entities/a.md", page("entity", "A", "Vedi [[inesistente]]."))
        _, results = self.run_checks(lint.check_structural)
        broken = [r for r in results if r.type == "broken-link"]
        self.assertEqual(len(broken), 1)
        self.assertEqual(broken[0].affected_pages, ["inesistente"])


class TestSchemaChecks(LintVaultTestCase):
    def test_duplicate_slug_cross_folder(self):
        self.write("entities/anthropic.md", page("entity", "Anthropic", "[[claude]]"))
        self.write("concepts/anthropic.md", page("concept", "Anthropic", "[[claude]]"))
        _, results = self.run_checks(lint.check_duplicate_slugs)
        dups = [r for r in results if r.type == "duplicate-slug"]
        self.assertEqual(len(dups), 1)
        self.assertEqual(sorted(dups[0].affected_pages),
                         ["concepts/anthropic.md", "entities/anthropic.md"])

    def test_related_broken_detected(self):
        self.write("entities/a.md", page("entity", "A", "Body.",
                                         extra_fm="related: [esiste, non-esiste]\n"))
        self.write("entities/esiste.md", page("entity", "Esiste", "Body."))
        _, results = self.run_checks(lint.check_schema_rules)
        refs = [r for r in results if r.type == "frontmatter-ref"]
        self.assertEqual(len(refs), 1)
        self.assertIn("non-esiste", refs[0].detail)

    def test_source_path_missing_on_disk(self):
        self.write("sources/doc.md", page("source", "Doc", "Body.",
                                          extra_fm="source_path: raw/sources/sparito.pdf\n"))
        _, results = self.run_checks(lint.check_schema_rules)
        self.assertTrue(any(r.type == "frontmatter-ref" and "sparito.pdf" in r.detail
                            for r in results))

    def test_raw_source_not_ingested(self):
        raw = self.vault / "raw" / "sources"
        raw.mkdir(parents=True)
        (raw / "mai-ingerito.pdf").write_bytes(b"pdf")
        (raw / "ingerito.pdf").write_bytes(b"pdf")
        self.write("sources/ingerito.md", page("source", "Ingerito", "Body.",
                                               extra_fm="source_path: raw/sources/ingerito.pdf\n"))
        _, results = self.run_checks(lint.check_schema_rules)
        ni = [r for r in results if r.type == "not-ingested"]
        self.assertEqual(len(ni), 1)
        self.assertIn("mai-ingerito.pdf", ni[0].page)

    def test_type_folder_mismatch(self):
        self.write("concepts/fuori-posto.md", page("entity", "Fuori Posto", "Body."))
        _, results = self.run_checks(lint.check_schema_rules)
        self.assertTrue(any(r.type == "type-folder" for r in results))

    def test_naming_non_kebab(self):
        self.write("entities/Foo Bar.md", page("entity", "Foo Bar", "Body."))
        _, results = self.run_checks(lint.check_schema_rules)
        self.assertTrue(any(r.type == "naming" for r in results))

    def test_bad_date_format(self):
        self.write("entities/a.md",
                   "---\ntype: entity\ntitle: A\ncreated: 10/06/2026\n---\nBody.\n")
        _, results = self.run_checks(lint.check_frontmatter)
        self.assertTrue(any("YYYY-MM-DD" in r.detail for r in results))


class TestLintIgnore(LintVaultTestCase):
    def test_lint_ignore_suppresses_type_for_page(self):
        self.write("queries/q.md", page("query", "Q", "Risposta senza link.",
                                        extra_fm="lint_ignore: [orphan, no-outlinks]\n"))
        pages, results = self.run_checks(lint.check_structural)
        filtered, suppressed = lint.apply_lint_ignore(results, pages)
        self.assertEqual(suppressed, 2)
        self.assertEqual([r for r in filtered if r.page == "queries/q.md"], [])

    def test_other_pages_unaffected(self):
        self.write("queries/q.md", page("query", "Q", "Body.",
                                        extra_fm="lint_ignore: [orphan]\n"))
        self.write("entities/a.md", page("entity", "A", "Body senza outlink."))
        pages, results = self.run_checks(lint.check_structural)
        filtered, _ = lint.apply_lint_ignore(results, pages)
        self.assertTrue(any(r.page == "entities/a.md" and r.type == "orphan"
                            for r in filtered))


class TestPendingCheck(LintVaultTestCase):
    def test_old_pending_merge_is_warning(self):
        old = time.time() - 10 * 86400
        (self.vault / ".llm-wiki" / "pending-merges.json").write_text(json.dumps([
            {"id": "merge-x", "page": "wiki/entities/a.md", "status": "pending",
             "created_at": old},
            {"id": "merge-y", "page": "wiki/entities/b.md", "status": "resolved",
             "created_at": old},
        ]), encoding="utf-8")
        results = lint.check_pending(self.vault, max_age_days=7)
        warnings = [r for r in results if r.severity == "warning"]
        self.assertEqual(len(warnings), 1)
        self.assertIn("merge-x", warnings[0].detail)

    def test_fresh_pending_only_info(self):
        (self.vault / ".llm-wiki" / "pending-merges.json").write_text(json.dumps([
            {"id": "merge-x", "page": "wiki/a.md", "status": "pending",
             "created_at": time.time()},
        ]), encoding="utf-8")
        results = lint.check_pending(self.vault, max_age_days=7)
        self.assertEqual([r.severity for r in results], ["info"])

    def test_no_queues_no_results(self):
        self.assertEqual(lint.check_pending(self.vault), [])


class TestIncrementalFilter(LintVaultTestCase):
    def test_filter_to_pages(self):
        self.write("entities/a.md", page("entity", "A", "Vedi [[rotto-a]]."))
        self.write("entities/b.md", page("entity", "B", "Vedi [[rotto-b]]."))
        _, results = self.run_checks(lint.check_structural)
        filtered = lint.filter_to_pages(results, ["wiki/entities/a.md"])
        self.assertTrue(all("a" in r.page or "rotto-a" in str(r.affected_pages)
                            for r in filtered))
        self.assertFalse(any(r.page == "entities/b.md" for r in filtered))

    def test_same_stem_other_folder_not_attracted(self):
        # Le issue di concepts/x.md non devono entrare nel lint incrementale
        # di entities/x.md (stesso stem, pagina diversa)...
        self.write("entities/x.md", page("entity", "X", "Body. [[y]]"))
        self.write("entities/y.md", page("entity", "Y", "[[x]]"))
        self.write("concepts/x.md", page("concept", "X concept", "Orfana senza inbound."))
        _, results = self.run_checks(lint.check_structural, lint.check_duplicate_slugs)
        filtered = lint.filter_to_pages(results, ["wiki/entities/x.md"])
        self.assertFalse(any(r.type == "orphan" and r.page == "concepts/x.md"
                             for r in filtered))
        # ...ma il duplicate-slug che la coinvolge sì (affected_pages la cita)
        self.assertTrue(any(r.type == "duplicate-slug" for r in filtered))


class TestHistoryDiff(LintVaultTestCase):
    def _result(self, page="entities/a.md", type_="orphan"):
        return lint.LintResult(type=type_, severity="info", page=page, detail="x")

    def test_first_run_all_new(self):
        results = [self._result()]
        diff = lint.diff_results(results, None)
        self.assertEqual(len(diff["new"]), 1)
        self.assertEqual(results[0].status, "new")

    def test_second_run_diff(self):
        first = [self._result("entities/a.md"), self._result("entities/b.md")]
        lint.diff_results(first, None)
        lint.save_run(self.vault, first, total_pages=2)
        previous = lint.load_previous_run(self.vault)
        self.assertIsNotNone(previous)

        # a persiste, b risolta, c nuova
        second = [self._result("entities/a.md"), self._result("entities/c.md")]
        diff = lint.diff_results(second, previous)
        self.assertEqual([r.page for r in diff["new"]], ["entities/c.md"])
        self.assertEqual([i["page"] for i in diff["resolved"]], ["entities/b.md"])
        self.assertEqual(second[0].status, "persistent")
        self.assertEqual(second[1].status, "new")

    def test_build_summary(self):
        first = [self._result("entities/a.md")]
        lint.save_run(self.vault, first, 1)
        second = [
            lint.LintResult(type="broken-link", severity="warning",
                            page="entities/c.md", detail="x"),
            self._result("entities/a.md"),
        ]
        diff = lint.diff_results(second, lint.load_previous_run(self.vault))
        s = lint.build_summary(second, total_pages=2, diff=diff)
        self.assertEqual(s["warnings"], 1)
        self.assertEqual(s["info"], 1)
        self.assertEqual(s["new"], 1)
        self.assertEqual(s["new_warnings"], 1)
        self.assertEqual(s["resolved"], 0)

    def test_build_summary_without_history(self):
        s = lint.build_summary([self._result()], total_pages=1, diff=None)
        self.assertIsNone(s["new"])
        self.assertEqual(s["info"], 1)

    def test_report_renders_diff_sections(self):
        first = [self._result("entities/a.md")]
        lint.save_run(self.vault, first, 1)
        second = [self._result("entities/c.md")]
        diff = lint.diff_results(second, lint.load_previous_run(self.vault))
        report = lint.render_markdown(second, total_pages=1, diff=diff)
        self.assertIn("Nuove dal run precedente", report)
        self.assertIn("Risolte", report)
        self.assertIn("entities/c.md", report)


if __name__ == "__main__":
    unittest.main()
