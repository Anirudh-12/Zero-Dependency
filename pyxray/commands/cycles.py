from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyxray.cli import Context



def cmd_cycles(ctx: Context, args: argparse.Namespace) -> int:
    from pyxray import output as out
    from pyxray.analysis import find_cycles
    from pyxray.output import render_path

    graph = ctx.get_graph()
    ctx.emit_warnings()

    cycles = find_cycles(graph)

    if ctx.json_output:
        out.print_json({"cycles": cycles, "cycle_count": len(cycles)})
        return 0

    out.section("Circular Dependencies")

    if not cycles:
        out.print_ok("No dependency cycles detected.")
        return 0

    out.println(out.yellow(f"  {len(cycles)} cycle(s) detected:"))
    out.println()

    for i, cycle in enumerate(cycles, 1):
        out.println(out.bold(f"  Cycle {i}"))
        for line in render_path(cycle):
            out.println("    " + line)
        out.println()

    return 0
