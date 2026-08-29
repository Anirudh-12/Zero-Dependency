"""
output.py — Terminal output for PyXRay.

Replaces: rich, colorama, click's echo helpers

Uses only:
    sys.stdout / sys.stderr
    os
    textwrap

Provides:
    - ANSI color (with NO_COLOR and TTY detection)
    - Box-drawing characters for trees
    - Section headers
    - Tables
    - Indented tree rendering
"""

from __future__ import annotations

import json
import os
import sys
import textwrap
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Color support detection
# ---------------------------------------------------------------------------


def _should_use_color(force: Optional[bool] = None) -> bool:
    if force is not None:
        return force
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


# Will be updated by CLI after parsing --no-color / --color
_COLOR_ENABLED: bool = _should_use_color()


def set_color(enabled: bool) -> None:
    global _COLOR_ENABLED
    _COLOR_ENABLED = enabled


# ---------------------------------------------------------------------------
# ANSI codes
# ---------------------------------------------------------------------------

_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"

# Foreground
_RED = "\033[91m"
_GREEN = "\033[92m"
_YELLOW = "\033[93m"
_BLUE = "\033[94m"
_MAGENTA = "\033[95m"
_CYAN = "\033[96m"
_WHITE = "\033[97m"
_GRAY = "\033[90m"


def _c(text: str, *codes: str) -> str:
    """Wrap *text* with ANSI codes if color is enabled."""
    if not _COLOR_ENABLED:
        return text
    return "".join(codes) + text + _RESET


def bold(t: str) -> str:
    return _c(t, _BOLD)


def dim(t: str) -> str:
    return _c(t, _DIM)


def red(t: str) -> str:
    return _c(t, _RED)


def green(t: str) -> str:
    return _c(t, _GREEN)


def yellow(t: str) -> str:
    return _c(t, _YELLOW)


def blue(t: str) -> str:
    return _c(t, _BLUE)


def cyan(t: str) -> str:
    return _c(t, _CYAN)


def magenta(t: str) -> str:
    return _c(t, _MAGENTA)


def gray(t: str) -> str:
    return _c(t, _GRAY)


# ---------------------------------------------------------------------------
# Print helpers
# ---------------------------------------------------------------------------


def println(text: str = "") -> None:
    print(text)


def print_err(text: str) -> None:
    print(red("✗ ") + text, file=sys.stderr)


def print_warn(text: str) -> None:
    print(yellow("⚠ ") + text, file=sys.stderr)


def print_ok(text: str) -> None:
    print(green("✓ ") + text)


def section(title: str, width: int = 50) -> None:
    """Print a titled section separator."""
    println()
    println(bold(cyan(title)))
    println(dim("─" * width))


def subsection(title: str) -> None:
    println()
    println(bold(title))


def header() -> None:
    """Print the PyXRay application header."""
    println(bold(cyan("  ____       __  ____             ")))
    println(bold(cyan(" |  _ \\ _   _\\ \\/ /  _ \\ __ _ _   _")))
    println(bold(cyan(" | |_) | | | |\\  /| |_) / _` | | | |")))
    println(bold(cyan(" |  __/| |_| |/  \\|  _ < (_| | |_| |")))
    println(bold(cyan(" |_|    \\__, /_/\\_\\_| \\_\\__,_|\\__, |")))
    println(bold(cyan("        |___/                  |___/ ")))
    println(dim("  Python Dependency Investigation Tool"))
    println()


# ---------------------------------------------------------------------------
# Tree rendering
# ---------------------------------------------------------------------------

_BRANCH = "├── "
_LAST = "└── "
_PIPE = "│   "
_SPACE = "    "


def render_tree(
    node: str,
    children_fn,  # callable: (node_name) → list[str]
    display_fn=None,  # callable: (node_name) → str  (for display)
    prefix: str = "",
    seen: Optional[set[str]] = None,
    depth: int = 0,
    max_depth: Optional[int] = None,
    _is_last: bool = True,
) -> list[str]:
    """Recursively render a dependency tree as lines of text.

    Parameters
    ----------
    node:        Current node name (normalized).
    children_fn: Returns the list of child node names.
    display_fn:  Returns the display string for a node (default: node itself).
    prefix:      Current line prefix (for indentation).
    seen:        Set of already-rendered nodes (to handle DAG sharing).
    depth:       Current depth level.
    max_depth:   Maximum depth to render (None = unlimited).
    """
    if seen is None:
        seen = set()

    display = display_fn(node) if display_fn else node
    lines: list[str] = []

    if depth == 0:
        lines.append(bold(display))
        seen.add(node)
        children = children_fn(node)
        for i, child in enumerate(sorted(children)):
            is_last = i == len(children) - 1
            lines.extend(
                render_tree(
                    child,
                    children_fn,
                    display_fn=display_fn,
                    prefix="",
                    seen=seen,
                    depth=1,
                    max_depth=max_depth,
                    _is_last=is_last,
                )
            )
        return lines

    connector = _LAST if _is_last else _BRANCH
    child_prefix = prefix + (_SPACE if _is_last else _PIPE)

    if node in seen:
        lines.append(prefix + connector + dim(display) + gray(" [already shown]"))
        return lines

    if max_depth is not None and depth > max_depth:
        lines.append(prefix + connector + dim(display) + gray(" [depth limit]"))
        return lines

    seen.add(node)
    lines.append(prefix + connector + display)

    children = children_fn(node)
    for i, child in enumerate(sorted(children)):
        is_last = i == len(children) - 1
        lines.extend(
            render_tree(
                child,
                children_fn,
                display_fn=display_fn,
                prefix=child_prefix,
                seen=seen,
                depth=depth + 1,
                max_depth=max_depth,
                _is_last=is_last,
            )
        )

    return lines


# ---------------------------------------------------------------------------
# Table rendering
# ---------------------------------------------------------------------------


def render_table(
    rows: list[tuple[str, ...]],
    headers: Optional[tuple[str, ...]] = None,
    col_widths: Optional[list[int]] = None,
) -> list[str]:
    """Render rows as a fixed-width table."""
    if not rows:
        return []

    n_cols = len(rows[0])
    all_rows = list(rows)
    if headers:
        all_rows = [headers] + all_rows

    if col_widths is None:
        col_widths = [0] * n_cols
        for row in all_rows:
            for i, cell in enumerate(row):
                col_widths[i] = max(col_widths[i], len(str(cell)))

    lines: list[str] = []
    if headers:
        header_line = "  ".join(
            bold(str(h).ljust(col_widths[i])) for i, h in enumerate(headers)
        )
        lines.append(header_line)
        lines.append(dim("─" * (sum(col_widths) + 2 * (n_cols - 1))))

    for row in rows:
        line = "  ".join(str(cell).ljust(col_widths[i]) for i, cell in enumerate(row))
        lines.append(line)

    return lines


# ---------------------------------------------------------------------------
# JSON output
# ---------------------------------------------------------------------------


def print_json(data: Any) -> None:
    """Serialize *data* to stdout as pretty-printed JSON."""
    print(json.dumps(data, indent=2, default=str))


# ---------------------------------------------------------------------------
# Path rendering helper
# ---------------------------------------------------------------------------


def render_path(path: list[str], display_fn=None) -> list[str]:
    """Render a dependency path as an indented chain."""
    if not path:
        return []
    lines: list[str] = []
    for i, node in enumerate(path):
        display = display_fn(node) if display_fn else node
        if i == 0:
            lines.append(bold(display))
        else:
            indent = "  " * i
            lines.append(indent + _LAST + display)
    return lines
