from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyxray.cli import Context



def cmd_tree(ctx: Context, args: argparse.Namespace) -> int:
    from pyxray import output as out
    from pyxray.analysis import compute_in_degrees
    from pyxray.output import render_tree

    project = ctx.get_project()
    graph = ctx.get_graph()
    ctx.emit_warnings()

    max_depth = args.depth
    sort_by = getattr(args, "sort_by", "alpha")

    def display(norm_name: str) -> str:
        pkg = graph.packages.get(norm_name)
        if pkg:
            ver = out.dim(f" {pkg.version}")
            if norm_name in graph.missing:
                return out.red(norm_name) + out.dim(" [not installed]")
            return out.cyan(norm_name) + ver
        return out.red(norm_name) + out.dim(" [?]")

    if ctx.json_output:

        def build_tree_dict(node: str, seen: set) -> dict:
            if node in seen:
                return {"name": node, "already_shown": True}
            seen.add(node)
            children = sorted(graph.forward.get(node, set()))
            pkg = graph.packages.get(node)
            return {
                "name": node,
                "version": pkg.version if pkg else "?",
                "dependencies": [build_tree_dict(c, seen) for c in children],
            }

        roots = sorted(graph.roots)
        result = {
            "project": project.name,
            "trees": [build_tree_dict(r, set()) for r in roots],
        }
        out.print_json(result)
        return 0

    out.section(f"Dependency Tree — {project.name}")

    if not graph.roots:
        out.println(out.dim("  (no dependencies declared)"))
        return 0

    # R6: build sort key — in-degree proxy for "heaviness"
    if sort_by == "in-degree":
        in_deg = compute_in_degrees(graph)
        def children_fn(n: str) -> list[str]:
            kids = list(graph.forward.get(n, set()))
            # Sort by in-degree descending (most-depended-upon first), then alpha
            return sorted(kids, key=lambda x: (-in_deg.get(x, 0), x))
    else:
        def children_fn(n: str) -> list[str]:
            return sorted(graph.forward.get(n, set()))

    # Render each root as its own subtree
    for root in sorted(graph.roots):
        lines = render_tree(
            root,
            children_fn=children_fn,
            display_fn=display,
            max_depth=max_depth,
        )
        for line in lines:
            out.println("  " + line)
        out.println()

    return 0
