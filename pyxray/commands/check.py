from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyxray.cli import Context



def cmd_check(ctx: Context, args: argparse.Namespace) -> int:
    """CI pass/fail gate: fail on cycles, missing packages, or excessive depth."""
    from pyxray import output as out
    from pyxray.analysis import compute_stats

    graph = ctx.get_graph()
    ctx.emit_warnings()
    stats = compute_stats(graph)

    cycles = stats["cycle_count"]
    missing = stats["missing_packages"]
    depth = stats["maximum_depth"]
    max_depth = getattr(args, "max_depth", 10)
    allow_cycles = getattr(args, "allow_cycles", False)
    allow_missing = getattr(args, "allow_missing", False)

    project = ctx.get_project()

    checks: list[tuple[str, bool, str]] = []  # (name, passed, detail)
    if not allow_cycles:
        passed = cycles == 0
        checks.append(("cycles", passed, f"{cycles} cycle(s) detected" if not passed else "0 cycles"))
    if not allow_missing:
        passed = missing == 0
        checks.append(("missing", passed, f"{missing} missing package(s)" if not passed else "0 missing packages"))

    depth_passed = depth <= max_depth
    checks.append(("depth", depth_passed, f"{depth} (limit: {max_depth})"))

    all_passed = all(p for _, p, _ in checks)

    if ctx.json_output:
        out.print_json(
            {
                "project": project.name,
                "passed": all_passed,
                "checks": [
                    {"name": n, "passed": p, "detail": d} for n, p, d in checks
                ],
            }
        )
        return 0 if all_passed else 1

    out.section(f"Dependency Health Check \u2014 {project.name}")
    for name, passed, detail in checks:
        icon = out.green("\u2713") if passed else out.red("\u2717")
        out.println(f"  {icon}  {name:<14} {detail}")

    out.println()
    if all_passed:
        out.print_ok("All checks passed.")
        result_str = out.green(out.bold("PASS"))
    else:
        failed = sum(1 for _, p, _ in checks if not p)
        result_str = out.red(out.bold("FAIL"))
        out.println(f"  Result: {result_str}  ({failed} check(s) failed)")

    out.println()
    return 0 if all_passed else 1
