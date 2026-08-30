from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyxray.cli import Context



def cmd_unused_extras(ctx: Context, args: argparse.Namespace) -> int:
    """Find declared extras whose sub-dependencies are never imported in source."""
    from pyxray import output as out
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

    # Find declared requirements with extras
    extras_reqs = [r for r in project.declared if r.extras]

    results: list[dict] = []

    for req in extras_reqs:
        pkg = installed.get(req.normalized_name) or graph.packages.get(req.normalized_name)
        if not pkg:
            continue

        for extra in sorted(req.extras):
            # Find sub-deps activated by this extra
            extra_sub_deps: list[str] = []
            for dep_req in pkg.requires:
                if not dep_req.marker:
                    continue
                marker = dep_req.marker
                # Check if marker references this extra
                if f'extra == "{extra}"' in marker or f"extra == '{extra}'" in marker:
                    if dep_req.normalized_name:
                        extra_sub_deps.append(dep_req.normalized_name)

            if not extra_sub_deps:
                continue

            # Check which sub-deps are actually used in source
            used = [d for d in extra_sub_deps if usage_map.get(d)]
            unused = [d for d in extra_sub_deps if d not in used]

            results.append(
                {
                    "package": req.normalized_name,
                    "extra": extra,
                    "sub_deps": extra_sub_deps,
                    "used": used,
                    "unused": unused,
                    "wasteful": len(unused) > 0 and len(used) == 0,
                }
            )

    if ctx.json_output:
        out.print_json({"project": project.name, "extras": results})
        return 0

    out.section(f"Unused Extras \u2014 {project.name}")

    if not extras_reqs:
        out.println(out.dim("  No dependencies with extras declared."))
        out.println()
        return 0

    if not results:
        out.println(out.dim("  No extra sub-dependency information available."))
        out.println(out.dim("  (Extras analysis requires installed packages with markers)"))
        out.println()
        return 0

    wasteful = [r for r in results if r["wasteful"]]
    clean = [r for r in results if not r["wasteful"]]

    for r in wasteful:
        warning_icon = out.red('\u26a0')
        out.println(
            f"  {warning_icon} {out.bold(r['package'])}[{r['extra']}]  "
            f"{out.dim('— all sub-deps unused in source')}"
        )
        out.println(f"      Extra pulls in:  {', '.join(r['sub_deps'])}")
        out.println(f"      Source uses:     {out.red('none')}")
        out.println(f"      {out.yellow('Consider removing:')} {r['package']}[{r['extra']}]")
        out.println()

    for r in clean:
        used_count = len(r["used"])
        sub_deps_count = len(r["sub_deps"])
        check_icon = out.green('\u2713')
        out.println(
            f"  {check_icon} {out.bold(r['package'])}[{r['extra']}]  "
            f"{out.dim(f'{used_count}/{sub_deps_count} sub-dep(s) used')}"
        )

    if not wasteful:
        out.println()
        out.print_ok("No wasteful extras detected.")

    out.println()
    return 0
