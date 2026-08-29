"""
cli.py — Argument parsing and command dispatch for PyXRay.

Uses only: argparse (stdlib)
Replaces: click, typer, docopt
"""

from __future__ import annotations

import argparse
import sys
from typing import Optional


# ---------------------------------------------------------------------------
# Shared context (loaded once, shared across commands)
# ---------------------------------------------------------------------------

class Context:
    """Lazy-loaded analysis context shared across subcommands."""

    def __init__(
        self,
        project_root: Optional[str],
        no_color: bool,
        json_output: bool,
        quiet: bool,
    ) -> None:
        self.project_root = project_root
        self.json_output = json_output
        self.quiet = quiet
        self._project = None
        self._installed = None
        self._graph = None
        self._warnings: list[str] = []
        self._graph_built = False

        # Configure output layer
        from pyxray import output as out
        out.set_color(not no_color)

    # ------------------------------------------------------------------
    # Lazy loaders
    # ------------------------------------------------------------------

    def get_installed(self) -> dict:
        if self._installed is None:
            from pyxray.metadata import discover_all_installed
            self._installed = discover_all_installed()
        return self._installed

    def get_project(self):
        if self._project is None:
            from pyxray.manifest import discover_project
            self._project, warnings = discover_project(self.project_root)
            self._warnings.extend(warnings)
        return self._project

    def get_graph(self):
        if not self._graph_built:
            from pyxray.graph import build_graph
            project = self.get_project()
            installed = self.get_installed()
            self._graph, warnings = build_graph(project, installed)
            self._warnings.extend(warnings)
            self._graph_built = True
        return self._graph

    def emit_warnings(self) -> None:
        if not self.quiet:
            from pyxray import output as out
            for w in self._warnings:
                out.print_warn(w)
            self._warnings.clear()


# ---------------------------------------------------------------------------
# Command implementations
# ---------------------------------------------------------------------------

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
        ("Direct dependencies",    str(stats["direct_dependencies"])),
        ("Transitive dependencies", str(stats["transitive_dependencies"])),
        ("Total packages",          str(stats["total_packages"])),
        ("",                        ""),
        ("Dependency edges",        str(stats["dependency_edges"])),
        ("Leaf packages",           str(stats["leaf_packages"])),
        ("Maximum depth",           str(stats["maximum_depth"])),
        ("Average depth",           str(stats["average_depth"])),
        ("Cycles detected",         str(stats["cycle_count"])),
        ("Missing packages",        str(stats["missing_packages"])),
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

    if graph.missing and not ctx.quiet:
        out.println()
        out.println(out.yellow("  Missing packages (declared/required but not installed):"))
        for m in sorted(graph.missing):
            out.println(f"    {out.red('✗')} {m}")

    out.println()
    return 0


def cmd_tree(ctx: Context, args: argparse.Namespace) -> int:
    from pyxray import output as out
    from pyxray.output import render_tree

    project = ctx.get_project()
    graph = ctx.get_graph()
    installed = ctx.get_installed()
    ctx.emit_warnings()

    max_depth = args.depth

    def display(norm_name: str) -> str:
        pkg = graph.packages.get(norm_name)
        if pkg:
            ver = out.dim(f" {pkg.version}")
            if norm_name in graph.missing:
                return out.red(norm_name) + out.dim(" [not installed]")
            return out.cyan(norm_name) + ver
        return out.red(norm_name) + out.dim(" [?]")

    if ctx.json_output:
        def build_tree_dict(node: str, seen: set) -> dict:
            if node in seen:
                return {"name": node, "already_shown": True}
            seen.add(node)
            children = sorted(graph.forward.get(node, set()))
            pkg = graph.packages.get(node)
            return {
                "name": node,
                "version": pkg.version if pkg else "?",
                "dependencies": [build_tree_dict(c, seen) for c in children],
            }

        roots = sorted(graph.roots)
        result = {
            "project": project.name,
            "trees": [build_tree_dict(r, set()) for r in roots],
        }
        out.print_json(result)
        return 0

    out.section(f"Dependency Tree — {project.name}")

    if not graph.roots:
        out.println(out.dim("  (no dependencies declared)"))
        return 0

    # Render each root as its own subtree
    for root in sorted(graph.roots):
        lines = render_tree(
            root,
            children_fn=lambda n: sorted(graph.forward.get(n, set())),
            display_fn=display,
            max_depth=max_depth,
        )
        for line in lines:
            out.println("  " + line)
        out.println()

    return 0


def cmd_why(ctx: Context, args: argparse.Namespace) -> int:
    from pyxray import output as out
    from pyxray.analysis import find_reverse_paths
    from pyxray.models import normalize_name

    package = args.package
    norm = normalize_name(package)

    graph = ctx.get_graph()
    ctx.emit_warnings()

    if norm not in graph.packages:
        out.print_err(
            f"'{package}' is not in the dependency graph. "
            f"Is it installed? Try: python -m pyxray summary"
        )
        return 1

    paths = find_reverse_paths(
        graph, target=norm, roots=graph.roots, max_paths=args.max_paths
    )

    pkg = graph.packages.get(norm)
    ver_str = f" ({pkg.version})" if pkg else ""

    if ctx.json_output:
        out.print_json({
            "package": norm,
            "version": pkg.version if pkg else "?",
            "paths": paths,
        })
        return 0

    out.section(f"Why is '{package}' installed?{ver_str}")

    if not paths:
        if norm in graph.roots:
            out.print_ok(f"'{package}' is a direct (root) project dependency.")
        else:
            out.println(out.dim(f"  No path found from project roots to '{package}'."))
            out.println(out.dim("  It may be installed but not reachable from declared dependencies."))
        return 0

    for i, path in enumerate(paths, 1):
        out.println(out.bold(f"\n  Path {i}"))
        pkg_display = lambda n: (
            (graph.packages[n].name if n in graph.packages else n)
            + " " + out.dim(f"({graph.packages[n].version})" if n in graph.packages and graph.packages[n].version != "?" else "")
        )
        from pyxray.output import render_path
        for line in render_path(path, display_fn=pkg_display):
            out.println("    " + line)

    out.println()
    return 0


def cmd_impact(ctx: Context, args: argparse.Namespace) -> int:
    from pyxray import output as out
    from pyxray.analysis import reachable_reverse
    from pyxray.models import normalize_name

    package = args.package
    norm = normalize_name(package)

    graph = ctx.get_graph()
    ctx.emit_warnings()

    if norm not in graph.packages:
        out.print_err(f"'{package}' is not in the dependency graph.")
        return 1

    affected = reachable_reverse(graph, norm)

    pkg = graph.packages.get(norm)
    ver_str = f" ({pkg.version})" if pkg else ""

    if ctx.json_output:
        out.print_json({
            "package": norm,
            "version": pkg.version if pkg else "?",
            "affected_count": len(affected),
            "affected": sorted(affected),
        })
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

    for dep in sorted(affected):
        pkg_d = graph.packages.get(dep)
        ver = out.dim(f" {pkg_d.version}") if pkg_d else ""
        marker = out.green("  ⊕ root ") if dep in graph.roots else "       "
        out.println(f"  {marker} {out.cyan(dep)}{ver}")

    out.println()
    return 0


def cmd_duplicates(ctx: Context, args: argparse.Namespace) -> int:
    from pyxray import output as out
    from pyxray.analysis import find_duplicate_versions

    graph = ctx.get_graph()
    installed = ctx.get_installed()
    ctx.emit_warnings()

    dupes = find_duplicate_versions(installed, graph)

    if ctx.json_output:
        out.print_json({"duplicates": {k: v for k, v in sorted(dupes.items())}})
        return 0

    out.section("Duplicate Package Versions")

    if not dupes:
        out.print_ok("No duplicate versions detected.")
        return 0

    for norm_name in sorted(dupes):
        versions = dupes[norm_name]
        out.println(f"  {out.cyan(norm_name)}")
        for v in versions:
            out.println(f"    {out.dim('•')} {v}")
        out.println()

    return 0


def cmd_cycles(ctx: Context, args: argparse.Namespace) -> int:
    from pyxray import output as out
    from pyxray.analysis import find_cycles
    from pyxray.output import render_path

    graph = ctx.get_graph()
    ctx.emit_warnings()

    cycles = find_cycles(graph)

    if ctx.json_output:
        out.print_json({"cycles": cycles, "cycle_count": len(cycles)})
        return 0

    out.section("Circular Dependencies")

    if not cycles:
        out.print_ok("No dependency cycles detected.")
        return 0

    out.println(out.yellow(f"  {len(cycles)} cycle(s) detected:"))
    out.println()

    for i, cycle in enumerate(cycles, 1):
        out.println(out.bold(f"  Cycle {i}"))
        for line in render_path(cycle):
            out.println("    " + line)
        out.println()

    return 0


def cmd_stats(ctx: Context, args: argparse.Namespace) -> int:
    from pyxray import output as out
    from pyxray.analysis import compute_stats, compute_in_degrees, compute_depths

    project = ctx.get_project()
    graph = ctx.get_graph()
    ctx.emit_warnings()

    stats = compute_stats(graph)
    depths = compute_depths(graph)
    in_deg = compute_in_degrees(graph)

    if ctx.json_output:
        out.print_json({"project": project.name, "stats": stats})
        return 0

    out.section(f"Graph Statistics — {project.name}")

    metrics = [
        ("Packages (total)",          stats["total_packages"],           "nodes"),
        ("Direct dependencies",       stats["direct_dependencies"],      "root nodes"),
        ("Transitive dependencies",   stats["transitive_dependencies"],  "non-root nodes"),
        ("Dependency edges",          stats["dependency_edges"],         "edges"),
        ("Leaf packages",             stats["leaf_packages"],            "no outgoing edges"),
        ("Missing packages",          stats["missing_packages"],         "not installed"),
        ("",                          "",                                ""),
        ("Maximum depth",             stats["maximum_depth"],            "hops from a root"),
        ("Average depth",             stats["average_depth"],            "BFS from roots"),
        ("Maximum fan-out",           stats["maximum_fan_out"],          "direct deps of one package"),
        ("Maximum fan-in",            stats["maximum_fan_in"],           "dependents of one package"),
        ("",                          "",                                ""),
        ("Cycle count",               stats["cycle_count"],              "strongly connected"),
        ("Largest subtree",           f"{stats['largest_subtree_root']} ({stats['largest_subtree_size']} pkgs)", "from one root"),
        ("Most depended upon",        f"{stats['most_depended_upon']} ({stats['most_depended_upon_count']} deps)", "highest in-degree"),
    ]

    for label, value, note in metrics:
        if not label:
            out.println()
            continue
        note_str = out.dim(f"  # {note}") if note else ""
        out.println(f"  {label:<32} {out.bold(str(value)):<20}{note_str}")

    out.println()
    return 0


def cmd_hotspots(ctx: Context, args: argparse.Namespace) -> int:
    from pyxray import output as out
    from pyxray.analysis import compute_in_degrees

    graph = ctx.get_graph()
    ctx.emit_warnings()

    in_deg = compute_in_degrees(graph)
    top_n = args.top

    ranked = sorted(in_deg.items(), key=lambda x: -x[1])
    if top_n:
        ranked = ranked[:top_n]

    if ctx.json_output:
        out.print_json({"hotspots": [{"package": k, "dependents": v} for k, v in ranked]})
        return 0

    out.section(f"Dependency Hotspots (top {top_n or len(ranked)})")
    out.println(out.dim("  Packages with the most reverse dependencies (in-degree)."))
    out.println()

    if not ranked:
        out.println(out.dim("  (empty graph)"))
        return 0

    max_count = ranked[0][1] if ranked else 1
    bar_width = 20

    for norm_name, count in ranked:
        if count == 0:
            break
        pkg = graph.packages.get(norm_name)
        ver = out.dim(f" {pkg.version}") if pkg else ""
        bar_len = int(bar_width * count / max(max_count, 1))
        bar = out.cyan("█" * bar_len) + out.dim("░" * (bar_width - bar_len))
        out.println(f"  {out.cyan(norm_name)}{ver}")
        out.println(f"  {bar}  {out.bold(str(count))} dependents")
        out.println()

    return 0


def cmd_longest_chain(ctx: Context, args: argparse.Namespace) -> int:
    from pyxray import output as out
    from pyxray.analysis import find_cycles, find_longest_chain
    from pyxray.output import render_path

    graph = ctx.get_graph()
    ctx.emit_warnings()

    cycles = find_cycles(graph)
    chain = find_longest_chain(graph, cycles=cycles)

    if ctx.json_output:
        out.print_json({
            "longest_chain": chain,
            "length": len(chain),
            "has_cycles": bool(cycles),
        })
        return 0

    out.section("Longest Dependency Chain")

    if cycles:
        out.print_warn(
            f"Graph has {len(cycles)} cycle(s). Longest chain is approximate "
            "(cycle-safe DFS, not true longest path)."
        )
        out.println()

    if not chain:
        out.println(out.dim("  (empty graph)"))
        return 0

    out.println(f"  Chain length: {out.bold(str(len(chain)))} packages")
    out.println()

    def pkg_display(n: str) -> str:
        pkg = graph.packages.get(n)
        ver = out.dim(f" ({pkg.version})") if pkg else ""
        return out.cyan(n) + ver

    for line in render_path(chain, display_fn=pkg_display):
        out.println("  " + line)

    out.println()
    return 0


def cmd_imports(ctx: Context, args: argparse.Namespace) -> int:
    from pyxray import output as out
    from pyxray.source import scan_source_roots, build_import_map, classify_imports

    project = ctx.get_project()
    installed = ctx.get_installed()
    ctx.emit_warnings()

    all_imports, warnings = scan_source_roots(
        project.source_roots, project.root
    )
    for w in warnings:
        out.print_warn(w)

    import_map = build_import_map(installed)
    third_party, stdlib_found, unknown = classify_imports(all_imports, import_map)

    if ctx.json_output:
        out.print_json({
            "source_roots": project.source_roots,
            "total_imports": len(all_imports),
            "third_party": sorted(third_party),
            "stdlib": sorted(stdlib_found),
            "unknown": sorted(unknown),
        })
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


def cmd_audit(ctx: Context, args: argparse.Namespace) -> int:
    from pyxray import output as out
    from pyxray.source import scan_source_roots, build_import_map, classify_imports
    from pyxray.models import normalize_name

    project = ctx.get_project()
    graph = ctx.get_graph()
    installed = ctx.get_installed()
    ctx.emit_warnings()

    all_imports, warnings = scan_source_roots(
        project.source_roots, project.root
    )
    for w in warnings:
        out.print_warn(w)

    import_map = build_import_map(installed)
    third_party_detected, stdlib_found, unknown = classify_imports(all_imports, import_map)

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
                undeclared_locs.setdefault(mapped, []).append(
                    f"{imp.file}:{imp.line}"
                )

        out.print_json({
            "declared_count": len(declared_norms),
            "detected_third_party": len(third_party_detected),
            "potentially_unused": sorted(potentially_unused),
            "potentially_undeclared": {
                k: v for k, v in sorted(undeclared_locs.items())
            },
        })
        return 0

    out.section(f"Dependency Audit — {project.name}")
    out.println(f"  {'Declared dependencies':<35} {out.bold(str(len(declared_norms)))}")
    out.println(f"  {'Third-party imports detected':<35} {out.bold(str(len(third_party_detected)))}")
    out.println(f"  {'Potentially unused declarations':<35} {out.bold(str(len(potentially_unused)))}")
    out.println(f"  {'Potentially undeclared imports':<35} {out.bold(str(len(potentially_undeclared)))}")

    if potentially_unused:
        out.println()
        out.println(
            out.yellow("  ⚠  Declared but no static import detected")
            + out.dim("  (may use dynamic imports, entry points, or be a transitive dep)")
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

        for norm in sorted(potentially_undeclared):
            out.println(f"    {out.red('•')} {norm}")
            for loc in locs.get(norm, [])[:5]:  # cap at 5 locations
                out.println(f"        {out.dim(loc)}")

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


# ---------------------------------------------------------------------------
# Argument parser construction
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pyxray",
        description=(
            "PyXRay — Python Dependency Investigation Tool\n"
            "Zero third-party runtime dependencies. All analysis is local and deterministic."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python -m pyxray summary\n"
            "  python -m pyxray tree --depth 3\n"
            "  python -m pyxray why requests\n"
            "  python -m pyxray impact typing-extensions\n"
            "  python -m pyxray audit --json\n"
        ),
    )

    parser.add_argument(
        "--root", "-r",
        metavar="DIR",
        default=None,
        help="Project root directory (default: current working directory)",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        default=False,
        help="Disable ANSI color output (also respects NO_COLOR env var)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Output results as JSON",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        default=False,
        help="Suppress warnings",
    )
    parser.add_argument(
        "--version", "-V",
        action="version",
        version="PyXRay 0.1.0",
    )

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    # summary
    p_sum = sub.add_parser("summary", help="Project dependency summary")
    p_sum.set_defaults(func=cmd_summary)

    # tree
    p_tree = sub.add_parser("tree", help="Render dependency tree")
    p_tree.add_argument(
        "--depth", "-d", type=int, default=None,
        help="Maximum tree depth to render",
    )
    p_tree.set_defaults(func=cmd_tree)

    # why
    p_why = sub.add_parser("why", help="Explain why a package is installed")
    p_why.add_argument("package", help="Package name to explain")
    p_why.add_argument(
        "--max-paths", type=int, default=5,
        help="Maximum number of paths to show (default: 5)",
    )
    p_why.set_defaults(func=cmd_why)

    # impact
    p_impact = sub.add_parser("impact", help="Show packages affected if a package disappeared")
    p_impact.add_argument("package", help="Package name to analyse")
    p_impact.set_defaults(func=cmd_impact)

    # duplicates
    p_dup = sub.add_parser("duplicates", help="Detect packages installed with multiple versions")
    p_dup.set_defaults(func=cmd_duplicates)

    # cycles
    p_cyc = sub.add_parser("cycles", help="Detect circular dependencies")
    p_cyc.set_defaults(func=cmd_cycles)

    # stats
    p_stats = sub.add_parser("stats", help="Detailed graph statistics")
    p_stats.set_defaults(func=cmd_stats)

    # hotspots
    p_hot = sub.add_parser("hotspots", help="Packages with the most dependents")
    p_hot.add_argument(
        "--top", "-n", type=int, default=20,
        help="Number of results to show (default: 20)",
    )
    p_hot.set_defaults(func=cmd_hotspots)

    # longest-chain
    p_lc = sub.add_parser("longest-chain", help="Find the longest dependency path")
    p_lc.set_defaults(func=cmd_longest_chain)

    # imports
    p_imp = sub.add_parser("imports", help="Scan source code for import statements")
    p_imp.add_argument(
        "--no-unknown", action="store_true", default=False,
        help="Suppress unclassified import listing",
    )
    p_imp.set_defaults(func=cmd_imports)

    # audit
    p_audit = sub.add_parser(
        "audit",
        help="Compare declared dependencies with detected source imports",
    )
    p_audit.set_defaults(func=cmd_audit)

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    ctx = Context(
        project_root=args.root,
        no_color=args.no_color,
        json_output=args.json,
        quiet=args.quiet,
    )

    try:
        return args.func(ctx, args)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except BrokenPipeError:
        return 0
    except Exception as exc:
        from pyxray import output as out
        out.print_err(f"Unexpected error: {exc}")
        if not ctx.quiet:
            import traceback
            traceback.print_exc(file=sys.stderr)
        return 1
