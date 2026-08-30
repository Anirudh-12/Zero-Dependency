from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyxray.cli import Context



def cmd_impact(ctx: Context, args: argparse.Namespace) -> int:
    from pyxray import output as out
    from pyxray.analysis import compute_depths, reachable_reverse
    from pyxray.models import normalize_name

    package = args.package
    norm = normalize_name(package)
    expand_all = getattr(args, "all", False)
    limit = getattr(args, "limit", None)

    graph = ctx.get_graph()
    ctx.emit_warnings()

    if norm not in graph.packages:
        out.print_err(f"'{package}' is not in the dependency graph.")
        return 1

    affected = reachable_reverse(graph, norm)

    pkg = graph.packages.get(norm)
    ver_str = f" ({pkg.version})" if pkg else ""

    if ctx.json_output:
        out.print_json(
            {
                "package": norm,
                "version": pkg.version if pkg else "?",
                "affected_count": len(affected),
                "affected": sorted(affected),
            }
        )
        return 0

    out.section(f"Impact of '{package}'{ver_str}")
    out.println(
        f"  If '{out.cyan(package)}' disappeared, "
        f"{out.bold(str(len(affected)))} package(s) would be affected:"
    )
    out.println()

    if not affected:
        out.println(out.dim("  (nothing depends on this package)"))
        return 0

    # R1: group by hop distance from the target package using reverse-graph depths
    # depth[dep] - depth[norm] gives approximate hop distance.
    depths = compute_depths(graph)
    norm_depth = depths.get(norm, 0)

    def _hop(dep: str) -> int:
        d = depths.get(dep, norm_depth)
        diff = d - norm_depth
        return max(diff, 1)  # at least 1 hop

    # Sort affected: hop ascending, then alpha
    sorted_affected = sorted(affected, key=lambda d: (_hop(d), d))

    # Apply --limit (R8)
    display_affected = sorted_affected
    truncated = 0
    if limit and limit > 0 and len(sorted_affected) > limit:
        display_affected = sorted_affected[:limit]
        truncated = len(sorted_affected) - limit

    # Render grouped by hop band
    current_band: int | None = None
    band_labels = {1: "Direct dependents", 2: "2 hops", 3: "3+ hops (deep transitive)"}
    deep_threshold = 3

    rendered_in_deep = 0
    total_deep = sum(1 for d in sorted_affected if _hop(d) >= deep_threshold)

    for dep in display_affected:
        hop = _hop(dep)
        band = min(hop, deep_threshold)
        if band != current_band:
            current_band = band
            label = band_labels.get(band, f"{band}+ hops")
            count = sum(1 for d in sorted_affected if min(_hop(d), deep_threshold) == band)
            out.println(
                f"  {out.bold(label):<38} {out.dim(f'── {count} package(s)')}"
            )
        if band >= deep_threshold and not expand_all:
            rendered_in_deep += 1
            if rendered_in_deep == 1:
                # Show count summary instead of listing
                out.println(
                    f"    {out.dim(f'{total_deep} package(s)  (use --all to expand)')}"
                )
            continue  # skip individual lines unless --all

        pkg_d = graph.packages.get(dep)
        ver = out.dim(f" {pkg_d.version}") if pkg_d else ""
        marker = out.green("  ⊕ root ") if dep in graph.roots else "       "
        out.println(f"  {marker} {out.cyan(dep)}{ver}")

    if truncated:
        out.println(out.dim(f"  … and {truncated} more (remove --limit to see all)"))

    out.println()
    return 0
