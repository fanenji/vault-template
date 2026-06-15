"""Test per i renderer _graph_html.py e _graph_canvas.py (consumano graph.json)."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import _graph_html as gh  # noqa: E402
import _graph_canvas as gc  # noqa: E402


def sample():
    return {
        "meta": {"vault": "v", "nodes": 4, "edges": 2, "modularity": 0.3, "generated": "2026-06-15"},
        "nodes": [
            {"id": "duckdb", "label": "DuckDB", "type": "entity", "structural": False,
             "path": "wiki/entities/DuckDB.md", "linkCount": 3, "community": 0,
             "pagerank": 0.2, "betweenness": 1.0, "x": 10.0, "y": 20.0},
            {"id": "parquet", "label": "Parquet", "type": "concept", "structural": False,
             "path": "wiki/concepts/parquet.md", "linkCount": 2, "community": 0,
             "pagerank": 0.1, "betweenness": 0.0, "x": 30.0, "y": 40.0},
            {"id": "iceberg", "label": "Iceberg", "type": "concept", "structural": False,
             "path": "wiki/concepts/iceberg.md", "linkCount": 2, "community": 1,
             "pagerank": 0.1, "betweenness": 0.0, "x": -50.0, "y": -60.0},
            {"id": "index", "label": "index", "type": "unknown", "structural": True,
             "path": "wiki/index.md", "linkCount": 5, "community": 0,
             "pagerank": 0.3, "betweenness": 2.0, "x": 0.0, "y": 0.0},
        ],
        "edges": [
            {"source": "duckdb", "target": "parquet", "weight": 2},
            {"source": "duckdb", "target": "index", "weight": 1},
        ],
        "communities": [
            {"id": 0, "size": 3, "topNodes": ["DuckDB", "Parquet"]},
            {"id": 1, "size": 1, "topNodes": ["Iceberg"]},
        ],
        "insights": {"bridges": [], "suggested": [], "isolated": []},
    }


class TestHtml(unittest.TestCase):
    def test_self_contained_structure(self):
        html = gh.render_html(sample())
        self.assertIn("<canvas", html)
        self.assertIn('id="graph-data"', html)
        self.assertIn("DuckDB", html)            # dati embeddati
        self.assertNotIn("http://", html.split("graph-data")[0])  # niente CDN nell'head
        self.assertNotIn("https://", html)       # nessuna risorsa remota

    def test_filter_controls_present(self):
        html = gh.render_html(sample())
        for needle in ("Nascondi strutturali", "Nascondi isolati", "Max link", "Tipi", "Reset"):
            self.assertIn(needle, html)

    def test_palette_injected(self):
        html = gh.render_html(sample())
        self.assertIn(gh.TYPE_COLORS["entity"], html)
        self.assertIn("COMMUNITY_COLORS", html)

    def test_script_close_escaped(self):
        data = sample()
        data["nodes"][0]["label"] = "evil</script>x"
        html = gh.render_html(data)
        self.assertIn("evil<\\/script>x", html)   # escaped
        # l'unico </script> reale è quello di chiusura del blocco <script>
        self.assertEqual(html.count("evil</script>"), 0)


class TestCanvas(unittest.TestCase):
    def test_returns_nodes_and_edges(self):
        cv = gc.build_canvas(sample())
        self.assertIn("nodes", cv)
        self.assertIn("edges", cv)
        json.dumps(cv)  # serializzabile

    def test_structural_hidden_by_default(self):
        cv = gc.build_canvas(sample())
        ids = {n["id"] for n in cv["nodes"]}
        self.assertNotIn("index", ids)            # strutturale nascosto

    def test_structural_shown_when_disabled(self):
        cv = gc.build_canvas(sample(), hide_structural=False)
        ids = {n["id"] for n in cv["nodes"]}
        self.assertIn("index", ids)

    def test_text_nodes_have_wikilink_and_color(self):
        cv = gc.build_canvas(sample())
        text_nodes = {n["id"]: n for n in cv["nodes"] if n["type"] == "text"}
        self.assertEqual(text_nodes["duckdb"]["text"], "[[DuckDB]]")          # label == basename
        self.assertEqual(text_nodes["parquet"]["text"], "[[parquet|Parquet]]")  # alias
        self.assertTrue(text_nodes["duckdb"]["color"].startswith("#"))

    def test_group_per_community_with_members(self):
        cv = gc.build_canvas(sample())
        groups = [n for n in cv["nodes"] if n["type"] == "group"]
        gids = {g["id"] for g in groups}
        self.assertIn("grp-0", gids)              # community 0: duckdb+parquet → riquadro
        self.assertNotIn("grp-1", gids)           # community 1: solo iceberg → niente riquadro

    def test_edges_only_between_visible(self):
        cv = gc.build_canvas(sample())
        ids = {n["id"] for n in cv["nodes"] if n["type"] == "text"}
        pairs = [(e["fromNode"], e["toNode"]) for e in cv["edges"]]
        self.assertIn(("duckdb", "parquet"), pairs)
        for a, b in pairs:
            self.assertIn(a, ids); self.assertIn(b, ids)  # index escluso → niente arco verso index


if __name__ == "__main__":
    unittest.main()
