"""
tests/test_source.py — Tests for AST import extraction and classification.

Uses only: unittest, tempfile, textwrap (stdlib)
"""

import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pyxray.models import Package, SourceImport, normalize_name
from pyxray.source import (
    build_import_map,
    classify_imports,
    extract_imports_from_file,
)


def write_temp_py(content: str) -> Path:
    """Write content to a temporary .py file and return its path."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as f:
        f.write(textwrap.dedent(content))
        return Path(f.name)


class TestExtractImports(unittest.TestCase):
    def tearDown(self):
        # Cleanup temp files
        for attr in ("_tmp",):
            p = getattr(self, attr, None)
            if p and p.exists():
                p.unlink()

    def test_simple_import(self):
        self._tmp = write_temp_py("import requests\n")
        imports, err = extract_imports_from_file(self._tmp)
        self.assertIsNone(err)
        self.assertEqual(len(imports), 1)
        self.assertEqual(imports[0].module, "requests")
        self.assertFalse(imports[0].is_from)

    def test_from_import(self):
        self._tmp = write_temp_py("from os import path\n")
        imports, err = extract_imports_from_file(self._tmp)
        self.assertIsNone(err)
        self.assertEqual(len(imports), 1)
        self.assertEqual(imports[0].module, "os")
        self.assertTrue(imports[0].is_from)

    def test_dotted_import(self):
        self._tmp = write_temp_py("import os.path\n")
        imports, err = extract_imports_from_file(self._tmp)
        self.assertEqual(imports[0].module, "os")  # top-level only

    def test_multiple_imports(self):
        self._tmp = write_temp_py("import sys\nimport os\nfrom pathlib import Path\n")
        imports, _ = extract_imports_from_file(self._tmp)
        modules = {i.module for i in imports}
        self.assertIn("sys", modules)
        self.assertIn("os", modules)
        self.assertIn("pathlib", modules)

    def test_syntax_error(self):
        self._tmp = write_temp_py("def broken(:\n")
        imports, err = extract_imports_from_file(self._tmp)
        self.assertEqual(imports, [])
        self.assertIsNotNone(err)
        self.assertIn("syntax error", err.lower())

    def test_nested_import(self):
        """Imports inside functions should still be extracted."""
        self._tmp = write_temp_py("def foo():\n    import json\n")
        imports, _ = extract_imports_from_file(self._tmp)
        self.assertEqual(imports[0].module, "json")

    def test_relative_import_skipped(self):
        """Relative imports (from . import x) have level > 0 → skipped."""
        self._tmp = write_temp_py("from . import utils\n")
        imports, _ = extract_imports_from_file(self._tmp)
        self.assertEqual(imports, [])

    def test_line_number(self):
        self._tmp = write_temp_py("# comment\nimport requests\n")
        imports, _ = extract_imports_from_file(self._tmp)
        self.assertEqual(imports[0].line, 2)


class TestClassifyImports(unittest.TestCase):
    def _make_import(self, module: str) -> SourceImport:
        return SourceImport(module=module, file="test.py", line=1, col=0)

    def test_stdlib_classified(self):
        imp_map = {}
        imports = [self._make_import("os"), self._make_import("sys")]
        third, stdlib, unknown = classify_imports(imports, imp_map)
        self.assertIn("os", stdlib)
        self.assertIn("sys", stdlib)
        self.assertEqual(third, set())
        self.assertEqual(unknown, set())

    def test_third_party_classified(self):
        imp_map = {"requests": "requests"}
        imports = [self._make_import("requests")]
        third, stdlib, unknown = classify_imports(imports, imp_map)
        self.assertIn("requests", third)

    def test_unknown_classified(self):
        imp_map = {}
        imports = [self._make_import("totally_unknown_pkg")]
        third, stdlib, unknown = classify_imports(imports, imp_map)
        self.assertIn("totally_unknown_pkg", unknown)


class TestBuildImportMap(unittest.TestCase):
    def test_basic_mapping(self):
        pkg = Package(
            name="requests",
            normalized_name="requests",
            version="2.0",
        )
        pkg.top_level_names = ["requests"]
        imp_map = build_import_map({"requests": pkg})
        self.assertIn("requests", imp_map)
        self.assertEqual(imp_map["requests"], "requests")

    def test_hyphenated_name_fallback(self):
        """my-package should map to my_package import name."""
        pkg = Package(
            name="my-package",
            normalized_name="my-package",
            version="1.0",
        )
        pkg.top_level_names = []
        imp_map = build_import_map({"my-package": pkg})
        self.assertIn("my_package", imp_map)

    def test_top_level_overrides(self):
        """top_level.txt content (e.g. bs4 for beautifulsoup4) takes priority."""
        pkg = Package(
            name="beautifulsoup4",
            normalized_name="beautifulsoup4",
            version="4.12.0",
        )
        pkg.top_level_names = ["bs4"]
        imp_map = build_import_map({"beautifulsoup4": pkg})
        self.assertIn("bs4", imp_map)
        self.assertEqual(imp_map["bs4"], "beautifulsoup4")


if __name__ == "__main__":
    unittest.main()
