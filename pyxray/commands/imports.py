from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyxray.cli import Context



def cmd_imports(ctx: Context, args: argparse.Namespace) -> int:
    from pyxray import output as out
    from pyxray.source import build_import_map, classify_imports, scan_with_usage

    project = ctx.get_project()
    graph = ctx.get_graph()
    installed = ctx.get_installed()
    ctx.emit_warnings()

    mapping_packages = {**installed, **graph.packages}
    import_map = build_import_map(mapping_packages)
    all_imports, usage_map, warnings = scan_with_usage(
        project.source_roots, project.root, import_map
    )
    for w in warnings:
        out.print_warn(w)

    third_party, stdlib_found, unknown = classify_imports(all_imports, import_map)

    if ctx.json_output:
        out.print_json(
            {
                "source_roots": project.source_roots,
                "total_imports": len(all_imports),
                "third_party": sorted(third_party),
                "stdlib": sorted(stdlib_found),
                "unknown": sorted(unknown),
            }
        )
        return 0

    out.section(f"Source Import Summary — {project.name}")
    out.println(f"  {'Source roots':<25} {', '.join(project.source_roots) or '(none)'}")
    out.println(f"  {'Total import statements':<25} {out.bold(str(len(all_imports)))}")
    out.println(f"  {'Third-party detected':<25} {out.bold(str(len(third_party)))}")
    out.println(f"  {'Standard library':<25} {out.bold(str(len(stdlib_found)))}")
    out.println(f"  {'Unclassified':<25} {out.bold(str(len(unknown)))}")
    out.println()

    if third_party:
        out.subsection("  Third-party imports detected:")
        for mod in sorted(third_party):
            out.println(f"    {out.cyan('•')} {mod}")

    if unknown and not args.no_unknown:
        out.println()
        out.subsection("  Unclassified imports (may be local, generated, or unknown):")
        for mod in sorted(unknown):
            out.println(f"    {out.dim('?')} {mod}")

    out.println()
    return 0
