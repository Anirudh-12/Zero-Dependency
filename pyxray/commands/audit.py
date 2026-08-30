from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyxray.cli import Context



def _is_test_file(path: str) -> bool:
    """Return True if *path* looks like a test file."""
    from pathlib import PurePosixPath
    p = PurePosixPath(path.replace("\\", "/"))
    name = p.stem.lower()
    if name.startswith("test_") or name.endswith("_test"):
        return True
    return any(part.lower() in _TEST_SEGMENTS for part in p.parts)

def cmd_audit(ctx: Context, args: argparse.Namespace) -> int:
    from pyxray import output as out
    from pyxray.models import normalize_name
    from pyxray.source import build_import_map, classify_imports, scan_with_usage

    project = ctx.get_project()
    graph = ctx.get_graph()
    installed = ctx.get_installed()
    ctx.emit_warnings()

    limit = getattr(args, "limit", None)

    import_map = build_import_map({**installed, **graph.packages})
    all_imports, usage_map, warnings = scan_with_usage(
        project.source_roots, project.root, import_map
    )
    for w in warnings:
        out.print_warn(w)

    third_party_detected, stdlib_found, unknown = classify_imports(
        all_imports, import_map
    )

    declared_norms = {normalize_name(r.name) for r in project.declared if r.name}

    # Potentially unused: declared but no static import detected
    potentially_unused = declared_norms - third_party_detected

    # Potentially undeclared: detected third-party but not declared
    potentially_undeclared = third_party_detected - declared_norms

    if ctx.json_output:
        # Gather file locations for undeclared
        undeclared_locs: dict[str, list[str]] = {}
        for imp in all_imports:
            mapped = import_map.get(imp.module)
            if mapped and mapped in potentially_undeclared:
                undeclared_locs.setdefault(mapped, []).append(f"{imp.file}:{imp.line}")

        out.print_json(
            {
                "declared_count": len(declared_norms),
                "detected_third_party": len(third_party_detected),
                "potentially_unused": sorted(potentially_unused),
                "potentially_undeclared": {
                    k: v for k, v in sorted(undeclared_locs.items())
                },
            }
        )
        return 0

    out.section(f"Dependency Audit — {project.name}")
    out.println(f"  {'Declared dependencies':<35} {out.bold(str(len(declared_norms)))}")
    out.println(
        f"  {'Third-party imports detected':<35} {out.bold(str(len(third_party_detected)))}"
    )
    out.println(
        f"  {'Potentially unused declarations':<35} {out.bold(str(len(potentially_unused)))}"
    )
    out.println(
        f"  {'Potentially undeclared imports':<35} {out.bold(str(len(potentially_undeclared)))}"
    )

    if potentially_unused:
        out.println()
        out.println(
            out.yellow("  ⚠  Declared but no static import detected")
            + out.dim(
                "  (may use dynamic imports, entry points, or be a transitive dep)"
            )
        )
        for norm in sorted(potentially_unused):
            pkg = installed.get(norm)
            ver = out.dim(f" {pkg.version}") if pkg else ""
            out.println(f"    {out.yellow('•')} {norm}{ver}")

    if potentially_undeclared:
        out.println()
        out.println(
            out.red("  ✗  Imported but not in declared dependencies")
            + out.dim("  (may be a transitive dep being imported directly)")
        )
        # Build location index
        locs: dict[str, list[str]] = {}
        for imp in all_imports:
            mapped = import_map.get(imp.module)
            if mapped and mapped in potentially_undeclared:
                locs.setdefault(mapped, []).append(f"{imp.file}:{imp.line}")

        # R2: tag each undeclared import as [production] or [test only]
        undeclared_sorted = sorted(potentially_undeclared)
        # Apply --limit (R8)
        truncated = 0
        if limit and limit > 0 and len(undeclared_sorted) > limit:
            truncated = len(undeclared_sorted) - limit
            undeclared_sorted = undeclared_sorted[:limit]

        for norm in undeclared_sorted:
            pkg_locs = locs.get(norm, [])
            all_test = all(_is_test_file(loc.split(":")[0]) for loc in pkg_locs) if pkg_locs else False
            tag = out.dim(" [test only]") if all_test else out.yellow(" [production]")
            out.println(f"    {out.red('•')} {norm}{tag}")
            for loc in pkg_locs[:5]:  # cap at 5 locations per package
                out.println(f"        {out.dim(loc)}")

        if truncated:
            out.println(out.dim(f"  … and {truncated} more (remove --limit to see all)"))

    if not potentially_unused and not potentially_undeclared:
        out.println()
        out.print_ok("Declared dependencies match detected imports.")

    out.println()
    out.println(
        out.dim(
            "  Note: Static analysis cannot detect dynamic imports "
            "(importlib.import_module, __import__, etc.)"
        )
    )
    out.println()
    return 0
