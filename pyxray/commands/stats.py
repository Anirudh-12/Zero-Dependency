from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyxray.cli import Context



def cmd_stats(ctx: Context, args: argparse.Namespace) -> int:
    from pyxray import output as out
    from pyxray.analysis import compute_depths, compute_in_degrees, compute_stats

    project = ctx.get_project()
    graph = ctx.get_graph()
    ctx.emit_warnings()

    stats = compute_stats(graph)
    depths = compute_depths(graph)
    in_deg = compute_in_degrees(graph)

    if ctx.json_output:
        out.print_json({"project": project.name, "stats": stats})
        return 0

    out.section(f"Graph Statistics — {project.name}")

    metrics = [
        ("Packages (total)", stats["total_packages"], "nodes"),
        ("Direct dependencies", stats["direct_dependencies"], "root nodes"),
        ("Transitive dependencies", stats["transitive_dependencies"], "non-root nodes"),
        ("Dependency edges", stats["dependency_edges"], "edges"),
        ("Leaf packages", stats["leaf_packages"], "no outgoing edges"),
        ("Missing packages", stats["missing_packages"], "not installed"),
        ("", "", ""),
        ("Maximum depth", stats["maximum_depth"], "hops from a root"),
        ("Average depth", stats["average_depth"], "BFS from roots"),
        ("Maximum fan-out", stats["maximum_fan_out"], "direct deps of one package"),
        ("Maximum fan-in", stats["maximum_fan_in"], "dependents of one package"),
        ("", "", ""),
        ("Cycle count", stats["cycle_count"], "strongly connected"),
        (
            "Largest subtree",
            f"{stats['largest_subtree_root']} ({stats['largest_subtree_size']} pkgs)",
            "from one root",
        ),
        (
            "Most depended upon",
            f"{stats['most_depended_upon']} ({stats['most_depended_upon_count']} deps)",
            "highest in-degree",
        ),
    ]

    for label, value, note in metrics:
        if not label:
            out.println()
            continue
        note_str = out.dim(f"  # {note}") if note else ""
        out.println(f"  {label:<32} {out.bold(str(value)):<20}{note_str}")

    out.println()
    return 0
