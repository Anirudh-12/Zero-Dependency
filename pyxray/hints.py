"""
hints.py — Static stdlib replacement hints for the ``prune`` command.

No ML, no network, no third-party deps.
A curated dict maps common thin packages to their stdlib alternative.
Unknown packages get a generic fallback message.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Static lookup table
# ---------------------------------------------------------------------------

STDLIB_HINTS: dict[str, str] = {
    # Typing / introspection
    "typing-inspection":   "inspect.get_annotations() covers most use cases (Python 3.10+)",
    "typing-extensions":   "typing (most backports now in stdlib for 3.11+)",
    "backports-abc":       "abc (stdlib)",

    # Data / serialisation
    "simplejson":          "json (stdlib)",
    "ujson":               "json (stdlib) — only replace if profiling shows json is a bottleneck",
    "toml":                "tomllib (stdlib 3.11+) / tomli for 3.10-",
    "pyyaml":              "Consider json or tomllib; no YAML parser in stdlib",
    "ordereddict":         "dict (ordered by default since Python 3.7+)",

    # Python 2 compatibility shims
    "six":                 "Write Python 3-only code — six is no longer needed",
    "future":              "Write Python 3-only code — the 'future' shim is obsolete",
    "enum34":              "enum (stdlib 3.4+)",
    "futures":             "concurrent.futures (stdlib 3.2+)",
    "pathlib2":            "pathlib (stdlib 3.4+)",

    # Utility / functional
    "more-itertools":      "itertools (stdlib) — check if your specific combinator is there",
    "attrs":               "dataclasses (stdlib 3.7+)",
    "dataclasses":         "dataclasses (stdlib 3.7+)",
    "cached-property":     "functools.cached_property (stdlib 3.8+)",
    "contextlib2":         "contextlib (stdlib)",
    "shutilwhich":         "shutil.which() (stdlib 3.3+)",
    "monotonic":           "time.monotonic() (stdlib 3.3+)",
    "wcwidth":             "unicodedata.east_asian_width() (stdlib)",

    # I/O / filesystem
    "zipp":                "zipfile (stdlib 3.8+)",
    "scandir":             "os.scandir() (stdlib 3.5+)",

    # Testing
    "mock":                "unittest.mock (stdlib 3.3+)",

    # CLI / output
    "click":               "argparse (stdlib) — as PyXRay itself demonstrates",
    "colorama":            "ANSI escape codes directly (\\033[...m) — as PyXRay itself does",
    "termcolor":           "ANSI escape codes directly (\\033[...m)",

    # Metadata / packaging
    "importlib-metadata":  "importlib.metadata (stdlib 3.8+)",
    "importlib-resources": "importlib.resources (stdlib 3.9+)",
    "pkg-resources":       "importlib.metadata (stdlib 3.8+)",
}

_GENERIC_HINT = "Consider replacing with a stdlib equivalent"


# ---------------------------------------------------------------------------
# Public accessor
# ---------------------------------------------------------------------------


def get_hint(norm_name: str) -> str:
    """Return a stdlib replacement hint for *norm_name*, or a generic message.

    Always returns a non-empty string — callers can print unconditionally.
    """
    return STDLIB_HINTS.get(norm_name, _GENERIC_HINT)


def has_specific_hint(norm_name: str) -> bool:
    """Return True if the package has a curated (non-generic) hint."""
    return norm_name in STDLIB_HINTS
