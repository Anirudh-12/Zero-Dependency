"""
tests/test_graph.py — Tests for graph construction and analysis algorithms.

Uses only: unittest (stdlib)
Uses synthetic Package objects — does NOT require any real installed packages.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pyxray.analysis import (
    compute_depths,
    compute_stats,
    find_cycles,
    find_longest_chain,
    find_paths,
    reachable_from,
    reachable_reverse,
)
from pyxray.graph import build_graph
from pyxray.models import DependencyGraph, Package, Project, normalize_name
from pyxray.requirements import parse_requirement

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_pkg(name: str, version: str = "1.0", deps: list[str] | None = None) -> Package:
    """Helper to create a Package with mocked dependencies."""
    p = Package(
        name=name,
        normalized_name=normalize_name(name),
        version=version,
        raw_requires=deps or [],
    )
    return p


def make_graph(*pkgs: Package, roots: list[str] | None = None) -> DependencyGraph:
    """Build a DependencyGraph from Package objects."""
    g = DependencyGraph()
    for p in pkgs:
        g.add_package(p)

    for p in pkgs:
        for req in p.requires:
            if req.name:
                g.add_edge(p.normalized_name, req.normalized_name)

    if roots:
        g.roots = set(roots)

    return g


# ---------------------------------------------------------------------------
# Graph construction via build_graph
# ---------------------------------------------------------------------------


class TestBuildGraph(unittest.TestCase):
    def test_simple_chain(self):
        """A → B → C"""
        pkgs = {
            "a": make_pkg("a", deps=["b"]),
            "b": make_pkg("b", deps=["c"]),
            "c": make_pkg("c"),
        }
        project = Project(
            name="test",
            root="/tmp/test",
            declared=[parse_requirement("a")],
        )
        graph, _ = build_graph(project, pkgs)

        self.assertIn("a", graph.packages)
        self.assertIn("b", graph.packages)
        self.assertIn("c", graph.packages)
        self.assertIn("b", graph.forward["a"])
        self.assertIn("c", graph.forward["b"])
        self.assertIn("a", graph.roots)

    def test_missing_package(self):
        """Declared dep not in installed → shows in graph.missing."""
        pkgs = {}
        project = Project(
            name="test",
            root="/tmp/test",
            declared=[parse_requirement("missing-pkg")],
        )
        graph, warnings = build_graph(project, pkgs)
        self.assertIn("missing-pkg", graph.missing)
        self.assertTrue(any("not installed" in w for w in warnings))

    def test_diamond_deduplication(self):
        """A → B, C; B → D; C → D — D visited only once."""
        pkgs = {
            "a": make_pkg("a", deps=["b", "c"]),
            "b": make_pkg("b", deps=["d"]),
            "c": make_pkg("c", deps=["d"]),
            "d": make_pkg("d"),
        }
        project = Project(
            name="test",
            root="/tmp/test",
            declared=[parse_requirement("a")],
        )
        graph, _ = build_graph(project, pkgs)

        self.assertEqual(len(graph.packages), 4)
        self.assertIn("d", graph.forward["b"])
        self.assertIn("d", graph.forward["c"])


# ---------------------------------------------------------------------------
# Reachability
# ---------------------------------------------------------------------------


class TestReachability(unittest.TestCase):
    def setUp(self):
        # A → B → C, D → C
        self.g = make_graph(
            make_pkg("a", deps=["b"]),
            make_pkg("b", deps=["c"]),
            make_pkg("c"),
            make_pkg("d", deps=["c"]),
            roots=["a", "d"],
        )

    def test_forward_reachable(self):
        r = reachable_from(self.g, "a")
        self.assertEqual(r, {"a", "b", "c"})

    def test_forward_leaf(self):
        r = reachable_from(self.g, "c")
        self.assertEqual(r, {"c"})

    def test_reverse_reachable(self):
        r = reachable_reverse(self.g, "c")
        self.assertIn("b", r)
        self.assertIn("a", r)
        self.assertIn("d", r)
        self.assertNotIn("c", r)  # start node excluded

    def test_reverse_root(self):
        r = reachable_reverse(self.g, "a")
        # Nothing points to a (it's a root)
        self.assertEqual(r, set())


# ---------------------------------------------------------------------------
# Cycle detection
# ---------------------------------------------------------------------------


class TestCycles(unittest.TestCase):
    def test_no_cycles(self):
        g = make_graph(
            make_pkg("a", deps=["b"]),
            make_pkg("b", deps=["c"]),
            make_pkg("c"),
        )
        self.assertEqual(find_cycles(g), [])

    def test_simple_cycle(self):
        # a → b → c → a
        g = DependencyGraph()
        for name in ["a", "b", "c"]:
            g.add_package(make_pkg(name))
        g.add_edge("a", "b")
        g.add_edge("b", "c")
        g.add_edge("c", "a")

        cycles = find_cycles(g)
        self.assertGreater(len(cycles), 0)

    def test_self_cycle(self):
        g = DependencyGraph()
        g.add_package(make_pkg("a"))
        g.add_edge("a", "a")
        cycles = find_cycles(g)
        self.assertGreater(len(cycles), 0)

    def test_diamond_no_cycle(self):
        g = make_graph(
            make_pkg("a", deps=["b", "c"]),
            make_pkg("b", deps=["d"]),
            make_pkg("c", deps=["d"]),
            make_pkg("d"),
        )
        self.assertEqual(find_cycles(g), [])


# ---------------------------------------------------------------------------
# Depth calculation
# ---------------------------------------------------------------------------


class TestDepths(unittest.TestCase):
    def test_chain_depths(self):
        """A(root) → B → C should give depths {a:0, b:1, c:2}."""
        pkgs = {
            "a": make_pkg("a", deps=["b"]),
            "b": make_pkg("b", deps=["c"]),
            "c": make_pkg("c"),
        }
        project = Project(name="t", root="/t", declared=[parse_requirement("a")])
        g, _ = build_graph(project, pkgs)

        depths = compute_depths(g)
        self.assertEqual(depths["a"], 0)
        self.assertEqual(depths["b"], 1)
        self.assertEqual(depths["c"], 2)

    def test_multiple_roots(self):
        """Two roots; shared dep gets min depth."""
        pkgs = {
            "a": make_pkg("a", deps=["c"]),
            "b": make_pkg("b", deps=["c"]),
            "c": make_pkg("c"),
        }
        project = Project(
            name="t",
            root="/t",
            declared=[parse_requirement("a"), parse_requirement("b")],
        )
        g, _ = build_graph(project, pkgs)
        depths = compute_depths(g)
        self.assertEqual(depths["c"], 1)


# ---------------------------------------------------------------------------
# Paths (why command)
# ---------------------------------------------------------------------------


class TestPaths(unittest.TestCase):
    def test_direct_path(self):
        g = make_graph(
            make_pkg("root", deps=["target"]),
            make_pkg("target"),
            roots=["root"],
        )
        paths = find_paths(g, "root", "target")
        self.assertEqual(paths, [["root", "target"]])

    def test_multi_hop_path(self):
        g = make_graph(
            make_pkg("a", deps=["b"]),
            make_pkg("b", deps=["c"]),
            make_pkg("c"),
            roots=["a"],
        )
        paths = find_paths(g, "a", "c")
        self.assertEqual(paths[0], ["a", "b", "c"])

    def test_no_path(self):
        g = make_graph(
            make_pkg("a"),
            make_pkg("b"),
            roots=["a"],
        )
        paths = find_paths(g, "a", "b")
        self.assertEqual(paths, [])


# ---------------------------------------------------------------------------
# Longest chain
# ---------------------------------------------------------------------------


class TestLongestChain(unittest.TestCase):
    def test_simple_chain(self):
        g = make_graph(
            make_pkg("a", deps=["b"]),
            make_pkg("b", deps=["c"]),
            make_pkg("c", deps=["d"]),
            make_pkg("d"),
            roots=["a"],
        )
        chain = find_longest_chain(g)
        self.assertEqual(chain, ["a", "b", "c", "d"])

    def test_with_cycle(self):
        g = DependencyGraph()
        for name in ["a", "b", "c"]:
            g.add_package(make_pkg(name))
        g.add_edge("a", "b")
        g.add_edge("b", "c")
        g.add_edge("c", "a")  # cycle
        g.roots = {"a"}

        # Should not hang; result is a finite chain
        chain = find_longest_chain(g)
        self.assertIsInstance(chain, list)
        self.assertGreater(len(chain), 0)


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


class TestStats(unittest.TestCase):
    def test_stats_keys(self):
        pkgs = {
            "a": make_pkg("a", deps=["b"]),
            "b": make_pkg("b", deps=["c"]),
            "c": make_pkg("c"),
        }
        project = Project(name="t", root="/t", declared=[parse_requirement("a")])
        g, _ = build_graph(project, pkgs)

        stats = compute_stats(g)
        expected_keys = {
            "direct_dependencies",
            "transitive_dependencies",
            "total_packages",
            "dependency_edges",
            "maximum_depth",
            "average_depth",
            "cycle_count",
        }
        for key in expected_keys:
            self.assertIn(key, stats)

    def test_direct_vs_transitive(self):
        pkgs = {
            "a": make_pkg("a", deps=["b"]),
            "b": make_pkg("b"),
        }
        project = Project(name="t", root="/t", declared=[parse_requirement("a")])
        g, _ = build_graph(project, pkgs)

        stats = compute_stats(g)
        self.assertEqual(stats["direct_dependencies"], 1)
        self.assertEqual(stats["transitive_dependencies"], 1)


if __name__ == "__main__":
    unittest.main()
