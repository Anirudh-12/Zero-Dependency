from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyxray.cli import Context



def cmd_duplicates(ctx: Context, args: argparse.Namespace) -> int:
    from pyxray import output as out
    from pyxray.analysis import find_duplicate_versions

    graph = ctx.get_graph()
    installed = ctx.get_installed()
    ctx.emit_warnings()

    dupes = find_duplicate_versions(installed, graph)

    if ctx.json_output:
        out.print_json({"duplicates": {k: v for k, v in sorted(dupes.items())}})
        return 0

    out.section("Duplicate Package Versions")

    if not dupes:
        out.print_ok("No duplicate versions detected.")
        return 0

    for norm_name in sorted(dupes):
        versions = dupes[norm_name]
        out.println(f"  {out.cyan(norm_name)}")
        for v in versions:
            out.println(f"    {out.dim('•')} {v}")
        out.println()

    return 0
