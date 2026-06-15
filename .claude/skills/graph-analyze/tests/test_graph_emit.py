"""Test per _graph_emit.py — contratto dati graph.json."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import _graph_emit as ge  # noqa: E402
import _graph_metrics as gm  # noqa: E402


def build_vault(tmp: str):
    """Crea una vault con due triangoli (tipi diversi) + un ponte, e ritorna
    (vault_root, nodes, edge_counts)."""
    root = Path(tmp)
    layout = {
        "a": ("entities", "Alpha"), "b": ("entities", "Beta"), "c": ("concepts", "Gamma"),
        "d": ("concepts", "Delta"), "e": ("sources", "Epsilon"), "f": ("sources", None),
        "index": (".", None),
    }
    nodes = {}
    for stem, (folder, title) in layout.items():
        d = root / "wiki" / folder if folder != "." else root / "wiki"
        d.mkdir(parents=True, exist_ok=True)
        fm = "---\ntype: source\n" + (f'title: "{title}"\n' if title else "") + "---\n\nBody.\n"
        p = d / f"{stem}.md"
        p.write_text(fm, encoding="utf-8")
        nodes[stem] = p
    edges = [("a", "b"), ("b", "c"), ("a", "c"),
             ("d", "e"), ("e", "f"), ("d", "f"),
             ("c", "d"), ("index", "a"), ("index", "d")]
    edge_counts = {}
    for s, t in edges:
        edge_counts[(s, t)] = edge_counts.get((s, t), 0) + 1
    return root, nodes, edge_counts


class TestTypeAndMeta(unittest.TestCase):
    def test_infer_type_from_folder(self):
        self.assertEqual(ge.infer_type(Path("/v/wiki/entities/x.md"), None), "entity")
        self.assertEqual(ge.infer_type(Path("/v/wiki/concepts/x.md"), None), "concept")
        self.assertEqual(ge.infer_type(Path("/v/wiki/sources/x.md"), None), "source")

    def test_infer_type_fallback_frontmatter(self):
        self.assertEqual(ge.infer_type(Path("/v/wiki/x.md"), "synthesis"), "synthesis")
        self.assertEqual(ge.infer_type(Path("/v/wiki/x.md"), None), "unknown")

    def test_read_meta(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "x.md"
            p.write_text('---\ntype: entity\ntitle: "Hello: World"\n---\n\nBody\n', encoding="utf-8")
            self.assertEqual(ge.read_meta(p), ("entity", "Hello: World"))

    def test_read_meta_no_frontmatter(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "x.md"
            p.write_text("# Solo body\n", encoding="utf-8")
            self.assertEqual(ge.read_meta(p), (None, None))


class TestClusterLayout(unittest.TestCase):
    def test_positions_for_all_nodes_deterministic(self):
        members = {0: ["a", "b", "c"], 1: ["d", "e"]}
        p1 = ge.cluster_layout(members)
        p2 = ge.cluster_layout(members)
        self.assertEqual(set(p1.keys()), {"a", "b", "c", "d", "e"})
        self.assertEqual(p1, p2)  # deterministico

    def test_empty(self):
        self.assertEqual(ge.cluster_layout({}), {})


class TestBuildGraphJson(unittest.TestCase):
    def _data(self, tmp):
        root, nodes, ec = build_vault(tmp)
        enriched = gm.enrich(nodes, ec, exclude_auto=ge.STRUCTURAL)
        return ge.build_graph_json(nodes, ec, enriched, vault_root=root), root

    def test_meta_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, _ = self._data(tmp)
            self.assertEqual(data["meta"]["nodes"], 7)
            self.assertEqual(data["meta"]["nodes"], len(data["nodes"]))
            self.assertEqual(data["meta"]["edges"], len(data["edges"]))

    def test_node_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, _ = self._data(tmp)
            node = next(n for n in data["nodes"] if n["id"] == "a")
            for key in ("id", "label", "type", "structural", "path", "linkCount",
                        "community", "pagerank", "betweenness", "x", "y"):
                self.assertIn(key, node)
            self.assertEqual(node["label"], "Alpha")        # da title
            self.assertEqual(node["type"], "entity")        # da cartella
            self.assertFalse(node["structural"])
            self.assertEqual(node["path"], "wiki/entities/a.md")

    def test_label_fallback_to_stem(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, _ = self._data(tmp)
            node = next(n for n in data["nodes"] if n["id"] == "f")  # senza title
            self.assertEqual(node["label"], "f")

    def test_structural_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, _ = self._data(tmp)
            idx = next(n for n in data["nodes"] if n["id"] == "index")
            self.assertTrue(idx["structural"])

    def test_edges_undirected_unique_sorted(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, _ = self._data(tmp)
            pairs = [(e["source"], e["target"]) for e in data["edges"]]
            self.assertEqual(pairs, sorted(pairs))             # ordinati
            self.assertEqual(len(pairs), len(set(pairs)))      # unici
            for s, t in pairs:
                self.assertLess(s, t)                          # non orientati (a<b)

    def test_communities_and_insights_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, _ = self._data(tmp)
            self.assertGreaterEqual(len(data["communities"]), 1)
            self.assertIn("bridges", data["insights"])
            self.assertIn("suggested", data["insights"])
            self.assertIn("isolated", data["insights"])


if __name__ == "__main__":
    unittest.main()
