from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyxray.cli import Context



def cmd_hotspots(ctx: Context, args: argparse.Namespace) -> int:
    from pyxray import output as out
    from pyxray.analysis import compute_in_degrees, reachable_from

    graph = ctx.get_graph()
    ctx.emit_warnings()

    in_deg = compute_in_degrees(graph)
    top_n = args.top
    limit = getattr(args, "limit", None)

    ranked = sorted(in_deg.items(), key=lambda x: -x[1])
    if top_n:
        ranked = ranked[:top_n]

    # Apply --limit (R8)
    truncated = 0
    if limit and limit > 0 and len(ranked) > limit:
        truncated = len(ranked) - limit
        ranked = ranked[:limit]

    if ctx.json_output:
        out.print_json(
            {"hotspots": [{"package": k, "dependents": v} for k, v in ranked]}
        )
        return 0

    out.section(f"Dependency Hotspots (top {top_n or len(ranked)})")
    out.println(
        out.dim("  Packages with the most reverse dependencies (in-degree).")
        + out.dim("  Risk = dependents × (1 + subtree_size)")
    )
    out.println()

    if not ranked:
        out.println(out.dim("  (empty graph)"))
        return 0

    max_count = ranked[0][1] if ranked else 1
    bar_width = 20

    for norm_name, count in ranked:
        if count == 0:
            break
        pkg = graph.packages.get(norm_name)
        ver = out.dim(f" {pkg.version}") if pkg else ""
        bar_len = int(bar_width * count / max(max_count, 1))
        bar = out.cyan("█" * bar_len) + out.dim("░" * (bar_width - bar_len))

        # R4: subtree size (number of packages this one transitively pulls in, excluding self)
        subtree_size = len(reachable_from(graph, norm_name)) - 1
        risk = count * (1 + subtree_size)

        out.println(f"  {out.cyan(norm_name)}{ver}")
        out.println(
            f"  {bar}  {out.bold(str(count))} dependents  "
            f"{out.dim(f'subtree: {subtree_size}  risk: {risk}')}"
        )
        out.println()

    if truncated:
        out.println(out.dim(f"  … and {truncated} more"))

    return 0
