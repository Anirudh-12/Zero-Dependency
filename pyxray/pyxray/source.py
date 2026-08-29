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
from pathlib import Path
from typing import Optional

from pyxray.models import Package, SourceImport, normalize_name


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
            "__future__", "_thread", "abc", "aifc", "argparse", "array",
            "ast", "asynchat", "asyncio", "asyncore", "atexit", "audioop",
            "base64", "bdb", "binascii", "binhex", "bisect", "builtins",
            "bz2", "calendar", "cgi", "cgitb", "chunk", "cmath", "cmd",
            "code", "codecs", "codeop", "colorsys", "compileall",
            "concurrent", "configparser", "contextlib", "contextvars",
            "copy", "copyreg", "cProfile", "csv", "ctypes", "curses",
            "dataclasses", "datetime", "dbm", "decimal", "difflib",
            "dis", "doctest", "email", "encodings", "enum", "errno",
            "faulthandler", "fcntl", "filecmp", "fileinput", "fnmatch",
            "fractions", "ftplib", "functools", "gc", "getopt", "getpass",
            "gettext", "glob", "grp", "gzip", "hashlib", "heapq", "hmac",
            "html", "http", "idlelib", "imaplib", "importlib", "inspect",
            "io", "ipaddress", "itertools", "json", "keyword", "lib2to3",
            "linecache", "locale", "logging", "lzma", "mailbox", "mailcap",
            "marshal", "math", "mimetypes", "mmap", "modulefinder",
            "multiprocessing", "netrc", "nis", "nntplib", "numbers",
            "operator", "optparse", "os", "ossaudiodev", "pathlib", "pdb",
            "pickletools", "pickle", "pipes", "pkgutil", "platform",
            "plistlib", "poplib", "posix", "posixpath", "pprint",
            "profile", "pstats", "pty", "pwd", "py_compile", "pyclbr",
            "pydoc", "queue", "quopri", "random", "re", "readline",
            "reprlib", "resource", "rlcompleter", "runpy", "sched",
            "secrets", "select", "selectors", "shelve", "shlex", "shutil",
            "signal", "site", "smtpd", "smtplib", "sndhdr", "socket",
            "socketserver", "spwd", "sqlite3", "sre_compile", "sre_constants",
            "sre_parse", "ssl", "stat", "statistics", "string", "stringprep",
            "struct", "subprocess", "sunau", "symtable", "sys", "sysconfig",
            "syslog", "tabnanny", "tarfile", "telnetlib", "tempfile",
            "termios", "test", "textwrap", "threading", "time", "timeit",
            "tkinter", "token", "tokenize", "tomllib", "trace", "traceback",
            "tracemalloc", "tty", "turtle", "turtledemo", "types",
            "typing", "unicodedata", "unittest", "urllib", "uu", "uuid",
            "venv", "warnings", "wave", "weakref", "webbrowser",
            "winreg", "winsound", "wsgiref", "xdrlib", "xml", "xmlrpc",
            "zipapp", "zipfile", "zipimport", "zlib", "zoneinfo",
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
        "__pycache__", ".venv", "venv", ".git", "node_modules",
        ".tox", ".mypy_cache", ".ruff_cache", "dist", "build",
        ".eggs", "*.egg-info",
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
