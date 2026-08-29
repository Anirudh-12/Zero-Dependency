"""
tests/test_requirements.py — Tests for the PEP 508 requirement parser.

Uses only: unittest (stdlib)
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pyxray.requirements import parse_requirement, evaluate_marker


class TestParseRequirement(unittest.TestCase):

    def test_simple_name(self):
        r = parse_requirement("requests")
        self.assertEqual(r.name, "requests")
        self.assertEqual(r.normalized_name, "requests")
        self.assertEqual(r.extras, frozenset())
        self.assertEqual(r.specifiers, [])
        self.assertIsNone(r.marker)
        self.assertIsNone(r.parse_error)

    def test_version_eq(self):
        r = parse_requirement("requests==2.31.0")
        self.assertEqual(r.name, "requests")
        self.assertEqual(len(r.specifiers), 1)
        self.assertEqual(r.specifiers[0].operator, "==")
        self.assertEqual(r.specifiers[0].version, "2.31.0")

    def test_version_ge(self):
        r = parse_requirement("requests>=2.0")
        self.assertEqual(r.specifiers[0].operator, ">=")
        self.assertEqual(r.specifiers[0].version, "2.0")

    def test_multiple_specifiers(self):
        r = parse_requirement("requests>=2,<3")
        self.assertEqual(len(r.specifiers), 2)
        ops = [s.operator for s in r.specifiers]
        self.assertIn(">=", ops)
        self.assertIn("<", ops)

    def test_extras(self):
        r = parse_requirement("requests[security]")
        self.assertEqual(r.extras, frozenset({"security"}))

    def test_extras_multiple(self):
        r = parse_requirement("requests[security,socks]")
        self.assertEqual(r.extras, frozenset({"security", "socks"}))

    def test_extras_with_version(self):
        r = parse_requirement("foo[bar]>=1.2")
        self.assertEqual(r.extras, frozenset({"bar"}))
        self.assertEqual(r.specifiers[0].operator, ">=")

    def test_marker_simple(self):
        r = parse_requirement('pywin32; sys_platform == "win32"')
        self.assertEqual(r.name, "pywin32")
        self.assertIsNotNone(r.marker)
        self.assertIn("sys_platform", r.marker)

    def test_marker_python_version(self):
        r = parse_requirement('typing-extensions; python_version < "3.11"')
        self.assertIsNotNone(r.marker)

    def test_normalized_name(self):
        r = parse_requirement("My_Package")
        self.assertEqual(r.normalized_name, "my-package")

    def test_url_requirement(self):
        r = parse_requirement("foo @ https://example.com/foo.tar.gz")
        self.assertIsNotNone(r.parse_error)
        self.assertIn("URL", r.parse_error)

    def test_empty(self):
        r = parse_requirement("")
        self.assertEqual(r.parse_error, "empty")

    def test_comment_line(self):
        r = parse_requirement("# this is a comment")
        self.assertEqual(r.parse_error, "comment line")

    def test_inline_comment_stripped(self):
        r = parse_requirement("requests>=2.0 # production dependency")
        self.assertEqual(r.name, "requests")
        self.assertIsNone(r.parse_error)

    def test_tilde_eq(self):
        r = parse_requirement("requests~=2.28")
        self.assertEqual(r.specifiers[0].operator, "~=")


class TestEvaluateMarker(unittest.TestCase):

    def test_none_marker(self):
        self.assertTrue(evaluate_marker(None))

    def test_empty_marker(self):
        self.assertTrue(evaluate_marker(""))

    def test_sys_platform_win32_on_non_win(self):
        import sys
        if sys.platform != "win32":
            self.assertFalse(evaluate_marker('sys_platform == "win32"'))

    def test_sys_platform_linux_on_linux(self):
        import sys
        result = evaluate_marker(f'sys_platform == "{sys.platform}"')
        self.assertTrue(result)

    def test_unknown_variable(self):
        # Unknown variables → include (True)
        self.assertTrue(evaluate_marker('unknown_var == "foo"'))

    def test_and_both_true(self):
        import sys
        marker = f'sys_platform == "{sys.platform}" and python_version >= "2.0"'
        self.assertTrue(evaluate_marker(marker))

    def test_or_one_true(self):
        import sys
        marker = f'sys_platform == "nonexistent_os" or sys_platform == "{sys.platform}"'
        self.assertTrue(evaluate_marker(marker))


if __name__ == "__main__":
    unittest.main()
