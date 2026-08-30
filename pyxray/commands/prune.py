from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyxray.cli import Context



def cmd_prune(ctx: Context, args: argparse.Namespace) -> int:
    from pyxray import output as out
    from pyxray.analysis import compute_prune_candidates
    from pyxray.hints import get_hint  # R3
    from pyxray.source import build_import_map, scan_with_usage

    project = ctx.get_project()
    graph = ctx.get_graph()
    installed = ctx.get_installed()
    ctx.emit_warnings()

    import_map = build_import_map({**installed, **graph.packages})
    _, usage_map, warnings = scan_with_usage(
        project.source_roots, project.root, import_map
    )
    for w in warnings:
        out.print_warn(w)

    from pyxray.models import normalize_name

    project_norm = normalize_name(project.name)

    candidates = [
        c
        for c in compute_prune_candidates(
            graph,
            usage_map,
            thin_threshold=args.thin,
            narrow_threshold=args.narrow,
            shallow_threshold=args.shallow,
        )
        if c.norm_name != project_norm
    ]

    if ctx.json_output:
        out.print_json(
            {
                "candidates": [
                    {
                        "package": c.norm_name,
                        "version": c.version,
                        "label": c.label,
                        "confidence": c.confidence,
                        "reason": c.reason,
                        "transitive_count": c.transitive_count,
                        "file_count": c.file_count,
                        "symbol_count": c.symbol_count,
                        "symbols_used": c.symbols_used,
                        "files_using": c.files_using,
                    }
                    for c in candidates
                ]
            }
        )
        return 0

    out.section(f"Prune Candidates — {project.name}")

    if not candidates:
        out.println("  No declared dependencies to analyze.")
        return 0

    for c in candidates:
        if c.label == "REIMPLEMENT":
            color = out.cyan
            icon = "✎"
        elif c.label == "REMOVE":
            color = out.red
            icon = "✗"
        elif c.label == "UNDECLARE":
            color = out.yellow
            icon = "⚠"
        elif c.label == "COVERED":
            color = out.magenta
            icon = "↎"
        else:
            color = out.dim
            icon = "✓"

        ver = out.dim(f" ({c.version})")
        out.println(
            f"  {color(icon)} {out.bold(c.norm_name)}{ver}  —  {color(c.label)}"
        )
        out.println(f"      Confidence: {c.confidence}")

        # Word wrap the reason
        import textwrap

        for line in textwrap.wrap(c.reason, width=70):
            out.println(f"      {line}")

        # R3: stdlib replacement hint for REIMPLEMENT candidates
        if c.label == "REIMPLEMENT":
            hint = get_hint(c.norm_name)
            out.println(f"      {out.green('Suggestion:')} {hint}")

        out.println()

    return 0
