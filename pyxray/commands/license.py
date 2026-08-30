from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyxray.cli import Context



def _normalise_license(raw: str) -> str:
    """Normalise a freeform license string to a canonical SPDX-ish identifier."""
    key = raw.strip().lower()
    return _LICENSE_ALIASES.get(key, raw.strip() or "Unknown")

def _get_package_license(norm_name: str) -> str:
    """Return the license string for an installed package, or 'Unknown'."""
    try:
        import importlib.metadata as im
        meta = im.metadata(norm_name)
        # Python 3.12+ has License-Expression (SPDX); prefer it
        lic = meta.get("License-Expression") or meta.get("License") or ""
        if lic:
            return _normalise_license(lic)
    except Exception:
        pass
    return "Unknown"

def cmd_license(ctx: Context, args: argparse.Namespace) -> int:
    """Display a license inventory across all packages in the graph."""
    from pyxray import output as out

    graph = ctx.get_graph()
    ctx.emit_warnings()

    show_packages = getattr(args, "show_packages", False)

    # Gather license for each package
    license_map: dict[str, list[str]] = {}  # {license_id → [norm_names]}
    for norm_name in sorted(graph.packages):
        lic = _get_package_license(norm_name)
        license_map.setdefault(lic, []).append(norm_name)

    total = sum(len(v) for v in license_map.values())
    sorted_licenses = sorted(license_map.items(), key=lambda x: -len(x[1]))

    if ctx.json_output:
        out.print_json(
            {
                "total_packages": total,
                "licenses": {k: v for k, v in sorted_licenses},
            }
        )
        return 0

    project = ctx.get_project()
    out.section(f"License Inventory \u2014 {project.name}")
    out.println(f"  {total} packages analysed\n")

    bar_width = 18
    max_count = sorted_licenses[0][1].__len__() if sorted_licenses else 1

    for lic_id, pkgs in sorted_licenses:
        count = len(pkgs)
        bar_len = int(bar_width * count / max(max_count, 1))
        bar = out.cyan("\u2588" * bar_len) + out.dim("\u2591" * (bar_width - bar_len))
        flag = "  " + out.red("\u2190 review") if lic_id == "Unknown" else ""
        out.println(f"  {lic_id:<22} {out.bold(str(count)):>4} packages  {bar}{flag}")
        if show_packages:
            for pkg in pkgs:
                ver = graph.packages[pkg].version if pkg in graph.packages else "?"
                out.println(f"      {out.dim(f'{pkg} {ver}')}")

    out.println()
    return 0
