from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyxray.cli import Context



def _get_edge_constraint(graph, from_norm: str, to_norm: str) -> str:
    """Return the version specifier string that ties from_norm → to_norm.

    Walks raw_requires of the from package and extracts the specifier portion
    (e.g. '>=0.36.3') for the matching dependency entry. Returns '' if none found.
    """
    from pyxray.requirements import fast_extract_normalized_name
    pkg = graph.packages.get(from_norm)
    if not pkg:
        return ""
    for raw in pkg.raw_requires:
        dep_norm = fast_extract_normalized_name(raw)
        if dep_norm == to_norm:
            # Extract specifier: everything after the first name token
            # raw is like 'starlette>=0.36.3' or 'anyio>=4.0.0,<5'
            # Strip the package name (up to first =/</>/ ;)
            import re
            m = re.match(r"[A-Za-z0-9_\-.]+\s*([^;]*)", raw)
            if m:
                spec = m.group(1).strip().split(";")[0].strip()
                return spec
    return ""

def cmd_why(ctx: Context, args: argparse.Namespace) -> int:
    from pyxray import output as out
    from pyxray.analysis import find_reverse_paths
    from pyxray.models import normalize_name

    package = args.package
    norm = normalize_name(package)

    graph = ctx.get_graph()
    ctx.emit_warnings()

    if norm not in graph.packages:
        out.print_err(
            f"'{package}' is not in the dependency graph. "
            f"Is it installed? Try: python -m pyxray summary"
        )
        return 1

    paths = find_reverse_paths(
        graph, target=norm, roots=graph.roots, max_paths=args.max_paths
    )

    pkg = graph.packages.get(norm)
    ver_str = f" ({pkg.version})" if pkg else ""

    if ctx.json_output:
        out.print_json(
            {
                "package": norm,
                "version": pkg.version if pkg else "?",
                "paths": paths,
            }
        )
        return 0

    out.section(f"Why is '{package}' installed?{ver_str}")

    if not paths:
        if norm in graph.roots:
            out.print_ok(f"'{package}' is a direct (root) project dependency.")
        else:
            out.println(out.dim(f"  No path found from project roots to '{package}'."))
            out.println(
                out.dim(
                    "  It may be installed but not reachable from declared dependencies."
                )
            )
        return 0

    for i, path in enumerate(paths, 1):
        out.println(out.bold(f"\n  Path {i}"))

        def pkg_display(n: str) -> str:
            return (
                (graph.packages[n].name if n in graph.packages else n)
                + " "
                + out.dim(
                    f"({graph.packages[n].version})"
                    if n in graph.packages and graph.packages[n].version != "?"
                    else ""
                )
            )

        # R7: edge_label_fn shows version constraint between hops
        def edge_label_fn(from_n: str, to_n: str) -> str:
            return _get_edge_constraint(graph, from_n, to_n)

        from pyxray.output import render_path

        for line in render_path(path, display_fn=pkg_display, edge_label_fn=edge_label_fn):
            out.println("    " + line)

    out.println()
    return 0
