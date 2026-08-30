from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyxray.cli import Context



def cmd_longest_chain(ctx: Context, args: argparse.Namespace) -> int:
    from pyxray import output as out
    from pyxray.analysis import find_cycles, find_longest_chain
    from pyxray.output import render_path

    graph = ctx.get_graph()
    ctx.emit_warnings()

    cycles = find_cycles(graph)
    chain = find_longest_chain(graph, cycles=cycles)

    if ctx.json_output:
        out.print_json(
            {
                "longest_chain": chain,
                "length": len(chain),
                "has_cycles": bool(cycles),
            }
        )
        return 0

    out.section("Longest Dependency Chain")

    if cycles:
        out.print_warn(
            f"Graph has {len(cycles)} cycle(s). Longest chain is approximate "
            "(cycle-safe DFS, not true longest path)."
        )
        out.println()

    if not chain:
        out.println(out.dim("  (empty graph)"))
        return 0

    out.println(f"  Chain length: {out.bold(str(len(chain)))} packages")
    out.println()

    def pkg_display(n: str) -> str:
        pkg = graph.packages.get(n)
        ver = out.dim(f" ({pkg.version})") if pkg else ""
        return out.cyan(n) + ver

    for line in render_path(chain, display_fn=pkg_display):
        out.println("  " + line)

    out.println()
    return 0
