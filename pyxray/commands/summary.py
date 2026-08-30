from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyxray.cli import Context



def _compute_health_grade(stats: dict) -> tuple[str, str]:
    """Return (grade, reason) based on graph health signals."""
    cycles = stats["cycle_count"]
    missing = stats["missing_packages"]
    depth = stats["maximum_depth"]

    if cycles > 3 or missing > 5:
        grade = "F"
        reason = f"{cycles} cycle(s), {missing} missing package(s)"
    elif cycles >= 1 or missing > 2:
        grade = "D"
        parts = []
        if cycles:
            parts.append(f"{cycles} cycle(s)")
        if missing > 2:
            parts.append(f"{missing} missing package(s)")
        reason = ", ".join(parts)
    elif missing > 0 or depth > 12:
        grade = "C"
        parts = []
        if missing:
            parts.append(f"{missing} missing package(s)")
        if depth > 12:
            parts.append(f"depth {depth} is very deep")
        reason = ", ".join(parts)
    elif depth > 8:
        grade = "B"
        reason = f"no cycles, 0 missing, depth {depth} is moderate"
    else:
        grade = "A"
        reason = "no cycles, 0 missing, depth OK"
    return grade, reason

def cmd_summary(ctx: Context, args: argparse.Namespace) -> int:
    from pyxray import output as out
    from pyxray.analysis import compute_stats

    project = ctx.get_project()
    graph = ctx.get_graph()
    ctx.emit_warnings()

    stats = compute_stats(graph)

    if ctx.json_output:
        data = {"project": project.name, **stats}
        if graph.missing:
            data["missing_packages"] = sorted(graph.missing)
        out.print_json(data)
        return 0

    out.header()
    out.section(f"Project: {project.name}")

    rows = [
        ("Direct dependencies", str(stats["direct_dependencies"])),
        ("Transitive dependencies", str(stats["transitive_dependencies"])),
        ("Total packages", str(stats["total_packages"])),
        ("", ""),
        ("Dependency edges", str(stats["dependency_edges"])),
        ("Leaf packages", str(stats["leaf_packages"])),
        ("Maximum depth", str(stats["maximum_depth"])),
        ("Average depth", str(stats["average_depth"])),
        ("Cycles detected", str(stats["cycle_count"])),
        ("Missing packages", str(stats["missing_packages"])),
    ]

    for label, value in rows:
        if not label:
            out.println()
            continue
        out.println(f"  {label:<30} {out.bold(value)}")

    if stats["largest_subtree_root"]:
        out.println()
        out.println(
            f"  {'Largest subtree':<30} "
            f"{out.cyan(stats['largest_subtree_root'])} → "
            f"{stats['largest_subtree_size']} packages"
        )

    if stats["most_depended_upon"]:
        out.println(
            f"  {'Most depended upon':<30} "
            f"{out.cyan(stats['most_depended_upon'])} → "
            f"{stats['most_depended_upon_count']} dependents"
        )

    # Health grade (R5)
    grade, reason = _compute_health_grade(stats)
    grade_color = (
        out.green if grade in ("A", "B")
        else out.yellow if grade in ("C", "D")
        else out.red
    )
    out.println(
        f"\n  {'Health':<30} {grade_color(out.bold(grade))}  "
        f"{out.dim(f'({reason})')}"
    )

    if graph.missing and not ctx.quiet:
        out.println()
        out.println(
            out.yellow("  Missing packages (declared/required but not installed):")
        )
        for m in sorted(graph.missing):
            out.println(f"    {out.red('✗')} {m}")

    out.println()
    return 0
