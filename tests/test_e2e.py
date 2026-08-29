"""
tests/test_e2e.py — End-to-end tests running the CLI against the project itself.
"""

import unittest
import io
import sys
import os
import json
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pyxray.cli import main

class TestE2E(unittest.TestCase):

    def run_cli(self, *args):
        """Run the CLI with the given arguments and return the JSON output."""
        held_stdout = io.StringIO()
        with patch('sys.stdout', held_stdout):
            exit_code = main(["--json", "--quiet", "--root", "."] + list(args))
            
        self.assertEqual(exit_code, 0, f"Command {args} failed with exit code {exit_code}")
        
        output = held_stdout.getvalue()
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            self.fail(f"Command {args} did not output valid JSON: {output}")

    def test_e2e_summary(self):
        data = self.run_cli("summary")
        self.assertIn("project", data)
        self.assertIn("total_packages", data)

    def test_e2e_tree(self):
        data = self.run_cli("tree")
        self.assertIn("project", data)
        self.assertIn("trees", data)

    def test_e2e_why(self):
        data = self.run_cli("why", "zero-dependency")
        self.assertIn("package", data)
        self.assertIn("paths", data)

    def test_e2e_impact(self):
        data = self.run_cli("impact", "zero-dependency")
        self.assertIn("package", data)
        self.assertIn("affected", data)

    def test_e2e_duplicates(self):
        data = self.run_cli("duplicates")
        self.assertIn("duplicates", data)

    def test_e2e_cycles(self):
        data = self.run_cli("cycles")
        self.assertIn("cycles", data)

    def test_e2e_stats(self):
        data = self.run_cli("stats")
        self.assertIn("stats", data)
        self.assertIn("project", data)

    def test_e2e_hotspots(self):
        data = self.run_cli("hotspots")
        self.assertIn("hotspots", data)

    def test_e2e_longest_chain(self):
        data = self.run_cli("longest-chain")
        self.assertIn("longest_chain", data)
        self.assertIn("length", data)

    def test_e2e_imports(self):
        data = self.run_cli("imports")
        self.assertIn("total_imports", data)
        self.assertIn("source_roots", data)

    def test_e2e_audit(self):
        data = self.run_cli("audit")
        self.assertIn("declared_count", data)
        self.assertIn("potentially_unused", data)

    def test_e2e_prune(self):
        data = self.run_cli("prune")
        self.assertIn("candidates", data)

if __name__ == "__main__":
    unittest.main()
