"""Test per _graph_metrics.py — grafi-giocattolo a risultato noto.

Eseguire dalla cartella tests:  python3 -m unittest discover -q
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import _graph_metrics as gm  # noqa: E402


def make(stems, directed_edges):
    """Costruisce (nodes, edge_counts) da una lista di stem e archi orientati."""
    nodes = {s: Path(f"/wiki/{s}.md") for s in stems}
    edge_counts = {}
    for src, tgt in directed_edges:
        edge_counts[(src, tgt)] = edge_counts.get((src, tgt), 0) + 1
    return nodes, edge_counts


# Due triangoli uniti da un ponte c-d
TWO_TRIANGLES = (
    ["a", "b", "c", "d", "e", "f"],
    [("a", "b"), ("b", "c"), ("a", "c"),
     ("d", "e"), ("e", "f"), ("d", "f"),
     ("c", "d")],
)


class TestBuildGraph(unittest.TestCase):
    def test_internal_edges_only_no_selfloops(self):
        nodes, ec = make(["a", "b"], [("a", "b"), ("a", "a"), ("a", "ghost")])
        g = gm.build_graph(nodes, ec)
        self.assertEqual(g["directed"]["a"], {"b": 1})        # self-loop e ghost esclusi
        self.assertEqual(g["undirected"]["a"], {"b": 1})
        self.assertEqual(g["undirected"]["b"], {"a": 1})


class TestComponents(unittest.TestCase):
    def test_single_component(self):
        nodes, ec = make(*TWO_TRIANGLES)
        comps = gm.connected_components(gm.build_graph(nodes, ec)["undirected"])
        self.assertEqual(len(comps), 1)
        self.assertEqual(len(comps[0]), 6)

    def test_two_islands(self):
        nodes, ec = make(["a", "b", "c", "d"], [("a", "b"), ("c", "d")])
        comps = gm.connected_components(gm.build_graph(nodes, ec)["undirected"])
        self.assertEqual(len(comps), 2)
        self.assertEqual(sorted(len(c) for c in comps), [2, 2])

    def test_isolated_node_is_singleton(self):
        nodes, ec = make(["a", "b", "x"], [("a", "b")])
        comps = gm.connected_components(gm.build_graph(nodes, ec)["undirected"])
        self.assertIn({"x"}, comps)


class TestCommunities(unittest.TestCase):
    def test_two_triangles_two_communities(self):
        nodes, ec = make(*TWO_TRIANGLES)
        und = gm.build_graph(nodes, ec)["undirected"]
        comm = gm.louvain_communities(und)
        # a,b,c stessa community; d,e,f stessa community; le due differiscono
        self.assertEqual(comm["a"], comm["b"])
        self.assertEqual(comm["b"], comm["c"])
        self.assertEqual(comm["d"], comm["e"])
        self.assertEqual(comm["e"], comm["f"])
        self.assertNotEqual(comm["a"], comm["d"])

    def test_modularity_positive(self):
        nodes, ec = make(*TWO_TRIANGLES)
        und = gm.build_graph(nodes, ec)["undirected"]
        comm = gm.louvain_communities(und)
        self.assertGreater(gm.modularity(und, comm), 0.0)

    def test_largest_community_is_id_zero(self):
        # tre nodi fittamente connessi + un pendant collegato a uno solo
        nodes, ec = make(
            ["a", "b", "c", "x", "y", "z", "p"],
            [("a", "b"), ("b", "c"), ("a", "c"),
             ("x", "y"), ("y", "z"), ("x", "z"),
             ("a", "x"), ("p", "a")],
        )
        und = gm.build_graph(nodes, ec)["undirected"]
        comm = gm.louvain_communities(und)
        sizes = {}
        for cid in comm.values():
            sizes[cid] = sizes.get(cid, 0) + 1
        self.assertEqual(max(sizes, key=sizes.get), 0)  # id 0 = più grande


class TestPageRank(unittest.TestCase):
    def test_hub_has_highest_rank(self):
        nodes, ec = make(["hub", "b", "c", "d"],
                         [("b", "hub"), ("c", "hub"), ("d", "hub")])
        pr = gm.pagerank(gm.build_graph(nodes, ec)["directed"])
        self.assertEqual(max(pr, key=pr.get), "hub")

    def test_ranks_sum_to_one(self):
        nodes, ec = make(*TWO_TRIANGLES)
        pr = gm.pagerank(gm.build_graph(nodes, ec)["directed"])
        self.assertAlmostEqual(sum(pr.values()), 1.0, places=6)


class TestBetweenness(unittest.TestCase):
    def test_bridge_nodes_highest(self):
        nodes, ec = make(*TWO_TRIANGLES)
        und = gm.build_graph(nodes, ec)["undirected"]
        btw = gm.betweenness(und)
        # c e d (estremi del ponte) devono superare i nodi periferici
        self.assertGreater(btw["c"], btw["a"])
        self.assertGreater(btw["d"], btw["f"])


class TestSuggestLinks(unittest.TestCase):
    def test_common_neighbors_suggested(self):
        # a e b puntano entrambi a c e d, ma non sono collegate fra loro
        nodes, ec = make(["a", "b", "c", "d"],
                         [("a", "c"), ("a", "d"), ("b", "c"), ("b", "d")])
        und = gm.build_graph(nodes, ec)["undirected"]
        sugg = gm.suggest_links(und, min_common=2)
        pairs = {(s["a"], s["b"]) for s in sugg}
        self.assertIn(("a", "b"), pairs)

    def test_already_linked_not_suggested(self):
        nodes, ec = make(["a", "b", "c", "d"],
                         [("a", "c"), ("a", "d"), ("b", "c"), ("b", "d"), ("a", "b")])
        und = gm.build_graph(nodes, ec)["undirected"]
        sugg = gm.suggest_links(und, min_common=2)
        pairs = {(s["a"], s["b"]) for s in sugg}
        self.assertNotIn(("a", "b"), pairs)

    def test_auto_pages_excluded(self):
        nodes, ec = make(["index", "a", "b", "c", "d"],
                         [("index", "c"), ("index", "d"), ("a", "c"), ("a", "d")])
        und = gm.build_graph(nodes, ec)["undirected"]
        sugg = gm.suggest_links(und, min_common=2)
        involved = {s["a"] for s in sugg} | {s["b"] for s in sugg}
        self.assertNotIn("index", involved)


if __name__ == "__main__":
    unittest.main()
