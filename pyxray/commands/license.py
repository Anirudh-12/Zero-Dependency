from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyxray.cli import Context


_LICENSE_ALIASES: dict[str, str] = {
    "mit license": "MIT",
    "the mit license": "MIT",
    "mit": "MIT",
    "apache software license": "Apache-2.0",
    "apache 2.0": "Apache-2.0",
    "apache-2.0": "Apache-2.0",
    "apache license 2.0": "Apache-2.0",
    "apache license, version 2.0": "Apache-2.0",
    "bsd license": "BSD",
    "bsd 3-clause license": "BSD-3-Clause",
    "bsd-3-clause": "BSD-3-Clause",
    "new bsd license": "BSD-3-Clause",
    "bsd 2-clause license": "BSD-2-Clause",
    "bsd-2-clause": "BSD-2-Clause",
    "simplified bsd": "BSD-2-Clause",
    "gpl": "GPL",
    "gplv2": "GPL-2.0",
    "gplv3": "GPL-3.0",
    "gnu general public license v2 (gplv2)": "GPL-2.0",
    "gnu general public license v3 (gplv3)": "GPL-3.0",
}


def _normalise_license(raw: str) -> str:
    """Normalise a freeform license string to a canonical SPDX-ish identifier."""
    key = raw.strip().lower()
    return _LICENSE_ALIASES.get(key, raw.strip() or "Unknown")


def _get_package_license(norm_name: str) -> str:
    """Return the license string for an installed package, or 'Unknown'."""
    try:
        import importlib.metadata as im

        meta = im.metadata(norm_name)

        # 1. Try License-Expression (PEP 639)
        lic_expr = meta.get("License-Expression")
        if lic_expr:
            return _normalise_license(lic_expr)

        # 2. Try Classifiers
        classifiers = meta.get_all("Classifier") or []
        for c in classifiers:
            if c.startswith("License :: OSI Approved :: "):
                return _normalise_license(c.split("::")[-1].strip())
            elif c.startswith("License :: "):
                return _normalise_license(c.split("::")[-1].strip())

        # 3. Try License field (but only if it's a short string, not full text)
        lic = meta.get("License") or ""
        if lic and len(lic) < 150:
            return _normalise_license(lic)

        # 4. Fallback if License is full text but contains keywords
        if lic:
            if "MIT License" in lic or "The MIT License" in lic or "MIT" in lic[:50]:
                return "MIT"
            if "Apache License" in lic or "Apache-2.0" in lic:
                return "Apache-2.0"
            if "BSD" in lic[:50]:
                return "BSD"

    except im.PackageNotFoundError:
        pass
    return "Unknown"


def cmd_license(ctx: Context, args: argparse.Namespace) -> int:
    """Display a license inventory across all packages in the graph."""
    from pyxray import output as out

    graph = ctx.get_graph()
    ctx.emit_warnings()

    show_packages = getattr(args, "show_packages", False)

    # Gather license for each package locally
    license_map: dict[str, list[str]] = {}  # {license_id → [norm_names]}
    unknown_pkgs = []

    for norm_name in sorted(graph.packages):
        lic = _get_package_license(norm_name)
        if lic == "Unknown":
            unknown_pkgs.append(norm_name)
        else:
            license_map.setdefault(lic, []).append(norm_name)

    if unknown_pkgs:
        import concurrent.futures
        import json
        import urllib.request

        from pyxray.pypi import PYPI_BASE

        def fetch_pypi_license(name: str) -> str:
            url = f"{PYPI_BASE}/{name}/json"
            try:
                with urllib.request.urlopen(url, timeout=5) as resp:
                    info = json.loads(resp.read()).get("info", {})

                lic_expr = info.get("license_expression")
                if lic_expr:
                    return _normalise_license(lic_expr)

                for c in info.get("classifiers", []):
                    if c.startswith("License :: OSI Approved :: "):
                        return _normalise_license(c.split("::")[-1].strip())
                    elif c.startswith("License :: "):
                        return _normalise_license(c.split("::")[-1].strip())

                lic = info.get("license") or ""
                if lic and len(lic) < 150:
                    return _normalise_license(lic)

                if lic:
                    if (
                        "MIT License" in lic
                        or "The MIT License" in lic
                        or "MIT" in lic[:50]
                    ):
                        return "MIT"
                    if "Apache License" in lic or "Apache-2.0" in lic:
                        return "Apache-2.0"
                    if "BSD" in lic[:50]:
                        return "BSD"
            except Exception:
                pass
            return "Unknown"

        if not ctx.json_output:
            out.print_err(
                out.dim(
                    f"  Fetching licenses for {len(unknown_pkgs)} uninstalled packages from PyPI..."
                )
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            future_to_pkg = {
                executor.submit(fetch_pypi_license, pkg): pkg for pkg in unknown_pkgs
            }
            for future in concurrent.futures.as_completed(future_to_pkg):
                pkg = future_to_pkg[future]
                lic = future.result()
                license_map.setdefault(lic, []).append(pkg)

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
