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
        from_lock: Optional[str] = None,
        no_lock: bool = False,
        use_pypi: bool = False,
        max_packages: int = 300,
    ) -> None:
        self.project_root = project_root
        self.json_output = json_output
        self.quiet = quiet
        self.from_lock = from_lock  # explicit lock file path, or None = auto-detect
        self.no_lock = no_lock  # suppress auto-detection
        self.use_pypi = use_pypi  # fetch metadata from PyPI API
        self.max_packages = max_packages  # cap for PyPI BFS
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
            project = self.get_project()
            self._graph_built = True

            # ── Mode 1: explicit lock file path ──────────────────────────
            if self.from_lock:
                from pathlib import Path
                from pyxray.lockfile import build_graph_from_lockfile
                from pyxray import output as out

                lock_path = Path(self.from_lock)
                if not lock_path.exists():
                    out.print_err(f"Lock file not found: {self.from_lock}")
                    self._graph, self._warnings = _empty_graph(), []
                    return self._graph
                declared_norms = {r.normalized_name for r in project.declared if r.name}
                self._graph, warnings = build_graph_from_lockfile(
                    lock_path, declared_norms
                )
                self._warnings.extend(warnings)
                if not self.quiet:
                    out.print_ok(f"Graph loaded from lock file: {lock_path.name}")
                return self._graph

            # ── Mode 2: auto-detect lock file ────────────────────────────
            if not self.use_pypi and not self.no_lock and not self.from_lock:
                from pathlib import Path
                from pyxray.lockfile import detect_lockfile, build_graph_from_lockfile

                root = Path(project.root)
                lock_path = detect_lockfile(str(root))
                if lock_path:
                    from pyxray import output as out

                    declared_norms = {
                        r.normalized_name for r in project.declared if r.name
                    }
                    self._graph, warnings = build_graph_from_lockfile(
                        lock_path, declared_norms
                    )
                    self._warnings.extend(warnings)
                    if not self.quiet:
                        out.print_ok(
                            f"Graph loaded from lock file: {lock_path.name} "
                            f"(pass --no-lock to use installed env instead)"
                        )
                    return self._graph

            # ── Mode 3: PyPI API (explicit --pypi flag) ──────────────────
            if self.use_pypi:
                from pyxray import output as out
                from pyxray.pypi import build_graph_from_pypi

                if not self.quiet:
                    out.print_warn(
                        f"Fetching dependency graph from PyPI "
                        f"(up to {self.max_packages} packages)…"
                    )
                self._graph, warnings = build_graph_from_pypi(
                    project.declared,
                    max_packages=self.max_packages,
                    verbose=not self.quiet,
                )
                self._warnings.extend(warnings)
                return self._graph

            # ── Mode 4: installed environment (default) ──────────────────
            from pyxray.graph import build_graph

            installed = self.get_installed()
            self._graph, warnings = build_graph(project, installed)
            self._warnings.extend(warnings)
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


def cmd_tree(ctx: Context, args: argparse.Namespace) -> int:
    from pyxray import output as out
    from pyxray.output import render_tree
    from pyxray.analysis import compute_in_degrees

    project = ctx.get_project()
    graph = ctx.get_graph()
    ctx.emit_warnings()

    max_depth = args.depth
    sort_by = getattr(args, "sort_by", "alpha")

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

    # R6: build sort key — in-degree proxy for "heaviness"
    if sort_by == "in-degree":
        in_deg = compute_in_degrees(graph)
        def children_fn(n: str) -> list[str]:
            kids = list(graph.forward.get(n, set()))
            # Sort by in-degree descending (most-depended-upon first), then alpha
            return sorted(kids, key=lambda x: (-in_deg.get(x, 0), x))
    else:
        def children_fn(n: str) -> list[str]:
            return sorted(graph.forward.get(n, set()))

    # Render each root as its own subtree
    for root in sorted(graph.roots):
        lines = render_tree(
            root,
            children_fn=children_fn,
            display_fn=display,
            max_depth=max_depth,
        )
        for line in lines:
            out.println("  " + line)
        out.println()

    return 0


def _get_edge_constraint(graph, from_norm: str, to_norm: str) -> str:
    """Return the version specifier string that ties from_norm → to_norm.

    Walks raw_requires of the from package and extracts the specifier portion
    (e.g. '>=0.36.3') for the matching dependency entry. Returns '' if none found.
    """
    from pyxray.requirements import fast_extract_normalized_name
    pkg = graph.packages.get(from_norm)
    if not pkg:
        return ""
    for raw in pkg.raw_requires:
        dep_norm = fast_extract_normalized_name(raw)
        if dep_norm == to_norm:
            # Extract specifier: everything after the first name token
            # raw is like 'starlette>=0.36.3' or 'anyio>=4.0.0,<5'
            # Strip the package name (up to first =/</>/ ;)
            import re
            m = re.match(r"[A-Za-z0-9_\-.]+\s*([^;]*)", raw)
            if m:
                spec = m.group(1).strip().split(";")[0].strip()
                return spec
    return ""


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
        out.print_json(
            {
                "package": norm,
                "version": pkg.version if pkg else "?",
                "paths": paths,
            }
        )
        return 0

    out.section(f"Why is '{package}' installed?{ver_str}")

    if not paths:
        if norm in graph.roots:
            out.print_ok(f"'{package}' is a direct (root) project dependency.")
        else:
            out.println(out.dim(f"  No path found from project roots to '{package}'."))
            out.println(
                out.dim(
                    "  It may be installed but not reachable from declared dependencies."
                )
            )
        return 0

    for i, path in enumerate(paths, 1):
        out.println(out.bold(f"\n  Path {i}"))

        def pkg_display(n: str) -> str:
            return (
                (graph.packages[n].name if n in graph.packages else n)
                + " "
                + out.dim(
                    f"({graph.packages[n].version})"
                    if n in graph.packages and graph.packages[n].version != "?"
                    else ""
                )
            )

        # R7: edge_label_fn shows version constraint between hops
        def edge_label_fn(from_n: str, to_n: str) -> str:
            return _get_edge_constraint(graph, from_n, to_n)

        from pyxray.output import render_path

        for line in render_path(path, display_fn=pkg_display, edge_label_fn=edge_label_fn):
            out.println("    " + line)

    out.println()
    return 0


def cmd_impact(ctx: Context, args: argparse.Namespace) -> int:
    from pyxray import output as out
    from pyxray.analysis import reachable_reverse, compute_depths
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
    current_band: Optional[int] = None
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
        ("Packages (total)", stats["total_packages"], "nodes"),
        ("Direct dependencies", stats["direct_dependencies"], "root nodes"),
        ("Transitive dependencies", stats["transitive_dependencies"], "non-root nodes"),
        ("Dependency edges", stats["dependency_edges"], "edges"),
        ("Leaf packages", stats["leaf_packages"], "no outgoing edges"),
        ("Missing packages", stats["missing_packages"], "not installed"),
        ("", "", ""),
        ("Maximum depth", stats["maximum_depth"], "hops from a root"),
        ("Average depth", stats["average_depth"], "BFS from roots"),
        ("Maximum fan-out", stats["maximum_fan_out"], "direct deps of one package"),
        ("Maximum fan-in", stats["maximum_fan_in"], "dependents of one package"),
        ("", "", ""),
        ("Cycle count", stats["cycle_count"], "strongly connected"),
        (
            "Largest subtree",
            f"{stats['largest_subtree_root']} ({stats['largest_subtree_size']} pkgs)",
            "from one root",
        ),
        (
            "Most depended upon",
            f"{stats['most_depended_upon']} ({stats['most_depended_upon_count']} deps)",
            "highest in-degree",
        ),
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
    from pyxray.analysis import compute_in_degrees, reachable_from

    graph = ctx.get_graph()
    ctx.emit_warnings()

    in_deg = compute_in_degrees(graph)
    top_n = args.top
    limit = getattr(args, "limit", None)

    ranked = sorted(in_deg.items(), key=lambda x: -x[1])
    if top_n:
        ranked = ranked[:top_n]

    # Apply --limit (R8)
    truncated = 0
    if limit and limit > 0 and len(ranked) > limit:
        truncated = len(ranked) - limit
        ranked = ranked[:limit]

    if ctx.json_output:
        out.print_json(
            {"hotspots": [{"package": k, "dependents": v} for k, v in ranked]}
        )
        return 0

    out.section(f"Dependency Hotspots (top {top_n or len(ranked)})")
    out.println(
        out.dim("  Packages with the most reverse dependencies (in-degree).")
        + out.dim("  Risk = dependents × (1 + subtree_size)")
    )
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

        # R4: subtree size (number of packages this one transitively pulls in, excluding self)
        subtree_size = len(reachable_from(graph, norm_name)) - 1
        risk = count * (1 + subtree_size)

        out.println(f"  {out.cyan(norm_name)}{ver}")
        out.println(
            f"  {bar}  {out.bold(str(count))} dependents  "
            f"{out.dim(f'subtree: {subtree_size}  risk: {risk}')}"
        )
        out.println()

    if truncated:
        out.println(out.dim(f"  … and {truncated} more"))

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
        out.print_json(
            {
                "longest_chain": chain,
                "length": len(chain),
                "has_cycles": bool(cycles),
            }
        )
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
    from pyxray.source import scan_with_usage, build_import_map, classify_imports

    project = ctx.get_project()
    graph = ctx.get_graph()
    installed = ctx.get_installed()
    ctx.emit_warnings()

    mapping_packages = {**installed, **graph.packages}
    import_map = build_import_map(mapping_packages)
    all_imports, usage_map, warnings = scan_with_usage(
        project.source_roots, project.root, import_map
    )
    for w in warnings:
        out.print_warn(w)

    third_party, stdlib_found, unknown = classify_imports(all_imports, import_map)

    if ctx.json_output:
        out.print_json(
            {
                "source_roots": project.source_roots,
                "total_imports": len(all_imports),
                "third_party": sorted(third_party),
                "stdlib": sorted(stdlib_found),
                "unknown": sorted(unknown),
            }
        )
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


# R2: helper to classify a file path as test vs production
_TEST_SEGMENTS = frozenset({"tests", "test", "testing", "spec", "specs"})


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
    from pyxray.source import scan_with_usage, build_import_map, classify_imports
    from pyxray.models import normalize_name

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


def cmd_prune(ctx: Context, args: argparse.Namespace) -> int:
    from pyxray import output as out
    from pyxray.analysis import compute_prune_candidates
    from pyxray.source import build_import_map, scan_with_usage
    from pyxray.hints import get_hint  # R3

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
        "--root",
        "-r",
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
        "--quiet",
        "-q",
        action="store_true",
        default=False,
        help="Suppress warnings",
    )
    parser.add_argument(
        "--version",
        "-V",
        action="version",
        version="PyXRay 0.1.0",
    )
    # R8: global --limit flag for list-style commands
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Limit list output to N items (0 = no limit). Applies to impact, hotspots, audit.",
    )

    # ── Graph source flags ────────────────────────────────────────────────
    source_group = parser.add_argument_group(
        "graph source",
        "Control where PyXRay reads dependency metadata from.\n"
        "Default: installed environment (importlib.metadata).\n"
        "Lock file (uv.lock / poetry.lock) is auto-detected if present.",
    )
    source_group.add_argument(
        "--from-lock",
        metavar="FILE",
        default=None,
        help=(
            "Explicit path to a lock file (uv.lock or poetry.lock). "
            "Analyses the graph without any packages needing to be installed."
        ),
    )
    source_group.add_argument(
        "--no-lock",
        action="store_true",
        default=False,
        help="Ignore any detected lock file; use the installed environment instead.",
    )
    source_group.add_argument(
        "--pypi",
        action="store_true",
        default=False,
        help=(
            "Fetch dependency metadata from PyPI JSON API (requires internet). "
            "Allows analysis of projects whose packages are not installed. "
            "Uses urllib.request (stdlib only)."
        ),
    )
    source_group.add_argument(
        "--max-packages",
        type=int,
        default=300,
        metavar="N",
        help="Maximum packages to fetch in --pypi mode (default: 300).",
    )

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    # summary
    p_sum = sub.add_parser("summary", help="Project dependency summary")
    p_sum.set_defaults(func=cmd_summary)

    # tree
    p_tree = sub.add_parser("tree", help="Render dependency tree")
    p_tree.add_argument(
        "--depth",
        "-d",
        type=int,
        default=None,
        help="Maximum tree depth to render",
    )
    p_tree.add_argument(
        "--sort-by",
        dest="sort_by",
        choices=["alpha", "in-degree"],
        default="alpha",
        help="Sort children alphabetically (default) or by in-degree descending (most-depended-upon first)",
    )
    p_tree.set_defaults(func=cmd_tree)

    # why
    p_why = sub.add_parser("why", help="Explain why a package is installed")
    p_why.add_argument("package", help="Package name to explain")
    p_why.add_argument(
        "--max-paths",
        type=int,
        default=5,
        help="Maximum number of paths to show (default: 5)",
    )
    p_why.set_defaults(func=cmd_why)

    # impact
    p_impact = sub.add_parser(
        "impact", help="Show packages affected if a package disappeared"
    )
    p_impact.add_argument("package", help="Package name to analyse")
    p_impact.add_argument(
        "--all",
        action="store_true",
        default=False,
        help="Expand deep transitive dependents (3+ hops) in full",
    )
    p_impact.set_defaults(func=cmd_impact)

    # duplicates
    p_dup = sub.add_parser(
        "duplicates", help="Detect packages installed with multiple versions"
    )
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
        "--top",
        "-n",
        type=int,
        default=20,
        help="Number of results to show (default: 20)",
    )
    p_hot.set_defaults(func=cmd_hotspots)

    # longest-chain
    p_lc = sub.add_parser("longest-chain", help="Find the longest dependency path")
    p_lc.set_defaults(func=cmd_longest_chain)

    # imports
    p_imp = sub.add_parser("imports", help="Scan source code for import statements")
    p_imp.add_argument(
        "--no-unknown",
        action="store_true",
        default=False,
        help="Suppress unclassified import listing",
    )
    p_imp.set_defaults(func=cmd_imports)

    # audit
    p_audit = sub.add_parser(
        "audit",
        help="Compare declared dependencies with detected source imports",
    )
    p_audit.set_defaults(func=cmd_audit)

    # prune
    p_prune = sub.add_parser(
        "prune",
        help="Find packages that can be removed or reimplemented",
    )
    p_prune.add_argument(
        "--thin",
        type=int,
        default=3,
        help="Max transitive deps to consider 'thin' (default: 3)",
    )
    p_prune.add_argument(
        "--narrow",
        type=int,
        default=3,
        help="Max source files importing to consider 'narrow' (default: 3)",
    )
    p_prune.add_argument(
        "--shallow",
        type=int,
        default=5,
        help="Max symbols imported to consider 'shallow' (default: 5)",
    )
    p_prune.set_defaults(func=cmd_prune)

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _empty_graph():
    """Return an empty DependencyGraph (used on error paths)."""
    from pyxray.models import DependencyGraph

    return DependencyGraph()


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Resolve graph source: --from-lock wins, then --pypi, then env default
    from_lock = getattr(args, "from_lock", None)
    use_pypi = getattr(args, "pypi", False)
    no_lock = getattr(args, "no_lock", False)
    max_packages = getattr(args, "max_packages", 300)

    ctx = Context(
        project_root=args.root,
        no_color=args.no_color,
        json_output=args.json,
        quiet=args.quiet,
        from_lock=from_lock,
        no_lock=no_lock,
        use_pypi=use_pypi,
        max_packages=max_packages,
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
