"""
tests/test_models.py — Tests for normalization and core model behaviour.

Uses only: unittest (stdlib)
"""

import os
import sys
import unittest

# Ensure pyxray is importable from the project root
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pyxray.models import DependencyGraph, Package, normalize_name


class TestNormalizeName(unittest.TestCase):

    def test_lowercase(self):
        self.assertEqual(normalize_name("Requests"), "requests")

    def test_hyphen_collapse(self):
        self.assertEqual(normalize_name("my_package"), "my-package")
        self.assertEqual(normalize_name("my.package"), "my-package")
        self.assertEqual(normalize_name("my-package"), "my-package")

    def test_mixed_separators(self):
        self.assertEqual(normalize_name("My_Package.Name"), "my-package-name")
        self.assertEqual(normalize_name("My---Package"), "my-package")

    def test_already_normalized(self):
        self.assertEqual(normalize_name("typing-extensions"), "typing-extensions")

    def test_beautifulsoup4(self):
        # Distribution: beautifulsoup4 → bs4 import (handled by metadata, not normalization)
        self.assertEqual(normalize_name("beautifulsoup4"), "beautifulsoup4")


class TestDependencyGraph(unittest.TestCase):

    def _make_pkg(self, name: str, version: str = "1.0") -> Package:
        from pyxray.models import normalize_name
        return Package(
            name=name,
            normalized_name=normalize_name(name),
            version=version,
        )

    def test_add_package(self):
        g = DependencyGraph()
        pkg = self._make_pkg("requests")
        g.add_package(pkg)
        self.assertIn("requests", g.packages)

    def test_add_edge(self):
        g = DependencyGraph()
        a = self._make_pkg("a")
        b = self._make_pkg("b")
        g.add_package(a)
        g.add_package(b)
        g.add_edge("a", "b")

        self.assertIn("b", g.dependencies_of("a"))
        self.assertIn("a", g.dependents_of("b"))

    def test_edge_count(self):
        g = DependencyGraph()
        for name in ["a", "b", "c"]:
            g.add_package(self._make_pkg(name))
        g.add_edge("a", "b")
        g.add_edge("a", "c")
        g.add_edge("b", "c")
        self.assertEqual(g.edge_count(), 3)

    def test_all_nodes(self):
        g = DependencyGraph()
        for name in ["x", "y", "z"]:
            g.add_package(self._make_pkg(name))
        self.assertEqual(g.all_nodes(), {"x", "y", "z"})


if __name__ == "__main__":
    unittest.main()
