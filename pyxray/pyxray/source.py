"""
source.py — Static Python source code analysis using ast.

Replaces: third-party import scanners (vulture, isort's scanning, etc.)

Uses only:
    ast      (stdlib, Python 3.x)
    pathlib  (stdlib)
    os       (stdlib)

Extracts import statements from .py files without executing them.
Maps import top-level names to installed distributions using:
    - top_level_names from Package metadata
    - stdlib module list (sys.stdlib_module_names, Python 3.10+)

Important limitations (documented in STDLIB.md):
    - Dynamic imports (importlib.import_module, __import__) are NOT detected
    - Conditional imports inside try/except or if TYPE_CHECKING may be missed
      if they are not at module level (they are caught if they are top-level)
    - Generated code or .pyi stubs are not scanned
"""

from __future__ import annotations

import ast
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from pyxray.models import Package, SourceImport, normalize_name

# ---------------------------------------------------------------------------
# Symbol-level usage tracking (for prune command)
# ---------------------------------------------------------------------------


@dataclass
class SourceUsage:
    """Per-package usage summary extracted from AST scan.

    Used by the ``prune`` command to determine reimplement candidacy.

    Fields
    ------
    norm_name:   Normalized distribution name.
    files:       Set of source files that import this package.
    symbols:     Imported symbol names.
                 '*' means bare ``import pkg`` (full module).
                 Specific names come from ``from pkg import X, Y``.
    """

    norm_name: str
    files: set = field(default_factory=set)
    symbols: set = field(default_factory=set)

    @property
    def file_count(self) -> int:
        return len(self.files)

    @property
    def symbol_count(self) -> int:
        return len(self.symbols)

    @property
    def uses_full_module(self) -> bool:
        """True when bare ``import pkg`` was used — full API surface unknown."""
        return "*" in self.symbols


# ---------------------------------------------------------------------------
# Standard library module names
# ---------------------------------------------------------------------------


def _stdlib_modules() -> frozenset[str]:
    """Return a frozenset of stdlib top-level module names.

    Uses sys.stdlib_module_names (Python 3.10+) or a curated fallback.
    """
    if hasattr(sys, "stdlib_module_names"):
        return frozenset(sys.stdlib_module_names)  # type: ignore[attr-defined]
    # Curated fallback for older pythons (we target 3.12 but keep it safe)
    return frozenset(
        {
            "__future__",
            "_thread",
            "abc",
            "aifc",
            "argparse",
            "array",
            "ast",
            "asynchat",
            "asyncio",
            "asyncore",
            "atexit",
            "audioop",
            "base64",
            "bdb",
            "binascii",
            "binhex",
            "bisect",
            "builtins",
            "bz2",
            "calendar",
            "cgi",
            "cgitb",
            "chunk",
            "cmath",
            "cmd",
            "code",
            "codecs",
            "codeop",
            "colorsys",
            "compileall",
            "concurrent",
            "configparser",
            "contextlib",
            "contextvars",
            "copy",
            "copyreg",
            "cProfile",
            "csv",
            "ctypes",
            "curses",
            "dataclasses",
            "datetime",
            "dbm",
            "decimal",
            "difflib",
            "dis",
            "doctest",
            "email",
            "encodings",
            "enum",
            "errno",
            "faulthandler",
            "fcntl",
            "filecmp",
            "fileinput",
            "fnmatch",
            "fractions",
            "ftplib",
            "functools",
            "gc",
            "getopt",
            "getpass",
            "gettext",
            "glob",
            "grp",
            "gzip",
            "hashlib",
            "heapq",
            "hmac",
            "html",
            "http",
            "idlelib",
            "imaplib",
            "importlib",
            "inspect",
            "io",
            "ipaddress",
            "itertools",
            "json",
            "keyword",
            "lib2to3",
            "linecache",
            "locale",
            "logging",
            "lzma",
            "mailbox",
            "mailcap",
            "marshal",
            "math",
            "mimetypes",
            "mmap",
            "modulefinder",
            "multiprocessing",
            "netrc",
            "nis",
            "nntplib",
            "numbers",
            "operator",
            "optparse",
            "os",
            "ossaudiodev",
            "pathlib",
            "pdb",
            "pickletools",
            "pickle",
            "pipes",
            "pkgutil",
            "platform",
            "plistlib",
            "poplib",
            "posix",
            "posixpath",
            "pprint",
            "profile",
            "pstats",
            "pty",
            "pwd",
            "py_compile",
            "pyclbr",
            "pydoc",
            "queue",
            "quopri",
            "random",
            "re",
            "readline",
            "reprlib",
            "resource",
            "rlcompleter",
            "runpy",
            "sched",
            "secrets",
            "select",
            "selectors",
            "shelve",
            "shlex",
            "shutil",
            "signal",
            "site",
            "smtpd",
            "smtplib",
            "sndhdr",
            "socket",
            "socketserver",
            "spwd",
            "sqlite3",
            "sre_compile",
            "sre_constants",
            "sre_parse",
            "ssl",
            "stat",
            "statistics",
            "string",
            "stringprep",
            "struct",
            "subprocess",
            "sunau",
            "symtable",
            "sys",
            "sysconfig",
            "syslog",
            "tabnanny",
            "tarfile",
            "telnetlib",
            "tempfile",
            "termios",
            "test",
            "textwrap",
            "threading",
            "time",
            "timeit",
            "tkinter",
            "token",
            "tokenize",
            "tomllib",
            "trace",
            "traceback",
            "tracemalloc",
            "tty",
            "turtle",
            "turtledemo",
            "types",
            "typing",
            "unicodedata",
            "unittest",
            "urllib",
            "uu",
            "uuid",
            "venv",
            "warnings",
            "wave",
            "weakref",
            "webbrowser",
            "winreg",
            "winsound",
            "wsgiref",
            "xdrlib",
            "xml",
            "xmlrpc",
            "zipapp",
            "zipfile",
            "zipimport",
            "zlib",
            "zoneinfo",
        }
    )


_STDLIB: frozenset[str] = _stdlib_modules()


# ---------------------------------------------------------------------------
# Import extraction
# ---------------------------------------------------------------------------


def extract_imports_from_file(path: Path) -> tuple[list[SourceImport], Optional[str]]:
    """Parse *path* with ast and return all import statements.

    Returns (imports, error_message).  On parse error returns ([], error).

    Notes
    -----
    - We catch SyntaxError and UnicodeDecodeError gracefully.
    - We walk the entire AST to catch imports inside functions/classes.
    """
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [], f"cannot read {path}: {exc}"

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        return [], f"syntax error in {path}: {exc}"

    imports: list[SourceImport] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                imports.append(
                    SourceImport(
                        module=top,
                        file=str(path),
                        line=node.lineno,
                        col=node.col_offset,
                        is_from=False,
                    )
                )
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:  # absolute import only
                top = node.module.split(".")[0]
                imports.append(
                    SourceImport(
                        module=top,
                        file=str(path),
                        line=node.lineno,
                        col=node.col_offset,
                        is_from=True,
                    )
                )

    return imports, None


def scan_source_roots(
    source_roots: list[str],
    project_root: str,
    skip_patterns: Optional[list[str]] = None,
) -> tuple[list[SourceImport], list[str]]:
    """Recursively scan *source_roots* for .py files and extract imports.

    Returns (imports, warnings).

    Parameters
    ----------
    source_roots:   Directories to scan.
    project_root:   Used to compute relative paths for display.
    skip_patterns:  Glob-style directory names to skip (e.g. ["__pycache__", ".venv"]).
    """
    _skip = set(skip_patterns or []) | {
        "__pycache__",
        ".venv",
        "venv",
        ".git",
        "node_modules",
        ".tox",
        ".mypy_cache",
        ".ruff_cache",
        "dist",
        "build",
        ".eggs",
        "*.egg-info",
    }

    all_imports: list[SourceImport] = []
    warnings: list[str] = []
    root_path = Path(project_root)
    seen_files: set[str] = set()

    for src_root in source_roots:
        src = Path(src_root)
        if not src.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(src):
            # Prune skipped directories in-place (modifies dirnames)
            dirnames[:] = [
                d for d in dirnames if d not in _skip and not d.endswith(".egg-info")
            ]
            for fname in filenames:
                if not fname.endswith(".py"):
                    continue
                fpath = Path(dirpath) / fname
                abs_str = str(fpath.resolve())
                if abs_str in seen_files:
                    continue
                seen_files.add(abs_str)

                try:
                    rel = str(fpath.relative_to(root_path))
                except ValueError:
                    rel = str(fpath)

                file_imports, err = extract_imports_from_file(fpath)
                if err:
                    warnings.append(err)
                    continue

                # Rewrite the .file field to a relative path
                for imp in file_imports:
                    imp.file = rel

                all_imports.extend(file_imports)

    return all_imports, warnings


# ---------------------------------------------------------------------------
# Import → distribution mapping
# ---------------------------------------------------------------------------


def build_import_map(
    packages: dict[str, Package],
) -> dict[str, str]:
    """Build a mapping of top-level import name → normalized distribution name.

    Strategy (in order of reliability):
        1. top_level_names from Package (from top_level.txt or RECORD).
        2. The distribution's own normalized name (e.g. "requests" → "requests").
        3. The distribution's name with underscores (e.g. "my_pkg" for "my-pkg").

    Limitation: Packages like beautifulsoup4 (import bs4) that use a
    completely different import name will only be mapped if top_level.txt
    is present.  We document this in STDLIB.md.
    """
    import_map: dict[str, str] = {}

    for norm_name, pkg in packages.items():
        # From explicit metadata
        for top in pkg.top_level_names:
            if top and top not in import_map:
                import_map[top] = norm_name

        # Fallback: try the package name itself
        base = norm_name.replace("-", "_")
        if base and base not in import_map:
            import_map[base] = norm_name

        # Also try the original display name
        display_base = pkg.name.replace("-", "_").replace(".", "_")
        if display_base and display_base not in import_map:
            import_map[display_base] = norm_name

    return import_map


def classify_imports(
    imports: list[SourceImport],
    import_map: dict[str, str],
) -> tuple[set[str], set[str], set[str]]:
    """Classify a list of SourceImports.

    Returns
    -------
    third_party_norm_names:
        Normalized distribution names that appear to be third-party imports.
    stdlib_modules:
        Top-level module names identified as stdlib.
    unknown_modules:
        Import names that could not be classified as stdlib or third-party.
    """
    third_party: set[str] = set()
    stdlib_found: set[str] = set()
    unknown: set[str] = set()

    for imp in imports:
        mod = imp.module
        if mod in _STDLIB:
            stdlib_found.add(mod)
        elif mod in import_map:
            third_party.add(import_map[mod])
        else:
            unknown.add(mod)

    return third_party, stdlib_found, unknown


# ---------------------------------------------------------------------------
# Symbol-level usage map (for prune command)
# ---------------------------------------------------------------------------

def build_usage_map(
    imports: list[SourceImport],
    import_map: dict[str, str],
    raw_symbols: Optional[list] = None,
) -> dict[str, "SourceUsage"]:
    """Build a per-package SourceUsage map from a list of SourceImports.

    For each third-party package detected, records:
    - Which source files import it
    - Which symbols are imported from it

    ``raw_symbols`` is an optional parallel list of symbol sets produced by
    ``extract_imports_with_symbols``.  If absent, bare ``*`` is used for
    all imports (conservative — assumes full API usage).

    Returns dict of normalized_name → SourceUsage.
    """
    usage: dict[str, SourceUsage] = {}

    for i, imp in enumerate(imports):
        if imp.module in _STDLIB:
            continue
        norm = import_map.get(imp.module)
        if not norm:
            continue

        if norm not in usage:
            usage[norm] = SourceUsage(norm_name=norm)

        usage[norm].files.add(imp.file)

        # Symbol tracking
        if raw_symbols and i < len(raw_symbols):
            for sym in raw_symbols[i]:
                usage[norm].symbols.add(sym)
        elif not imp.is_from:
            # bare `import pkg` — treat as full module usage
            usage[norm].symbols.add("*")
        else:
            # `from pkg import ?` but no symbol list → mark unknown
            usage[norm].symbols.add("?")

    return usage


def extract_imports_with_symbols(path: "Path") -> tuple[
    list[SourceImport], list[set[str]], Optional[str]
]:
    """Like extract_imports_from_file but also returns per-import symbol sets.

    Returns (imports, symbol_sets, error).
    symbol_sets[i] is the set of names imported by imports[i].

    Examples
    --------
    ``import os``                    → symbols = {"*"}
    ``from os import path``          → symbols = {"path"}
    ``from os.path import join, exists`` → symbols = {"join", "exists"}
    ``from os import *``             → symbols = {"*"}
    """
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [], [], f"cannot read {path}: {exc}"

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        return [], [], f"syntax error in {path}: {exc}"

    imports: list[SourceImport] = []
    symbol_sets: list[set[str]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                imports.append(SourceImport(
                    module=top, file=str(path),
                    line=node.lineno, col=node.col_offset, is_from=False,
                ))
                symbol_sets.append({"*"})  # bare import = full module

        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                top = node.module.split(".")[0]
                # Collect imported names
                names = set()
                for alias in node.names:
                    if alias.name == "*":
                        names.add("*")
                    else:
                        names.add(alias.name)
                imports.append(SourceImport(
                    module=top, file=str(path),
                    line=node.lineno, col=node.col_offset, is_from=True,
                ))
                symbol_sets.append(names)

    return imports, symbol_sets, None


def scan_with_usage(
    source_roots: list[str],
    project_root: str,
    import_map: dict[str, str],
    skip_patterns: Optional[list[str]] = None,
) -> tuple[list[SourceImport], dict[str, "SourceUsage"], list[str]]:
    """Scan source roots and return both raw imports and per-package usage maps.

    Returns (all_imports, usage_map, warnings).
    """
    _skip = set(skip_patterns or []) | {
        "__pycache__", ".venv", "venv", ".git", "node_modules",
        ".tox", ".mypy_cache", ".ruff_cache", "dist", "build",
    }

    all_imports: list[SourceImport] = []
    all_symbols: list[set[str]] = []
    warnings: list[str] = []
    seen_files: set[str] = set()

    for src_root in source_roots:
        src = Path(src_root)
        if not src.is_dir():
            continue
        for dirpath, dirnames, filenames in __import__("os").walk(src):
            dirnames[:] = [
                d for d in dirnames
                if d not in _skip and not d.endswith(".egg-info")
            ]
            for fname in filenames:
                if not fname.endswith(".py"):
                    continue
                fpath = Path(dirpath) / fname
                abs_str = str(fpath.resolve())
                if abs_str in seen_files:
                    continue
                seen_files.add(abs_str)

                try:
                    rel = str(fpath.relative_to(Path(project_root)))
                except ValueError:
                    rel = str(fpath)

                file_imports, file_symbols, err = extract_imports_with_symbols(fpath)
                if err:
                    warnings.append(err)
                    continue

                for imp in file_imports:
                    imp.file = rel

                all_imports.extend(file_imports)
                all_symbols.extend(file_symbols)

    usage_map = build_usage_map(all_imports, import_map, all_symbols)
    return all_imports, usage_map, warnings
