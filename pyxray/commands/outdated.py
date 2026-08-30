from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyxray.cli import Context



def _compare_versions(installed_ver: str, latest_ver: str) -> tuple[str, bool]:
    from pyxray.commands.compare import _semver_tuple, _version_delta
    """
    Compare two version strings.
    Returns (delta_type, is_outdated).
    delta_type is 'major', 'minor', or 'patch'.
    """
    iv = _semver_tuple(installed_ver)
    lv = _semver_tuple(latest_ver)
    if lv <= iv:
        return "patch", False
    delta = _version_delta(installed_ver, latest_ver)
    return delta, True

_DELTA_RANK = {"patch": 0, "minor": 1, "major": 2}

def cmd_outdated(ctx: Context, args: argparse.Namespace) -> int:
    """Compare installed/locked versions against PyPI latest."""
    from pyxray import output as out
    from pyxray.pypi import fetch_latest_version

    graph = ctx.get_graph()
    ctx.emit_warnings()
    project = ctx.get_project()

    top_n = getattr(args, "top", None)
    min_delta = getattr(args, "min_delta", "patch")
    min_rank = _DELTA_RANK.get(min_delta, 0)

    packages = [
        (norm, pkg)
        for norm, pkg in graph.packages.items()
        if pkg.version and pkg.version != "?"
    ]

    if not ctx.json_output:
        out.section(f"Outdated Packages \u2014 {project.name}")
        out.println(
            f"  {out.dim(f'Checking {len(packages)} packages against PyPI...')}\n"
        )

    outdated: list[tuple[str, str, str, str]] = []  # (norm, installed, latest, delta)

    for i, (norm, pkg) in enumerate(packages):
        latest = fetch_latest_version(norm, verbose=ctx.verbose)
        if not latest:
            continue
        delta, is_out = _compare_versions(pkg.version, latest)
        if is_out and _DELTA_RANK.get(delta, 0) >= min_rank:
            outdated.append((norm, pkg.version, latest, delta))
        # Progress dot every 20 packages
        if not ctx.json_output and not ctx.quiet and (i + 1) % 20 == 0:
            import sys as _sys
            print(f"  ... {i+1}/{len(packages)} checked", file=_sys.stderr)

    # Sort by delta severity desc, then alpha
    outdated.sort(key=lambda x: (-_DELTA_RANK.get(x[3], 0), x[0]))

    if top_n:
        outdated = outdated[:top_n]

    if ctx.json_output:
        out.print_json(
            {
                "project": project.name,
                "total_checked": len(packages),
                "outdated_count": len(outdated),
                "outdated": [
                    {"package": n, "installed": iv, "latest": lv, "delta": d}
                    for n, iv, lv, d in outdated
                ],
            }
        )
        return 0

    if not outdated:
        out.print_ok(f"All {len(packages)} packages are up to date.")
        out.println()
        return 0

    # Header
    out.println(
        f"  {'Package':<30} {'Installed':<14} {'Latest':<14} {'Delta'}"
    )
    out.println(f"  {'-'*30} {'-'*14} {'-'*14} {'-'*10}")

    delta_color = {"major": out.red, "minor": out.yellow, "patch": out.dim}
    arrow = "\u2191"

    for norm, iv, lv, delta in outdated:
        color = delta_color.get(delta, out.dim)
        out.println(
            f"  {out.cyan(norm):<30} {out.dim(iv):<14} {color(lv):<14} "
            f"{color(f'{arrow} {delta}')}"
        )

    out.println(
        f"\n  {out.bold(str(len(outdated)))} outdated of "
        f"{len(packages)} checked."
    )
    out.println()
    return 0
